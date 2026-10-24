import hashlib
import json


def notification_state_key(post, our_username, post_href):
    incoming = []

    def collect(comments):
        for comment in comments:
            if not comment.get("isOurs") and (
                (comment.get("username") or "").casefold() != our_username.casefold()
            ):
                incoming.append(
                    {
                        "id": comment.get("id"),
                        "username": comment.get("username"),
                        "content": comment.get("content"),
                    }
                )
            collect(comment.get("replies", []))

    collect(post.get("comments", []))
    comments = sorted(json.dumps(item, sort_keys=True) for item in incoming)
    state = json.dumps(
        {
            "postHref": post_href.rstrip("/"),
            "ourUsername": our_username.casefold(),
            "comments": comments,
        },
        sort_keys=True,
    )
    return "thread-v1:" + hashlib.sha256(state.encode("utf-8")).hexdigest()


def mark_notification_handled(path, key):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(key + "\n")


def scrape_notifications(page, max_scrolls=5):
    page.goto("https://www.reddit.com/notifications", wait_until="domcontentloaded")

    try:
        page.locator("notification-item").first.wait_for(state="attached", timeout=10_000)
    except Exception:
        pass

    previous_count = 0

    for _ in range(max_scrolls):
        notifications = page.locator("notification-item")
        current_count = notifications.count()

        if current_count == previous_count and current_count > 0:
            break

        previous_count = current_count

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)

    notifications = page.locator("notification-item")

    results = []

    for i in range(notifications.count()):
        notification = notifications.nth(i)

        try:
            text = notification.inner_text().strip()
        except Exception:
            text = ""

        href = ""

        links = notification.locator("a[href]")

        for j in range(links.count()):
            try:
                candidate = links.nth(j).get_attribute("href")

                if not candidate:
                    continue

                if "/comments/" in candidate:
                    href = candidate
                    break

                if not href:
                    href = candidate

            except Exception:
                pass

        if href and href.startswith("/"):
            href = "https://www.reddit.com" + href

        timestamp = ""

        time_element = notification.locator("time").first

        if time_element.count():
            try:
                timestamp = (
                    time_element.get_attribute("datetime") or time_element.inner_text().strip()
                )
            except Exception:
                pass

        username = ""

        user_link = notification.locator("a[href*='/user/'], a[href*='/u/']").first

        if user_link.count():
            try:
                username = user_link.inner_text().strip()
            except Exception:
                pass

        results.append({"text": text, "username": username, "timestamp": timestamp, "href": href})

    return results
