import unittest
from unittest.mock import Mock, patch

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from reddit import browser, posts


def element(**attrs):
    item = Mock(spec=WebElement)
    item.get_attribute.side_effect = attrs.get
    item.is_displayed.return_value = True
    item.is_enabled.return_value = True
    item.parent = Mock()
    return item


class SeleniumBrowserTests(unittest.TestCase):
    def test_shadow_search_uses_element_scope(self):
        scope = element()
        child = element()
        scope.parent.execute_script.return_value = [child]
        self.assertEqual(browser.find_all(scope, "button"), [child])
        args = scope.parent.execute_script.call_args.args
        self.assertIs(args[1], scope)
        self.assertEqual(args[2], "button")
        self.assertIn("shadowRoot", args[0])

    def test_fill_contenteditable_uses_only_target_element(self):
        editor = element(innerText="New reply")
        editor.tag_name = "div"
        editor.parent.capabilities = {"platformName": "linux"}
        browser.fill_editor(editor, "New reply")
        self.assertEqual(editor.send_keys.call_args_list[0].args, (Keys.CONTROL, "a"))
        editor.send_keys.assert_any_call(Keys.BACKSPACE)
        editor.send_keys.assert_any_call("New reply")
        editor.click.assert_called_once()

    def test_fill_input_clears_previous_value(self):
        editor = element(value="username")
        editor.tag_name = "input"
        browser.fill_editor(editor, "username")
        editor.clear.assert_called_once()
        editor.send_keys.assert_called_once_with("username")

    def test_post_scrape_preserves_nested_conversation_shape(self):
        driver = Mock()
        driver.current_url = "https://www.reddit.com/r/test/comments/post/title/"
        post = element(author="op", **{"subreddit-prefixed-name": "r/test"})
        comments = [element(thingid="t1_a", depth="0", author="user"),
                    element(thingid="t1_b", depth="1", author="bot")]
        with patch.object(posts, "wait_element", return_value=post), \
             patch.object(posts, "find_all", return_value=comments), \
             patch.object(posts, "text_of", return_value="text"):
            result = posts.scrape_post(driver)
        self.assertEqual(result["href"], driver.current_url)
        self.assertEqual(result["username"], "op")
        self.assertEqual(result["comments"][0]["id"], "t1_a")
        self.assertEqual(result["comments"][0]["replies"][0]["id"], "t1_b")

    def test_driver_creation_configures_selenium(self):
        with patch.object(browser.webdriver, "Chrome") as chrome:
            browser.create_driver(headless=True)
        options = chrome.call_args.kwargs["options"]
        self.assertEqual(options.page_load_strategy, "eager")
        self.assertIn("--headless=new", options.arguments)


if __name__ == "__main__":
    unittest.main()
