import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from reddit.conversations.notifications import notification_state_key, mark_notification_handled
from reddit.posts import scrape_post
from reddit.conversations.posting_policy import (
    posting_limit_reason,
    outreach_reason,
    eligible_reply_ids,
)
from AI.chatgpt import generate_response
from AI.prompts import planning_prompt, follow_up_prompt, post_key
from reddit.conversations.utils import (
    _find_post,
    _find_comment_path,
    _find_reddit_comment,
    _post_reply,
    _post_top_level_comment,
    _add_contacted_post,
    _comment_permalink,
    _append_our_message_to_thread,
    _update_existing_conversation,
)

PLANNED_PATH = Path("data/planned_conversations.json")
ONGOING_PATH = Path("data/ongoing_conversations.json")
CONTACTED_PATH = Path("data/contacted_posts.txt")
CONTACTED_NOTIFICATIONS_PATH = Path("data/contacted_notifications.txt")


def _load_json(path, default=None):
    if default is None:
        default = []

    path = Path(path)
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

    temp_path.replace(path)


def _parse_decision(response):
    try:
        decision = json.loads(response) if isinstance(response, str) else response
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(decision, dict):
        return None
    if decision.get("action") not in ("none", "reply", "comment"):
        return None
    if decision["action"] != "none":
        if not isinstance(decision.get("content"), str) or not decision["content"].strip():
            return None
    return decision


def _valid_target(decision, post, our_username, expected_username=None):
    if decision.get("action") == "none":
        return True
    if decision.get("action") == "reply":
        reply_to = decision.get("replyTo")
        if not isinstance(reply_to, str) or not reply_to:
            return False
        path = _find_comment_path(post.get("comments", []), reply_to)
        if not path:
            return False
        author = path[-1].get("username")
    else:
        author = post.get("username")
    if not isinstance(author, str) or not author:
        return False
    if author.casefold() in {our_username.casefold(), "automoderator", "[deleted]", "[removed]"}:
        return False
    if decision.get("targetUsername") != author:
        return False
    return not expected_username or author.casefold() == expected_username.casefold()


def plan_conversations(file_path, our_username, app):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    reason = posting_limit_reason(_load_json(ONGOING_PATH, []), our_username, new_conversation=True)
    if reason:
        print(f"Skipping outreach planning: {reason}")
        return []

    contacted_posts = set()
    if CONTACTED_PATH.exists():
        with open(CONTACTED_PATH, "r", encoding="utf-8") as file:
            contacted_posts = {line.strip() for line in file if line.strip()}

    decisions = []
    seen_posts = {post_key(href) for href in contacted_posts}
    seen_posts.update(
        post_key(item["postHref"])
        for item in _load_json(PLANNED_PATH, [])
        if item.get("postHref") and item.get("action") in ("reply", "comment")
    )

    for post in data:
        href = post.get("href")
        if not href or post_key(href) in seen_posts:
            continue
        seen_posts.add(post_key(href))

        now = datetime.now(timezone.utc).isoformat()

        prompt = planning_prompt(post, our_username, app)

        response = generate_response(prompt)

        decision = _parse_decision(response)
        if decision is None or not _valid_target(decision, post, our_username):
            print("Invalid AI decision or target; skipping post.")
            continue
        decision["lastChecked"] = now
        decision["id"] = str(uuid.uuid4())
        decision["postHref"] = post.get("href")
        decision["community"] = post.get("community")
        decision["postUsername"] = post.get("username")
        decision["ourUsername"] = our_username
        decision["sourcePath"] = file_path
        decision["appName"] = app["name"]
        decisions.append(decision)

    planned = _load_json(PLANNED_PATH, [])
    planned.extend(decisions)
    _save_json(PLANNED_PATH, planned)

    print(f"Added {len(decisions)} conversations to {PLANNED_PATH}")
    return decisions


def execute_conversations(page, conversations=None):
    planned = _load_json(PLANNED_PATH, [])
    queue = planned.copy() if conversations is None else conversations
    ongoing = _load_json(ONGOING_PATH, [])

    already_executed = {
        conversation.get("id") for conversation in ongoing if conversation.get("id")
    }

    def add_message_to_thread(post, action, reply_to, message):
        if action == "comment":
            post.setdefault("comments", []).append(message)
            return True

        if action == "reply":

            def find_and_add(comments):
                for comment in comments:
                    if comment.get("id") == reply_to:
                        comment.setdefault("replies", []).append(message)
                        return True

                    if find_and_add(comment.get("replies", [])):
                        return True

                return False

            return find_and_add(post.get("comments", []))

        return False

    for conversation in queue:
        conversation_id = conversation.get("id")
        action = conversation.get("action")
        href = conversation.get("postHref")
        content = conversation.get("content", "")
        source_path = conversation.get("sourcePath")
        reply_to = conversation.get("replyTo")
        target_username = conversation.get("targetUsername")

        print()
        print("=" * 70)
        print(f"Conversation: {conversation_id}")
        print(f"Action:       {action}")
        print(f"Post:         {href}")
        print("=" * 70)

        if conversation_id in already_executed:
            print("Already executed. Skipping.")
            continue

        if action == "none":
            print("No action required.")
            planned = [item for item in planned if item.get("id") != conversation_id]
            _save_json(PLANNED_PATH, planned)
            continue

        if action not in ("reply", "comment"):
            print(f"Unknown action: {action}")
            continue

        if not href:
            print("Missing postHref.")
            continue

        if not content:
            print("Missing content.")
            continue

        if action == "reply" and not reply_to:
            print("Reply action has no replyTo.")
            continue

        if not source_path:
            print("Missing sourcePath.")
            continue

        source_data = _load_json(source_path, [])
        source_post = _find_post(source_data, href)

        if source_post is None:
            print(f"Could not find post in {source_path}")
            continue

        if action == "reply":
            target_comment = _find_comment_path(source_post.get("comments", []), reply_to)

            if target_comment is None:
                print(f"Could not find {reply_to} in source JSON.")
                continue

        if not _valid_target(conversation, source_post, conversation.get("ourUsername", "")):
            print("Invalid saved reply target. Skipping.")
            continue

        reason = outreach_reason(ongoing, conversation) or posting_limit_reason(
            ongoing, conversation.get("ourUsername", ""), new_conversation=True
        )
        if reason:
            print(f"Outreach skipped: {reason}")
            continue

        if action == "reply":
            destination = _comment_permalink(href, reply_to)
            print("Opening comment permalink:")
        else:
            destination = href
            print("Opening post:")

        print(destination)

        try:
            page.goto(destination, wait_until="domcontentloaded")

            page.locator("shreddit-post").first.wait_for(state="attached", timeout=15000)

            page.wait_for_timeout(1000)

            if action == "reply":
                try:
                    page.locator("shreddit-comment").first.wait_for(state="attached", timeout=10000)
                except Exception:
                    pass

            elif action == "comment":
                try:
                    page.locator(
                        'faceplate-textarea-input[data-testid="trigger-button"]'
                    ).first.wait_for(state="attached", timeout=10000)
                except Exception:
                    pass

        except Exception as e:
            print(f"Failed opening Reddit: {e}")
            continue

        try:
            if action == "reply":
                print(f"Replying to {reply_to} ({target_username})")

                if _find_reddit_comment(page, reply_to) is None:
                    print("Comment not loaded on permalink. Trying main post...")
                    page.goto(href, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)

                _post_reply(page, reply_to, content)

            else:
                print(f"Writing top-level comment to {target_username}")
                _post_top_level_comment(page, content)

            page.wait_for_timeout(1200)

        except Exception as e:
            print()
            print(f"FAILED conversation {conversation_id}")
            print(f"Reason: {e}")
            print()
            continue

        executed_at = datetime.now(timezone.utc).isoformat()

        sent_message = {
            "id": None,
            "username": conversation.get("ourUsername", "OUR_ACCOUNT"),
            "content": content,
            "replies": [],
            "isOurs": True,
            "sentAt": executed_at,
        }

        added_to_thread = add_message_to_thread(source_post, action, reply_to, sent_message)

        if not added_to_thread:
            print("WARNING: Message was sent, but could not " "be inserted into saved thread.")

        ongoing_conversation = {
            **conversation,
            "conversationStatus": "ACTIVE",
            "executionStatus": "EXECUTED",
            "executedAt": executed_at,
            "youAreTalkingTo": target_username,
            "thread": source_post,
            "ourMessages": [
                {
                    "action": action,
                    "replyTo": reply_to,
                    "targetUsername": target_username,
                    "content": content,
                    "sentAt": executed_at,
                }
            ],
        }

        ongoing.append(ongoing_conversation)
        _save_json(ONGOING_PATH, ongoing)

        _add_contacted_post(href)

        planned = [item for item in planned if item.get("id") != conversation_id]

        _save_json(PLANNED_PATH, planned)

        already_executed.add(conversation_id)

        print()
        print("Successfully executed.")
        print()


def handle_conversation_reply(page, href):
    ongoing_conversations = _load_json(ONGOING_PATH, [])

    conversations = [
        item
        for item in ongoing_conversations
        if item.get("postHref") and post_key(href) == post_key(item["postHref"])
    ]

    if not conversations:
        print("Conversation not found.")
        return

    if len(conversations) > 1:
        print("Many conversations under 1 post. Fix that!")
        return

    conversation = conversations[0]

    app_name = conversation["appName"]
    app = next(
        (item for item in _load_json("data/apps/apps.json", []) if item.get("name") == app_name),
        {"name": app_name},
    )

    page.goto(conversation["postHref"], wait_until="domcontentloaded")
    post = scrape_post(page)
    notification_key = notification_state_key(
        post, conversation["ourUsername"], conversation["postHref"]
    )
    handled = set()
    if CONTACTED_NOTIFICATIONS_PATH.exists():
        handled = set(CONTACTED_NOTIFICATIONS_PATH.read_text(encoding="utf-8").splitlines())
    if notification_key in handled:
        print(f"Incoming thread content already handled: {href}")
        return

    eligible_ids = eligible_reply_ids(conversation, post)
    if not eligible_ids:
        print("Waiting for a new reply to our latest message.")
        return
    reason = posting_limit_reason(ongoing_conversations, conversation["ourUsername"])
    if reason:
        print(f"Follow-up deferred: {reason}")
        return

    conversation["thread"] = post

    _save_json(ONGOING_PATH, ongoing_conversations)

    prompt = follow_up_prompt(conversation, app)

    response = generate_response(prompt)

    decision = _parse_decision(response)
    if decision is None or not _valid_target(
        decision, post, conversation["ourUsername"], conversation.get("youAreTalkingTo")
    ):
        print("Invalid AI decision or target; notification remains retryable.")
        return

    print()
    print("DECISION:")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print()

    action = decision.get("action")
    content = decision.get("content", "")
    reply_to = decision.get("replyTo")
    target_username = decision.get("targetUsername")

    conversation["lastChecked"] = decision.get(
        "lastChecked", datetime.now(timezone.utc).isoformat()
    )

    conversation["reason"] = decision.get("reason", "")

    conversation["confidence"] = decision.get("confidence", 0.0)

    if action == "none":
        print("No action required.")

        conversation["conversationStatus"] = "ACTIVE"
        conversation["executionStatus"] = "WAITING_FOR_REPLY"

        _save_json(ONGOING_PATH, ongoing_conversations)

        mark_notification_handled(CONTACTED_NOTIFICATIONS_PATH, notification_key)

        return

    if action != "reply" or reply_to not in eligible_ids:
        print("Follow-up must answer a new reply to our latest message.")
        return
    previous_contents = {
        " ".join(message.get("content", "").split()).casefold()
        for message in conversation.get("ourMessages", [])
    }
    if " ".join(content.split()).casefold() in previous_contents:
        print("Duplicate follow-up text suppressed.")
        return

    if not content:
        print("Missing content.")
        return

    if action == "reply" and not reply_to:
        print("Reply action has no replyTo.")
        return

    post_href = conversation.get("postHref")

    if not post_href:
        print("Conversation has no postHref.")
        return

    if action == "reply":
        destination = _comment_permalink(post_href, reply_to)

        print("Opening comment permalink:")
        print(destination)

    else:
        destination = post_href

        print("Opening post:")
        print(destination)

    try:
        page.goto(destination, wait_until="domcontentloaded")

        page.locator("shreddit-post").first.wait_for(state="attached", timeout=15000)

        page.wait_for_timeout(1000)

        if action == "reply":
            try:
                page.locator("shreddit-comment").first.wait_for(state="attached", timeout=10000)
            except Exception:
                pass

        elif action == "comment":
            try:
                page.locator(
                    'faceplate-textarea-input[data-testid="trigger-button"]'
                ).first.wait_for(state="attached", timeout=10000)
            except Exception:
                pass

    except Exception as e:
        print(f"Failed opening Reddit: {e}")
        return

    try:
        if action == "reply":
            print(f"Replying to {reply_to} " f"({target_username})")

            if _find_reddit_comment(page, reply_to) is None:
                print("Comment not loaded on permalink. " "Trying main post...")

                page.goto(post_href, wait_until="domcontentloaded")

                page.wait_for_timeout(1500)

            _post_reply(page, reply_to, content)

        else:
            print(f"Writing top-level comment " f"to {target_username}")

            _post_top_level_comment(page, content)

        page.wait_for_timeout(1200)

    except Exception as e:
        print()
        print("FAILED sending conversation reply")
        print(f"Reason: {e}")
        print()
        return

    executed_at = datetime.now(timezone.utc).isoformat()

    sent_message = {
        "id": None,
        "username": conversation.get("ourUsername", "OUR_ACCOUNT"),
        "content": content,
        "replies": [],
        "isOurs": True,
        "sentAt": executed_at,
    }

    def add_message_to_thread(comments):
        if action == "comment":
            comments.append(sent_message)
            return True

        for comment in comments:
            if comment.get("id") == reply_to:
                comment.setdefault("replies", []).append(sent_message)

                return True

            if add_message_to_thread(comment.get("replies", [])):
                return True

        return False

    added_to_thread = add_message_to_thread(conversation["thread"].setdefault("comments", []))

    if not added_to_thread:
        print("WARNING: Message was sent, but could " "not be inserted into saved thread.")

    conversation["action"] = action
    conversation["replyTo"] = reply_to
    conversation["targetUsername"] = target_username
    conversation["content"] = content

    conversation["conversationStatus"] = "ACTIVE"
    conversation["executionStatus"] = "EXECUTED"
    conversation["executedAt"] = executed_at

    conversation["youAreTalkingTo"] = target_username

    conversation.setdefault("ourMessages", []).append(
        {
            "action": action,
            "replyTo": reply_to,
            "targetUsername": target_username,
            "content": content,
            "sentAt": executed_at,
        }
    )

    _save_json(ONGOING_PATH, ongoing_conversations)

    mark_notification_handled(CONTACTED_NOTIFICATIONS_PATH, notification_key)

    print()
    print("Conversation reply successfully executed.")
    print()
