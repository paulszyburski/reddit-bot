from selenium.common.exceptions import TimeoutException
from reddit.browser import find_all, text_of, wait_element


def scrape_posts(page):
    wait_element(page, 'a[slot="title"]')
    return {post.text.strip(): post.get_attribute("href")
            for post in find_all(page, 'a[slot="title"]')}


def scrape_post(page):
    post = wait_element(page, "shreddit-post")
    href = page.current_url
    community = post.get_attribute("subreddit-prefixed-name") or text_of(post, 'a[href^="/r/"]')
    if community and not community.startswith("r/"):
        community = f"r/{community}"
    result = {
        "href": href,
        "community": community,
        "title": text_of(post, '[slot="title"]'),
        "description": text_of(post, "shreddit-post-text-body"),
        "username": post.get_attribute("author") or "",
        "comments": [],
    }
    try:
        wait_element(page, "shreddit-comment", visible_only=False)
    except TimeoutException:
        pass
    parents = {}
    for i, comment in enumerate(find_all(page, "shreddit-comment")):
        try:
            depth = int(comment.get_attribute("depth") or 0)
        except ValueError:
            depth = 0
        node = {
            "id": comment.get_attribute("thingid") or comment.get_attribute("id") or f"{href}#comment-{i}",
            "username": comment.get_attribute("author") or text_of(comment, 'a[href*="/user/"]'),
            "content": (text_of(comment, 'div[slot="comment"]')
                        or text_of(comment, '[id$="-comment-rtjson-content"]')
                        or text_of(comment, ".md")),
            "replies": [],
        }
        parent = parents.get(depth - 1) if depth else None
        (parent["replies"] if parent else result["comments"]).append(node)
        parents[depth] = node
        for old_depth in list(parents):
            if old_depth > depth:
                del parents[old_depth]
    return result
