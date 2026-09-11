"""Selenium setup and element helpers for Reddit's web components."""
import os
from pathlib import Path
import shutil

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


def chromium_binary():
    load_dotenv()
    configured = os.getenv("CHROMIUM_BINARY")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        raise RuntimeError(f"CHROMIUM_BINARY is not an executable file: {path}")

    for name in ("chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path

    # Reuse an existing Chromium download without requiring its old tooling.
    cache = Path.home() / ".cache" / "ms-playwright"
    candidates = sorted(
        cache.glob("chromium-*/chrome-linux*/chrome"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError("Chromium was not found. Install Chromium or set CHROMIUM_BINARY in .env to its executable path.")


def create_driver(headless=False):
    options = webdriver.ChromeOptions()
    # Chromium uses Selenium's Chrome driver, with an explicit browser binary.
    options.binary_location = chromium_binary()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    return webdriver.Chrome(options=options)


def driver_for(scope):
    return scope if hasattr(scope, "execute_script") else scope.parent


def find_all(scope, selector):
    """Search a document/element and its open shadow roots, in DOM order."""
    return driver_for(scope).execute_script("""
        const scope = arguments[0] || document;
        const selector = arguments[1];
        const found = [];
        function visit(root) {
            for (const el of root.children || []) {
                if (el.matches(selector)) found.push(el);
                if (el.shadowRoot) visit(el.shadowRoot);
                visit(el);
            }
        }
        if (scope.shadowRoot) visit(scope.shadowRoot);
        visit(scope);
        return found;
    """, None if hasattr(scope, "execute_script") else scope, selector)


def visible(elements):
    result = []
    for element in elements:
        try:
            if element.is_displayed():
                result.append(element)
        except StaleElementReferenceException:
            pass
    return result


def wait_element(scope, selector, timeout=10, visible_only=True):
    def locate(_):
        elements = find_all(scope, selector)
        if visible_only:
            elements = visible(elements)
        return elements[0] if elements else False
    return WebDriverWait(driver_for(scope), timeout,
                         ignored_exceptions=(StaleElementReferenceException,)).until(locate)


def text_of(scope, selector, default=""):
    elements = find_all(scope, selector)
    return (elements[0].get_attribute("innerText") or "").strip() if elements else default


def named_elements(scope, selector, name):
    return [element for element in visible(find_all(scope, selector))
            if (element.accessible_name or element.text).strip().casefold() == name.casefold()]


def click_element(element):
    driver_for(element).execute_script(
        "arguments[0].scrollIntoView({block: 'center'});", element)
    WebDriverWait(driver_for(element), 10).until(
        lambda _: element.is_displayed() and element.is_enabled())
    element.click()


def fill_editor(element, content):
    click_element(element)
    if element.tag_name.lower() in ("input", "textarea"):
        element.clear()
    else:
        modifier = Keys.COMMAND if driver_for(element).capabilities.get("platformName", "").lower() == "mac" else Keys.CONTROL
        element.send_keys(modifier, "a")
        element.send_keys(Keys.BACKSPACE)
    element.send_keys(content)
    value = element.get_attribute("value") if element.tag_name.lower() in ("input", "textarea") else element.get_attribute("innerText")
    if content.strip() not in (value or "").strip():
        raise RuntimeError("Reddit editor did not accept the supplied text.")
