import os
import time

from dotenv import load_dotenv
from selenium.webdriver.support.ui import WebDriverWait

from reddit.browser import (
    create_driver,
    fill_editor,
    named_elements,
    wait_element,
    find_all,
    visible,
    click_element,
)

load_dotenv()

USERNAME = os.getenv("REDDIT_USERNAME")
PASSWORD = os.getenv("REDDIT_PASSWORD")


def is_logged_in(page):
    """
    Return True when Reddit appears to be logged in.

    We intentionally do NOT rely on the 'Log In' link disappearing,
    because Reddit can leave matching elements in the DOM.
    """

    # Login form should no longer be visible.
    username_inputs = visible(
        find_all(page, 'input[name="username"]')
    )

    password_inputs = visible(
        find_all(page, 'input[name="password"]')
    )

    if username_inputs or password_inputs:
        return False

    # Look for UI elements normally present for a logged-in user.
    logged_in_selectors = [
        "#expand-user-drawer-button",
        'button[aria-label*="user menu" i]',
        'button[aria-label*="profile" i]',
        '[data-testid="user-menu"]',
    ]

    for selector in logged_in_selectors:
        try:
            if visible(find_all(page, selector)):
                return True
        except Exception:
            pass

    return False


def print_login_debug(page):
    print("Current URL:", page.current_url)

    try:
        print("Title:", page.title)
    except Exception:
        pass

    try:
        username_visible = bool(
            visible(find_all(page, 'input[name="username"]'))
        )

        print("Username field visible:", username_visible)
    except Exception:
        pass


def login(page, max_attempts=10):

    if not USERNAME or not PASSWORD:
        raise RuntimeError(
            "REDDIT_USERNAME or REDDIT_PASSWORD is missing from .env"
        )

    for attempt in range(1, max_attempts + 1):

        print()
        print(f"Login attempt {attempt}/{max_attempts}")

        try:
            # IMPORTANT: plain URL, not Markdown.
            page.get("https://www.reddit.com/")

            # Give Reddit's JS a moment to initialize.
            time.sleep(2)

            # Maybe we're already logged in from an existing profile/session.
            if is_logged_in(page):
                print("Already logged in")
                return True

            print("Looking for Log In button...")

            links = WebDriverWait(
                page,
                15,
                poll_frequency=0.5,
            ).until(
                lambda _:
                named_elements(
                    page,
                    'a, button, [role="link"], [role="button"]',
                    "Log In",
                )
                or False
            )

            print("Clicking Log In...")
            click_element(links[0])

            # Let the login modal/dialog render.
            time.sleep(1.5)

            print("Waiting for username field...")

            username_input = wait_element(
                page,
                'input[name="username"]',
                timeout=15,
            )

            print("Entering username...")
            fill_editor(username_input, USERNAME)

            # Small pause helps Reddit/react state catch up.
            time.sleep(0.5)

            print("Waiting for password field...")

            password_input = wait_element(
                page,
                'input[name="password"]',
                timeout=15,
            )

            print("Entering password...")
            fill_editor(password_input, PASSWORD)

            time.sleep(0.8)

            print("Looking for submit button...")

            buttons = WebDriverWait(
                page,
                15,
                poll_frequency=0.5,
            ).until(
                lambda _:
                [
                    button
                    for button in named_elements(
                        page,
                        'button, [role="button"]',
                        "Log In",
                    )
                    if button.is_enabled()
                ]
                or False
            )

            print("Submitting login...")
            click_element(buttons[0])

            # Don't immediately inspect the DOM.
            # Reddit needs time to send the request, authenticate,
            # update cookies and rerender.
            time.sleep(2)

            print("Waiting for Reddit to confirm login...")

            logged_in = WebDriverWait(
                page,
                30,
                poll_frequency=0.5,
            ).until(
                lambda _: is_logged_in(page)
            )

            if logged_in:
                print("Logged in successfully")
                print("URL:", page.current_url)

                # Extra stabilization before the rest of the bot continues.
                time.sleep(2)

                return True

        except Exception as error:
            print(f"Login attempt failed: {type(error).__name__}: {error}")

            print_login_debug(page)

        if attempt < max_attempts:
            print("Waiting before next attempt...")
            time.sleep(4)

    raise RuntimeError(
        f"Failed to log into Reddit after {max_attempts} attempts."
    )


if __name__ == "__main__":

    driver = create_driver()

    try:
        login(driver, max_attempts=20)

        input("Press Enter to close the browser...")

    finally:
        driver.quit()