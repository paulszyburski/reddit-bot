import os
import time

from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv("REDDIT_USERNAME")
PASSWORD = os.getenv("REDDIT_PASSWORD")


def has_visible_match(locator):
    for index in range(locator.count()):
        try:
            if locator.nth(index).is_visible():
                return True
        except Exception:
            continue
    return False


def login(page, max_attempts=10):
    for attempt in range(1, max_attempts + 1):
        print(f"Login attempt {attempt}/{max_attempts}")
        try:
            page.goto("https://www.reddit.com/", wait_until="domcontentloaded")
            page.get_by_role("link", name="Log In").click()

            username_input = page.locator('input[name="username"]')
            username_input.wait_for(state="visible", timeout=10_000)
            username_input.fill(USERNAME)
            page.locator('input[name="password"]').fill(PASSWORD)
            page.get_by_role("button", name="Log In").click()
            page.wait_for_timeout(2500)

            errors = page.get_by_text("Something went wrong", exact=False)
            if has_visible_match(errors):
                print("Reddit returned 'Something went wrong'. Retrying...")
                page.wait_for_timeout(2000)
                continue

            try:
                form_is_visible = username_input.is_visible()
            except Exception:
                form_is_visible = False

            login_links = page.get_by_role("link", name="Log In")
            if not form_is_visible or not has_visible_match(login_links):
                print("Logged in successfully")
                return True

            print("Login did not complete. Retrying...")
        except Exception as error:
            print(f"Login attempt failed: {error}")

        time.sleep(2)

    raise RuntimeError(f"Failed to log into Reddit after {max_attempts} attempts.")
