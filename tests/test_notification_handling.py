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
        self.post = {"comments": [{"id": "t1_ours_before", "username": "bot",
                                  "content": "Initial offer", "replies": [self.comment]}]}
        self.ongoing.write_text(json.dumps([{
            "postHref": self.href, "appName": "app", "ourUsername": "bot",
            "thread": {}, "youAreTalkingTo": "user",
            "ourMessages": [{"content": "Initial offer", "sentAt": "2020-01-01T00:00:00+00:00",
                             "replyTo": "t1_original"}],
        }]))
        self.page = Mock()
        self.ai = Mock(return_value={"action": "none"})
        for name, value in [
            ("CONTACTED_NOTIFICATIONS_PATH", self.history),
            ("ONGOING_PATH", self.ongoing),
            ("generate_response", self.ai),
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
        self.assertEqual(len(saved["ourMessages"]), 2)

    def test_invalid_decision_is_retryable(self):
        self.ai.return_value = {"action": "reply", "content": "", "replyTo": "t1_first"}
        self.handle()
        self.assertFalse(self.history.exists())
        self.ai.return_value = {"action": "none"}
        self.handle()
        self.assertTrue(self.history.exists())

    def test_malformed_ai_responses_remain_retryable(self):
        for response in ('not json', '[]', 'null', {"action": "reply", "content": 123}):
            with self.subTest(response=response):
                self.ai.return_value = response
                self.handle()
                self.assertFalse(self.history.exists())

    def test_notification_url_matches_post_id_despite_slug_and_query(self):
        self.handle()
        self.history.unlink()
        conversations.handle_conversation_reply(
            self.page, "https://www.reddit.com/r/test/comments/post/different_slug/new_reply/?context=3"
        )
        self.assertEqual(self.ai.call_count, 2)

    def test_wrong_reply_target_is_rejected(self):
        saved = json.loads(self.ongoing.read_text())
        saved[0]["youAreTalkingTo"] = "expected_user"
        self.ongoing.write_text(json.dumps(saved))
        self.ai.return_value = {
            "action": "reply", "replyTo": "t1_first", "content": "Answer",
            "targetUsername": "user",
        }
        with patch.object(conversations, "_post_reply") as send:
            self.handle()
            send.assert_not_called()
        self.assertFalse(self.history.exists())

    def test_unrelated_reply_does_not_trigger_ai(self):
        self.post = {"comments": [self.comment]}
        self.handle()
        self.ai.assert_not_called()
        self.assertFalse(self.history.exists())

    def test_cooldown_defers_notification_without_marking_handled(self):
        saved = json.loads(self.ongoing.read_text())
        saved[0]["ourMessages"][0]["sentAt"] = conversations.datetime.now(conversations.timezone.utc).isoformat()
        self.ongoing.write_text(json.dumps(saved))
        self.handle()
        self.ai.assert_not_called()
        self.assertFalse(self.history.exists())

    def test_outreach_queue_and_restart_respect_send_interval(self):
        source = Path(self.temp.name) / "queue_source.json"
        planned = Path(self.temp.name) / "queue.json"
        posts = []
        queue = []
        for index in range(2):
            href = f"https://www.reddit.com/r/test/comments/post{index}/title/"
            posts.append({"href": href, "username": f"new_user{index}"})
            queue.append({"id": str(index), "postHref": href, "sourcePath": str(source),
                          "action": "comment", "content": "An offer", "ourUsername": "bot",
                          "targetUsername": f"new_user{index}"})
        source.write_text(json.dumps(posts))
        planned.write_text(json.dumps(queue))
        with patch.object(conversations, "PLANNED_PATH", planned), \
             patch.object(conversations, "_add_contacted_post"), \
             patch.object(conversations, "_post_top_level_comment") as send:
            conversations.execute_conversations(self.page)
            conversations.execute_conversations(self.page)
            send.assert_called_once()
        self.assertEqual(len(json.loads(planned.read_text())), 1)

    def test_planning_skips_contacted_and_duplicate_posts(self):
        source = Path(self.temp.name) / "posts.json"
        contacted = Path(self.temp.name) / "contacted.txt"
        planned = Path(self.temp.name) / "planned.json"
        contacted.write_text("https://www.reddit.com/r/test/comments/old/title/\n")
        source.write_text(json.dumps([
            {"href": "/r/test/comments/old/title/?tracking=1"},
            {"href": self.href},
            {"href": self.href + "?tracking=1"},
        ]))
        self.ai.return_value = json.dumps({"action": "none", "content": ""})
        with patch.object(conversations, "CONTACTED_PATH", contacted), \
             patch.object(conversations, "PLANNED_PATH", planned):
            decisions = conversations.plan_conversations(str(source), "bot", {"name": "test"})
        self.ai.assert_called_once()
        self.assertEqual(len(decisions), 1)
        self.assertIn("lastChecked", decisions[0])


if __name__ == "__main__":
    unittest.main()
