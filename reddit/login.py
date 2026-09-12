from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import os
import time

load_dotenv()

USERNAME = os.getenv("REDDIT_USERNAME")
PASSWORD = os.getenv("REDDIT_PASSWORD")


def login(page, max_attempts=10):
    for attempt in range(1, max_attempts + 1):
        print(f"Login attempt {attempt}/{max_attempts}")

        try:
            page.goto(
                "https://reddit.com",
                wait_until="domcontentloaded"
            )

            page.get_by_role(
                "link",
                name="Log In"
            ).click()

            page.locator(
                'input[name="username"]'
            ).wait_for(
                state="visible",
                timeout=10000
            )

            page.locator(
                'input[name="username"]'
            ).fill(USERNAME)

            page.locator(
                'input[name="password"]'
            ).fill(PASSWORD)

            page.get_by_role(
                "button",
                name="Log In"
            ).click()

            # Give Reddit some time to either log in
            # or show the temporary error.
            page.wait_for_timeout(2500)

            # -----------------------------------------
            # Check for Reddit error messages
            # -----------------------------------------

            error_messages = page.get_by_text(
                "Something went wrong",
                exact=False
            )

            if error_messages.count():
                for i in range(error_messages.count()):
                    try:
                        if error_messages.nth(i).is_visible():
                            print("Reddit returned 'Something went wrong'. Retrying...")
                            break
                    except Exception:
                        pass
                else:
                    error_messages = None

                if error_messages is not None:
                    page.wait_for_timeout(2000)
                    continue

            # -----------------------------------------
            # Detect successful login
            # -----------------------------------------

            # Login dialog should disappear after success.
            username_input = page.locator(
                'input[name="username"]'
            )

            try:
                still_visible = username_input.is_visible()
            except Exception:
                still_visible = False

            if not still_visible:
                print("Logged in successfully")
                return True

            # Another possible sign:
            # login button/link disappeared.
            login_links = page.get_by_role(
                "link",
                name="Log In"
            )

            visible_login_link = False

            for i in range(login_links.count()):
                try:
                    if login_links.nth(i).is_visible():
                        visible_login_link = True
                        break
                except Exception:
                    pass

            if not visible_login_link:
                print("Logged in successfully")
                return True

            print("Login did not complete. Retrying...")

        except Exception as e:
            print(f"Login attempt failed: {e}")

        # wait before next attempt
        time.sleep(2)

    raise RuntimeError(
        f"Failed to log into Reddit after {max_attempts} attempts."
    )


if __name__ == "__main__":
    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        login(
            page,
            max_attempts=20
        )

        time.sleep(5000)

        browser.close()