def locator_text(locator):
    if not locator.count():
        return ""
    try:
        return locator.inner_text().strip()
    except Exception:
        return ""


def scrape_posts(page):
    titles = page.locator('a[slot="title"]')
    return {
        titles.nth(index).inner_text().strip(): titles.nth(index).get_attribute("href")
        for index in range(titles.count())
    }


def scrape_comments(page, post_href):
    try:
        page.locator("shreddit-comment").first.wait_for(
            state="attached",
            timeout=10_000,
        )
    except Exception:
        pass

    elements = page.locator("shreddit-comment")
    comments = []
    parents = {}

    for index in range(elements.count()):
        element = elements.nth(index)
        comment_id = (
            element.get_attribute("thingid")
            or element.get_attribute("id")
            or f"{post_href}#comment-{index}"
        )
        try:
            depth = int(element.get_attribute("depth") or 0)
        except ValueError:
            depth = 0

        username = element.get_attribute("author") or locator_text(
            element.locator('a[href*="/user/"]').first
        )
        content = ""
        for selector in (
            'div[slot="comment"]',
            '[id$="-comment-rtjson-content"]',
            ".md",
        ):
            content = locator_text(element.locator(selector).first)
            if content:
                break

        node = {
            "id": comment_id,
            "username": username,
            "content": content,
            "replies": [],
        }
        parent = parents.get(depth - 1)
        if depth and parent:
            parent["replies"].append(node)
        else:
            comments.append(node)

        parents[depth] = node
        parents = {level: item for level, item in parents.items() if level <= depth}

    return comments


def scrape_post(page):
    post = page.locator("shreddit-post").first
    post.wait_for(state="visible")

    community = post.get_attribute("subreddit-prefixed-name") or locator_text(
        post.locator('a[href^="/r/"]').first
    )
    if community and not community.startswith("r/"):
        community = f"r/{community}"

    return {
        "href": page.url,
        "community": community,
        "title": locator_text(post.locator('[slot="title"]').first),
        "description": locator_text(post.locator("shreddit-post-text-body").first),
        "username": post.get_attribute("author") or "",
        "comments": scrape_comments(page, page.url),
    }
