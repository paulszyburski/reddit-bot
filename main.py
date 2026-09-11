from reddit.browser import create_driver
from dotenv import load_dotenv
from datetime import datetime

import os
import time
import json

from reddit.login import *
from reddit.search import *
from reddit.posts import *
from reddit.conversations.conversations import *
from reddit.conversations.notifications import *
from AI.chatgpt import *

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

with open("data/contacted_posts.txt", "r") as file:
    contacted_posts = file.read()

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

def main():
    page = create_driver()
    try:
        login(page)

        time.sleep(2)

        best_posts = []
        for app in apps:
            for community in communities:

                page.get(community)

                time.sleep(1)

                posts = scrape_posts(page)

                print("\n\nChatGPT:")

                best_post = generate_response(
                    f"""
    Given these Reddit posts:

    {posts}

    Choose exactly ONE post that gives me the best chance of finding Android testers for my own app by joining the discussion and replying to people there.

    you CANNOT pick the post that has one of these hrefs:

    {contacted_posts}

    Prioritize posts where:

    * the author explicitly says things like "I will test your app", "will test back", "test for test", "test 4 test", "happy to test yours", or similar;

    * commenters are actively exchanging app tests with each other;

    * the post is about Android testing, Google Play closed testing, beta testing, or finding testers;

    * there are multiple active commenters who may also be potential testers;

    * people are willing to stay enrolled, install apps, or reciprocate testing.

    Avoid posts where:

    * the author only wants feedback for their own app and does not offer reciprocal testing;

    * the post is mainly about iOS, TestFlight, websites, SaaS, or non-Android products;

    * the author says they cannot test Android apps;

    * links are broken or the discussion is inactive;

    * there is little or no evidence that I could recruit testers from the thread.

    Evaluate the title, description, AND comments, not just the title.

    Return ONLY the href of the single best post.

    Do not explain your choice.

    Do not add markdown.

    Do not add quotes.

    Do not output anything except the href.
    """
                )

                # Remove accidental whitespace/newlines

                best_post = best_post.strip()

                print(best_post)

                page.get(best_post)

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

        notifications = scrape_notifications(page)

        for notification in notifications:
            href = notification.get("href", "")

            if "/comments/" not in href:
                continue

            

            handle_conversation_reply(page, href)
            
    finally:
        page.quit()

if __name__ == "__main__":

    main()



