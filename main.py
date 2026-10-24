import fcntl
import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from AI.chatgpt import generate_selection_response
from AI.prompts import select_post
from reddit.conversations.conversations import (
    ONGOING_PATH,
    PLANNED_PATH,
    _load_json,
    execute_conversations,
    handle_conversation_reply,
    plan_conversations,
)
from reddit.conversations.notifications import scrape_notifications
from reddit.conversations.posting_policy import posting_limit_reason
from reddit.login import login
from reddit.posts import scrape_post, scrape_posts

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
APPS_PATH = DATA_DIR / "apps" / "apps.json"
USERNAME = os.getenv("REDDIT_USERNAME")

COMMUNITIES = [
    "https://www.reddit.com/r/AndroidClosedTesting/",
    "https://www.reddit.com/r/TestersCommunity/",
    "https://www.reddit.com/r/AndroidAppTesters/",
    "https://www.reddit.com/r/AndroidTesting/",
    "https://www.reddit.com/r/TestMyApp/",
]


def load_apps():
    with APPS_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def save_posts(posts):
    now = datetime.now()
    folder = DATA_DIR / now.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"best_posts_{now.strftime('%H-%M-%S')}.json"
    with path.open("w", encoding="utf-8") as file:
        json.dump(posts, file, ensure_ascii=False, indent=4)
    print(f"\nSaved posts to: {path}")
    return str(path)


def excluded_post_urls():
    contacted_path = DATA_DIR / "contacted_posts.txt"
    contacted = set(contacted_path.read_text().splitlines()) if contacted_path.exists() else set()
    contacted.update(
        item["postHref"]
        for item in _load_json(PLANNED_PATH, [])
        if item.get("postHref") and item.get("action") in {"reply", "comment"}
    )
    return contacted


def find_posts(page, excluded):
    selected = []
    for community in COMMUNITIES:
        page.goto(community)
        time.sleep(1)
        posts = scrape_posts(page)
        best_post = select_post(posts, excluded, generate_selection_response)
        if best_post is None:
            print("No eligible post in this community.")
            continue
        excluded.add(best_post)
        print(f"Selected post: {best_post}")
        page.goto(best_post)
        selected.append(scrape_post(page))
    return selected


def run_bot():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            login(page)
            time.sleep(2)

            for notification in scrape_notifications(page):
                href = notification.get("href", "")
                if "/comments/" in href:
                    handle_conversation_reply(page, href)

            execute_conversations(page)

            for app in load_apps():
                history = _load_json(ONGOING_PATH, [])
                reason = posting_limit_reason(history, USERNAME, new_conversation=True)
                if reason:
                    print(f"Skipping new outreach: {reason}")
                    break

                posts = find_posts(page, excluded_post_urls())
                source_path = save_posts(posts)
                planned = plan_conversations(source_path, USERNAME, app)
                execute_conversations(page, planned)
        finally:
            browser.close()


def main():
    DATA_DIR.mkdir(exist_ok=True)
    with (DATA_DIR / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another bot run is active; skipping this run.")
            return
        run_bot()


if __name__ == "__main__":
    main()
