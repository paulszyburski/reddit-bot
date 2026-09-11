import time
from urllib.parse import urljoin
from selenium.common.exceptions import TimeoutException
from reddit.browser import find_all, text_of, wait_element
import hashlib
import json


def notification_state_key(post, our_username, post_href):
    """Identify incoming thread content, excluding our replies and volatile UI data."""
    incoming = []

    def collect(comments):
        for comment in comments:
            if not comment.get("isOurs") and (
                (comment.get("username") or "").casefold() != our_username.casefold()
            ):
                incoming.append({
                    "id": comment.get("id"),
                    "username": comment.get("username"),
                    "content": comment.get("content"),
                })
            collect(comment.get("replies", []))

    collect(post.get("comments", []))
    # Sorting prevents Reddit's comment ranking from creating a new event.
    comments = sorted(json.dumps(item, sort_keys=True) for item in incoming)
    state = json.dumps({
        "postHref": post_href.rstrip("/"),
        "ourUsername": our_username.casefold(),
        "comments": comments,
    }, sort_keys=True)
    return "thread-v1:" + hashlib.sha256(state.encode("utf-8")).hexdigest()


def mark_notification_handled(path, key):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(key + "\n")


def scrape_notifications(page, max_scrolls=5):
    """Open Reddit notifications and return visible notification metadata."""
    page.get("https://www.reddit.com/notifications")
    try:
        wait_element(page, "notification-item", visible_only=False)
    except TimeoutException:
        pass
    previous_count = 0
    for _ in range(max_scrolls):
        current_count = len(find_all(page, "notification-item"))
        if current_count == previous_count and current_count > 0:
            break
        previous_count = current_count
        page.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)

    results = []
    for notification in find_all(page, "notification-item"):
        links = [link.get_attribute("href") for link in find_all(notification, "a[href]")]
        links = [link for link in links if link]
        href = next((link for link in links if "/comments/" in link), links[0] if links else "")
        times = find_all(notification, "time")
        timestamp = (times[0].get_attribute("datetime") or times[0].text.strip()) if times else ""
        results.append({
            "text": notification.text.strip(),
            "username": text_of(notification, "a[href*='/user/'], a[href*='/u/']"),
            "timestamp": timestamp,
            "href": urljoin("https://www.reddit.com", href) if href else "",
        })
    return results
