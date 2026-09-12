import json
import unittest
from unittest.mock import Mock

from AI.prompts import follow_up_prompt, planning_prompt, select_post


class AIUsageTests(unittest.TestCase):
    def test_excluded_and_duplicate_urls_are_filtered_before_ai(self):
        generate = Mock(return_value="https://www.reddit.com/r/test/comments/new/title/")
        posts = {
            "Old": "/r/test/comments/old/title/?tracking=1",
            "New": "/r/test/comments/new/title/",
            "Duplicate": "https://www.reddit.com/r/test/comments/new/title/?tracking=1",
        }
        result = select_post(posts, ["https://www.reddit.com/r/test/comments/old/title/"], generate)
        self.assertEqual(result, "https://www.reddit.com/r/test/comments/new/title/")
        candidates = json.loads(generate.call_args.args[0].split("CANDIDATES:\n")[1])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title"], "New")

    def test_empty_candidates_need_no_ai_call(self):
        generate = Mock()
        self.assertIsNone(select_post({"Old": "/comments/old/title"}, ["/comments/old/title"], generate))
        generate.assert_not_called()

    def test_none_or_invented_url_is_not_navigated_to(self):
        for response in ("NONE", "https://example.com", "/comments/other/title"):
            with self.subTest(response=response):
                self.assertIsNone(select_post({"Test": "/comments/new/title"}, [], Mock(return_value=response)))

    def test_compact_context_preserves_nested_replies_history_and_app_links(self):
        post = {"comments": [{"id": "one", "content": "parent", "replies": [
            {"id": "two", "content": "I joined the group", "replies": []}
        ]}]}
        app = {"name": "test", "GoogleGroupLink": "https://groups.google.com/g/test"}
        conversation = {"ourUsername": "bot", "youAreTalkingTo": "tester", "thread": post,
                        "ourMessages": [{"content": "Earlier message"}], "sourcePath": "internal/path"}
        prompt = follow_up_prompt(conversation, app)
        data = json.loads(prompt.split("DATA:\n")[1])
        self.assertEqual(data["thread"], post)
        self.assertEqual(data["ourMessages"], conversation["ourMessages"])
        self.assertEqual(data["app"], app)
        self.assertNotIn("sourcePath", data)
        planning = json.loads(planning_prompt(post, "bot", app).split("DATA:\n")[1])
        self.assertEqual(planning["post"], post)


if __name__ == "__main__":
    unittest.main()
