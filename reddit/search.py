

def search(query, page):
    page.locator('textarea[name="q"]').fill(query)
    page.locator('textarea[name="q"]').press("Enter")