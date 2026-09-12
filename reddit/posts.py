
import time



def scrape_posts(page):
    #for _ in range(100):
    #    page.mouse.wheel(0, 2000)
    #    time.sleep(0.3)

    titles = page.locator('a[slot="title"]')

    scraped = {}

    for i in range(titles.count()):
        post = titles.nth(i)

        title = post.inner_text().strip()
        link = post.get_attribute("href")

        scraped[title] = link

    return scraped

def scrape_post(page):

    post = page.locator("shreddit-post").first
    post.wait_for(state="visible")

    # -------------------------
    # Post href
    # -------------------------

    href = page.url

    # -------------------------
    # Post title
    # -------------------------

    title = ""

    title_locator = post.locator('[slot="title"]').first

    if title_locator.count():
        try:
            title = title_locator.inner_text().strip()
        except Exception:
            pass

    # -------------------------
    # OP username
    # -------------------------

    username = post.get_attribute("author") or ""

    # -------------------------
    # Community
    # -------------------------

    community = ""

    subreddit = post.get_attribute("subreddit-prefixed-name")

    if subreddit:
        community = subreddit

    if not community:
        subreddit_link = post.locator('a[href^="/r/"]').first

        if subreddit_link.count():
            try:
                community = subreddit_link.inner_text().strip()
            except Exception:
                pass

    if community and not community.startswith("r/"):
        community = f"r/{community}"

    # -------------------------
    # Description
    # -------------------------

    description = ""

    body = post.locator("shreddit-post-text-body").first

    if body.count():
        try:
            description = body.inner_text().strip()
        except Exception:
            pass

    # =========================================================
    # COMMENTS
    # =========================================================

    try:
        page.locator("shreddit-comment").first.wait_for(
            state="attached",
            timeout=10000
        )
    except Exception:
        pass

    comment_elements = page.locator("shreddit-comment")

    flat_comments = []

    for i in range(comment_elements.count()):

        comment = comment_elements.nth(i)

        # -------------------------
        # Unique comment ID
        # -------------------------

        comment_id = (
            comment.get_attribute("thingid")
            or comment.get_attribute("id")
            or f"{href}#comment-{i}"
        )

        # -------------------------
        # Comment depth
        # -------------------------

        try:
            depth = int(comment.get_attribute("depth") or 0)
        except ValueError:
            depth = 0

        # -------------------------
        # Comment username
        # -------------------------

        comment_username = comment.get_attribute("author") or ""

        if not comment_username:
            author = comment.locator('a[href*="/user/"]').first

            if author.count():
                try:
                    comment_username = author.inner_text().strip()
                except Exception:
                    pass

        # -------------------------
        # Comment content
        # -------------------------

        content = ""

        content_locator = comment.locator(
            'div[slot="comment"]'
        ).first

        if content_locator.count():
            try:
                content = content_locator.inner_text().strip()
            except Exception:
                pass

        if not content:
            content_locator = comment.locator(
                '[id$="-comment-rtjson-content"]'
            ).first

            if content_locator.count():
                try:
                    content = content_locator.inner_text().strip()
                except Exception:
                    pass

        if not content:
            content_locator = comment.locator(".md").first

            if content_locator.count():
                try:
                    content = content_locator.inner_text().strip()
                except Exception:
                    pass

        flat_comments.append({
            "id": comment_id,
            "depth": depth,
            "username": comment_username,
            "content": content,
        })

    # =========================================================
    # Convert flat comments into nested tree
    # =========================================================

    comments = []

    parents = {}

    for item in flat_comments:

        depth = item["depth"]

        node = {
            "id": item["id"],
            "username": item["username"],
            "content": item["content"],
            "replies": [],
        }

        if depth == 0:

            comments.append(node)

        else:

            parent = parents.get(depth - 1)

            if parent:
                parent["replies"].append(node)

            else:
                comments.append(node)

        parents[depth] = node

        # Remove parents from deeper levels
        # because they can no longer be the parent
        # of subsequent comments at this depth.

        for old_depth in list(parents.keys()):
            if old_depth > depth:
                del parents[old_depth]

    # =========================================================
    # Return scraped post
    # =========================================================

    return {
        "href": href,
        "community": community,
        "title": title,
        "description": description,
        "username": username,
        "comments": comments,
    }