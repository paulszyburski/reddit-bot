import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"AI.chatgpt": types.ModuleType("AI.chatgpt")}):
    utils = importlib.import_module("reddit.conversations.utils")


class ReplySubmitTests(unittest.TestCase):
    def attempt(self, button=None):
        page = Mock()
        page.evaluate.return_value = {"width": 1200, "height": 800}
        editor = Mock()
        scope = Mock()
        scope.locator.return_value = "scoped"
        page.get_by_role.return_value = "global"

        def visible(locator):
            if button is not None:
                return [button] if locator == "global" else []
            return [Mock()] if page.mouse.click.called else []

        with patch.object(utils, "_find_composer_scope", return_value=scope), \
             patch.object(utils, "_visible_elements", side_effect=visible):
            result = utils._click_reply_submit(page, editor)
        return result, page

    def test_missing_submit_is_found_after_center_click(self):
        result, page = self.attempt()
        self.assertTrue(result)
        page.mouse.click.assert_called_once_with(600, 400)

    def test_obstructed_submit_is_retried_after_center_click(self):
        button = Mock()
        button.click.side_effect = [TimeoutError("popup intercepted click"), None]
        result, page = self.attempt(button)
        self.assertTrue(result)
        page.mouse.click.assert_called_once_with(600, 400)
        self.assertEqual(button.click.call_count, 2)

    def test_success_does_not_click_center(self):
        result, page = self.attempt(Mock())
        self.assertTrue(result)
        page.mouse.click.assert_not_called()

    def test_persistent_obstruction_stops_after_one_retry(self):
        button = Mock()
        button.click.side_effect = TimeoutError("still obstructed")
        result, page = self.attempt(button)
        self.assertFalse(result)
        page.mouse.click.assert_called_once_with(600, 400)
        self.assertEqual(button.click.call_count, 2)


if __name__ == "__main__":
    unittest.main()
