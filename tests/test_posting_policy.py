from datetime import datetime, timedelta, timezone
import unittest

from reddit.conversations.posting_policy import (
    eligible_reply_ids,
    outreach_reason,
    posting_limit_reason,
)


class PostingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)

    def conversation(self, hours=1, username="bot", count=1):
        return {
            "ourUsername": username,
            "youAreTalkingTo": "tester",
            "postHref": "/comments/post/title/",
            "ourMessages": [
                {
                    "sentAt": (self.now - timedelta(hours=hours + i)).isoformat(),
                    "content": "Our message",
                    "replyTo": "already_answered",
                }
                for i in range(count)
            ],
        }

    def test_limits_use_persisted_history_and_rolling_window(self):
        self.assertIsNone(posting_limit_reason([], "bot", now=self.now))
        self.assertIn(
            "interval", posting_limit_reason([self.conversation(hours=0.1)], "bot", now=self.now)
        )
        self.assertIn(
            "new-conversation",
            posting_limit_reason(
                [self.conversation()] * 3, "bot", new_conversation=True, now=self.now
            ),
        )
        self.assertIn(
            "message limit",
            posting_limit_reason([self.conversation(count=10)], "bot", now=self.now),
        )
        self.assertIsNone(
            posting_limit_reason(
                [self.conversation(hours=25)] * 10, "bot", new_conversation=True, now=self.now
            )
        )
        self.assertIsNone(
            posting_limit_reason(
                [self.conversation(username="someone_else")] * 10, "bot", now=self.now
            )
        )

    def test_same_person_or_post_cannot_be_recruited_again(self):
        history = [self.conversation()]
        candidate = {
            "ourUsername": "BOT",
            "targetUsername": "TESTER",
            "postHref": "/comments/other/title/",
        }
        self.assertIn("person", outreach_reason(history, candidate))
        candidate.update(
            targetUsername="other", postHref="https://www.reddit.com/comments/post/changed/?x=1"
        )
        self.assertIn("post", outreach_reason(history, candidate))

    def test_only_unanswered_target_replies_under_our_latest_message_qualify(self):
        conversation = self.conversation()
        target = lambda id: {"id": id, "username": "tester", "content": "Yes!", "replies": []}
        post = {
            "comments": [
                target("unrelated"),
                {
                    "id": "ours",
                    "username": "bot",
                    "content": "Our message",
                    "replies": [
                        target("new"),
                        target("already_answered"),
                        {"id": "stranger", "username": "other", "content": "Hi"},
                    ],
                },
            ]
        }
        self.assertEqual(eligible_reply_ids(conversation, post), {"new"})
        conversation["ourMessages"].append({"content": "Next answer", "replyTo": "new"})
        self.assertEqual(eligible_reply_ids(conversation, post), set())

    def test_unknown_send_timestamp_blocks_instead_of_resetting_limits(self):
        self.assertIsNotNone(posting_limit_reason([{"ourUsername": "bot"}], "bot", now=self.now))


if __name__ == "__main__":
    unittest.main()
