"""Selenium setup and element helpers for Reddit's web components."""

import os
from pathlib import Path
import shutil

from dotenv import load_dotenv

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait


def firefox_binary():
    load_dotenv()

    configured = os.getenv("FIREFOX_BINARY")

    if configured:
        path = Path(configured).expanduser()

        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

        raise RuntimeError(
            f"FIREFOX_BINARY is not an executable file: {path}"
        )

    for name in ("firefox-esr", "firefox"):
        path = shutil.which(name)

        if path:
            return path

    raise RuntimeError(
        "Firefox was not found. "
        "Install Firefox ESR or set FIREFOX_BINARY in .env."
    )


def geckodriver_binary():
    load_dotenv()

    configured = os.getenv("GECKODRIVER_BINARY")

    if configured:
        path = Path(configured).expanduser()

        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

        raise RuntimeError(
            f"GECKODRIVER_BINARY is not an executable file: {path}"
        )

    path = shutil.which("geckodriver")

    if path:
        return path

    raise RuntimeError(
        "geckodriver was not found. "
        "Install geckodriver or set GECKODRIVER_BINARY in .env."
    )


def create_driver(headless=False):
    options = webdriver.FirefoxOptions()

    options.binary_location = firefox_binary()
    options.page_load_strategy = "eager"

    if headless:
        options.add_argument("-headless")

    service = Service(
        executable_path=geckodriver_binary()
    )

    return webdriver.Firefox(
        service=service,
        options=options,
    )


def driver_for(scope):
    return scope if hasattr(scope, "execute_script") else scope.parent


def find_all(scope, selector):
    """Search a document/element and its open shadow roots, in DOM order."""

    return driver_for(scope).execute_script(
        """
        const scope = arguments[0] || document;
        const selector = arguments[1];
        const found = [];

        function visit(root) {
            for (const el of root.children || []) {

                if (el.matches(selector)) {
                    found.push(el);
                }

                if (el.shadowRoot) {
                    visit(el.shadowRoot);
                }

                visit(el);
            }
        }

        if (scope.shadowRoot) {
            visit(scope.shadowRoot);
        }

        visit(scope);

        return found;
        """,
        None if hasattr(scope, "execute_script") else scope,
        selector,
    )


def visible(elements):
    result = []

    for element in elements:
        try:
            if element.is_displayed():
                result.append(element)

        except StaleElementReferenceException:
            pass

    return result


def wait_element(
    scope,
    selector,
    timeout=10,
    visible_only=True,
):
    def locate(_):
        elements = find_all(scope, selector)

        if visible_only:
            elements = visible(elements)

        return elements[0] if elements else False

    return WebDriverWait(
        driver_for(scope),
        timeout,
        ignored_exceptions=(StaleElementReferenceException,),
    ).until(locate)


def text_of(scope, selector, default=""):
    elements = find_all(scope, selector)

    if not elements:
        return default

    return (
        elements[0].get_attribute("innerText") or ""
    ).strip()


def named_elements(scope, selector, name):
    return [
        element
        for element in visible(find_all(scope, selector))
        if (element.accessible_name or element.text)
        .strip()
        .casefold()
        == name.casefold()
    ]


def click_element(element):
    driver = driver_for(element)

    driver.execute_script(
        """
        arguments[0].scrollIntoView({
            block: 'center'
        });
        """,
        element,
    )

    WebDriverWait(driver, 10).until(
        lambda _: (
            element.is_displayed()
            and element.is_enabled()
        )
    )

    element.click()


def fill_editor(element, content):
    click_element(element)

    tag_name = element.tag_name.lower()

    if tag_name in ("input", "textarea"):
        element.clear()

    else:
        driver = driver_for(element)

        platform = (
            driver.capabilities
            .get("platformName", "")
            .lower()
        )

        modifier = (
            Keys.COMMAND
            if platform == "mac"
            else Keys.CONTROL
        )

        element.send_keys(modifier, "a")
        element.send_keys(Keys.BACKSPACE)

    element.send_keys(content)

    if tag_name in ("input", "textarea"):
        value = element.get_attribute("value")
    else:
        value = element.get_attribute("innerText")

    if content.strip() not in (value or "").strip():
        raise RuntimeError(
            "Reddit editor did not accept the supplied text."
        )