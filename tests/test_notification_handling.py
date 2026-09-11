import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

# Keep these tests independent of API credentials and network clients.
chatgpt = types.ModuleType("AI.chatgpt")
chatgpt.generate_response = Mock()
with patch.dict(sys.modules, {"AI.chatgpt": chatgpt}):
    conversations = importlib.import_module("reddit.conversations.conversations")

from reddit.conversations.notifications import notification_state_key


class NotificationHandlingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.history = Path(self.temp.name) / "contacted_notifications.txt"
        self.ongoing = Path(self.temp.name) / "ongoing.json"
        self.href = "https://www.reddit.com/r/test/comments/post/title/"
        self.comment = {"id": "t1_first", "username": "user", "content": "Hi", "replies": []}
        self.post = {"comments": [self.comment]}
        self.ongoing.write_text(json.dumps([{
            "postHref": self.href, "appName": "app", "ourUsername": "bot",
            "thread": {}, "ourMessages": [],
        }]))
        self.page = Mock()
        self.ai = Mock(return_value={"action": "none"})
        for name, value in [
            ("CONTACTED_NOTIFICATIONS_PATH", self.history),
            ("ONGOING_PATH", self.ongoing),
            ("generate_response", self.ai),
            ("wait_element", Mock()),
            ("time", Mock()),
            ("scrape_post", Mock(side_effect=lambda page: copy.deepcopy(self.post))),
        ]:
            patcher = patch.object(conversations, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def handle(self):
        conversations.handle_conversation_reply(self.page, self.href)

    def test_legacy_url_does_not_block_and_unchanged_thread_is_skipped(self):
        self.history.write_text(self.href + "\n")
        self.handle()
        self.handle()
        self.assertEqual(self.ai.call_count, 1)
        self.assertEqual(len(self.history.read_text().splitlines()), 2)

    def test_new_reply_at_same_url_is_processed(self):
        self.handle()
        self.comment["replies"].append({
            "id": "t1_next", "username": "user", "content": "Another question", "replies": [],
        })
        self.handle()
        self.assertEqual(self.ai.call_count, 2)

    def test_own_reply_and_ranking_do_not_create_new_event(self):
        key = notification_state_key(self.post, "bot", self.href)
        self.comment["score"] = 10
        self.comment["replies"].append({
            "id": "t1_ours", "username": "BOT", "content": "Answer", "replies": [],
        })
        self.assertEqual(key, notification_state_key(self.post, "bot", self.href))

    def test_failed_send_is_retryable_and_success_is_deduplicated(self):
        self.ai.return_value = {
            "action": "reply", "replyTo": "t1_first", "content": "Answer",
            "targetUsername": "user",
        }
        with patch.object(conversations, "_find_reddit_comment", return_value=Mock()), \
             patch.object(conversations, "_post_reply", side_effect=[RuntimeError("failed"), None]) as send:
            self.handle()
            self.assertFalse(self.history.exists())
            self.handle()
            self.handle()
            self.assertEqual(send.call_count, 2)
        saved = json.loads(self.ongoing.read_text())[0]
        self.assertEqual(len(saved["ourMessages"]), 1)

    def test_invalid_decision_is_retryable(self):
        self.ai.return_value = {"action": "reply", "content": "", "replyTo": "t1_first"}
        self.handle()
        self.assertFalse(self.history.exists())
        self.ai.return_value = {"action": "none"}
        self.handle()
        self.assertTrue(self.history.exists())


if __name__ == "__main__":
    unittest.main()


class SeleniumReplyTests(unittest.TestCase):
    def test_reply_uses_new_editor_and_requested_comment(self):
        from reddit.conversations import utils
        comment = Mock()
        nested_comment = Mock()
        nested_button = Mock()
        button = Mock()
        button.accessible_name = "Reply"
        page = Mock()
        page.execute_script.side_effect = [nested_comment, comment]
        old_editor = Mock(id="search")
        new_editor = Mock(id="reply")

        def find(scope, selector):
            if selector == 'button, [role="button"]':
                return [nested_button, button]
            if scope is comment:
                return [new_editor]
            return [old_editor]

        with patch.object(utils, "_find_reddit_comment", return_value=comment) as lookup, \
             patch.object(utils, "find_all", side_effect=find), \
             patch.object(utils, "click_element") as click, \
             patch.object(utils, "fill_editor") as fill, \
             patch.object(utils, "_submit_editor") as submit:
            utils._post_reply(page, "t1_target", "Hello")
        lookup.assert_called_once_with(page, "t1_target")
        click.assert_called_once_with(button)
        fill.assert_called_once_with(new_editor, "Hello")
        submit.assert_called_once_with(page, new_editor)
