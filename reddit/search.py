from selenium.webdriver.common.keys import Keys
from reddit.browser import fill_editor, wait_element


def search(query, page):
    field = wait_element(page, 'textarea[name="q"], input[name="q"]')
    fill_editor(field, query)
    field.send_keys(Keys.ENTER)
