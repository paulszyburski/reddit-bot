from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from datetime import datetime

import os
import fcntl
import time
import json
from pathlib import Path

from reddit.login import *
from reddit.search import *
from reddit.posts import *
from reddit.conversations.conversations import *
from reddit.conversations.conversations import _load_json
from reddit.conversations.posting_policy import posting_limit_reason
from reddit.conversations.notifications import *
from AI.chatgpt import *
from AI.prompts import select_post

load_dotenv()

USERNAME = os.getenv("REDDIT_USERNAME")

communities = [
    "https://www.reddit.com/r/AndroidClosedTesting/",
    "https://www.reddit.com/r/TestersCommunity/",
    "https://www.reddit.com/r/AndroidAppTesters/",
    "https://www.reddit.com/r/AndroidTesting/",
    "https://www.reddit.com/r/TestMyApp/",
]

with open("data/apps/apps.json", "r") as file:
    apps = json.load(file)


def save_posts(posts):

    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")

    folder_path = os.path.join("data", date_folder)

    os.makedirs(folder_path, exist_ok=True)

    filename = f"best_posts_{now.strftime('%H-%M-%S')}.json"

    file_path = os.path.join(folder_path, filename)

    with open(file_path, "w", encoding="utf-8") as file:

        json.dump(posts, file, ensure_ascii=False, indent=4)

    print(f"\nSaved posts to: {file_path}")

    return file_path

def _run_main():
    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        login(page)

        time.sleep(2)

        notifications = scrape_notifications(page)

        for notification in notifications:
            href = notification.get("href", "")

            if "/comments/" not in href:
                continue



            handle_conversation_reply(page, href)

        # Resume deferred plans before paying to generate more outreach.
        execute_conversations(page)

        for app in apps:
            reason = posting_limit_reason(_load_json(ONGOING_PATH, []), USERNAME, new_conversation=True)
            if reason:
                print(f"Skipping new outreach: {reason}")
                break
            best_posts = []
            contacted_path = Path("data/contacted_posts.txt")
            excluded_posts = set(contacted_path.read_text().splitlines()) if contacted_path.exists() else set()
            excluded_posts.update(
                item["postHref"] for item in _load_json(PLANNED_PATH, [])
                if item.get("postHref") and item.get("action") in ("reply", "comment")
            )
            for community in communities:

                page.goto(community)

                time.sleep(1)

                posts = scrape_posts(page)

                print("\n\nChatGPT:")

                best_post = select_post(posts, excluded_posts, generate_selection_response)
                if best_post is None:
                    print("No eligible post in this community.")
                    continue
                excluded_posts.add(best_post)

                print(best_post)

                page.goto(best_post)

                post_info = scrape_post(page)

                best_posts.append(post_info)

            # -------------------------
            # Save everything
            # -------------------------

            file_path = save_posts(best_posts)

            print("\nFinal posts:")

            print(best_posts)

            print("\nPlanning conversations!")

            planned_convos = plan_conversations(
                file_path, USERNAME, app
            )

            print(planned_convos)

            print("executing")

            execute_conversations(page, planned_convos)

        browser.close()

def main():
    # One process at a time so overlapping scheduled runs cannot bypass limits.
    Path("data").mkdir(exist_ok=True)
    with open("data/run.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another bot run is active; skipping this run.")
            return
        _run_main()


if __name__ == "__main__":

    #main()
    pass

