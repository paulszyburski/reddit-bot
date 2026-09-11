import os
import time
from dotenv import load_dotenv
from selenium.webdriver.support.ui import WebDriverWait
from reddit.browser import create_driver, fill_editor, named_elements, wait_element, find_all, visible, click_element

load_dotenv()
USERNAME = os.getenv("REDDIT_USERNAME")
PASSWORD = os.getenv("REDDIT_PASSWORD")


def login(page, max_attempts=10):
    for attempt in range(1, max_attempts + 1):
        print(f"Login attempt {attempt}/{max_attempts}")
        try:
            page.get("https://reddit.com")
            link = WebDriverWait(page, 10).until(
                lambda _: named_elements(page, 'a, [role="link"]', "Log In"))
            click_element(link[0])
            fill_editor(wait_element(page, 'input[name="username"]'), USERNAME)
            fill_editor(wait_element(page, 'input[name="password"]'), PASSWORD)
            buttons = WebDriverWait(page, 10).until(
                lambda _: [button for button in named_elements(page, 'button, [role="button"]', "Log In")
                           if button.is_enabled()])
            click_element(buttons[0])
            # Wait for both the dialog and login link to disappear.
            WebDriverWait(page, 15).until(
                lambda _: not visible(find_all(page, 'input[name="username"]'))
                and not named_elements(page, 'a, [role="link"]', "Log In"))
            print("Logged in successfully")
            return True
        except Exception as error:
            print(f"Login attempt failed: {error}")
        time.sleep(2)
    raise RuntimeError(f"Failed to log into Reddit after {max_attempts} attempts.")


if __name__ == "__main__":
    driver = create_driver()
    try:
        login(driver, max_attempts=20)
        input("Press Enter to close the browser...")
    finally:
        driver.quit()
