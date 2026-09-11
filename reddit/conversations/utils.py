from selenium.webdriver.support.ui import WebDriverWait
from reddit.browser import find_all, visible, wait_element, driver_for, fill_editor, click_element
import json
import uuid
import re

from datetime import datetime, timezone
from pathlib import Path

from AI.chatgpt import *

PLANNED_PATH = Path("data/planned_conversations.json")
ONGOING_PATH = Path("data/ongoing_conversations.json")
CONTACTED_PATH = Path("data/contacted_posts.txt")


# ============================================================
# SOURCE DATA HELPERS
# ============================================================

def _find_post(source_data, href):

    if isinstance(source_data, dict):

        if source_data.get("href") == href:
            return source_data

        return None

    if isinstance(source_data, list):

        for post in source_data:

            if post.get("href") == href:
                return post

    return None


def _find_comment_path(
    comments,
    target_id,
    path=None
):

    if path is None:
        path = []

    for comment in comments:

        current = {
            "id": comment.get("id"),
            "username": comment.get("username"),
            "content": comment.get(
                "content",
                ""
            )
        }

        new_path = path + [current]

        if comment.get("id") == target_id:
            return new_path

        result = _find_comment_path(
            comment.get(
                "replies",
                []
            ),
            target_id,
            new_path
        )

        if result:
            return result

    return None


REPLY_EDITOR_SELECTOR = (
    '[contenteditable="true"][role="textbox"][data-lexical-editor="true"], '
    'textarea:not([disabled]), [role="textbox"]:not([aria-disabled="true"])'
)


def _find_reddit_comment(page, comment_id):
    clean_id = comment_id.removeprefix("t1_")
    for comment in find_all(page, "shreddit-comment"):
        if any((comment.get_attribute(attr) or "").removeprefix("t1_") == clean_id
               for attr in ("thingid", "id")):
            return comment
    return None


def _find_composer_scope(editor):
    # Walk through shadow hosts as well as ordinary parents.
    return driver_for(editor).execute_script('''
        let node = arguments[0], composer = null;
        while (node) {
            if (node.matches && node.matches('faceplate-form, form')) return node;
            if (!composer && node.matches && node.matches('shreddit-composer')) composer = node;
            node = node.parentElement || node.getRootNode().host;
        }
        return composer;
    ''', editor)


def _submit_editor(page, editor):
    scope = _find_composer_scope(editor)
    if scope is None:
        raise RuntimeError("Could not find the form containing the reply editor.")
    def submit_button(_):
        buttons = visible(find_all(scope, 'button, [role="button"]'))
        for button in buttons:
            name = (button.accessible_name or button.text).strip().casefold()
            if button.is_enabled() and (button.get_attribute("type") == "submit" or name in ("reply", "comment")):
                return button
        return False
    click_element(WebDriverWait(page, 10).until(submit_button))


def _post_reply(page, reply_to, content):
    comment = _find_reddit_comment(page, reply_to)
    if comment is None:
        raise RuntimeError(f"Could not find Reddit comment {reply_to}")
    old_editors = {element.id for element in visible(find_all(page, REPLY_EDITOR_SELECTOR))}

    def reply_button(_):
        for button in visible(find_all(comment, 'button, [role="button"]')):
            owner = page.execute_script('''
                let node = arguments[0];
                while (node) {
                    if (node.matches && node.matches('shreddit-comment')) return node;
                    node = node.parentElement || node.getRootNode().host;
                }
                return null;
            ''', button)
            if owner != comment:
                continue
            name = (button.accessible_name or button.text).strip().casefold()
            if (name == "reply" or "reply" in (button.get_attribute("aria-label") or "").casefold()) and button.is_enabled():
                return button
        return False
    click_element(WebDriverWait(page, 10).until(reply_button))

    def new_editor(_):
        # Use the newly opened editor, never an unrelated existing textbox.
        for scope in (comment, page):
            editors = [element for element in visible(find_all(scope, REPLY_EDITOR_SELECTOR))
                       if element.id not in old_editors]
            if editors:
                return editors[-1]
        return False
    editor = WebDriverWait(page, 10).until(new_editor)
    fill_editor(editor, content)
    _submit_editor(page, editor)


def _post_top_level_comment(page, content):
    trigger = wait_element(page, 'faceplate-textarea-input[data-testid="trigger-button"]')
    # The containing tracker handles opening Reddit's collapsed composer.
    tracker = page.execute_script(
        "return arguments[0].closest('faceplate-tracker') || arguments[0];", trigger)
    click_element(tracker)

    def composer(_):
        for form in reversed(find_all(page, 'faceplate-form[action*="/create-comment"]')):
            editors = visible(find_all(form, 'div[slot="rte"][name="body"][contenteditable="true"][data-lexical-editor="true"]'))
            if editors:
                return form, editors[0]
        return False
    form, editor = WebDriverWait(page, 10).until(composer)
    fill_editor(editor, content)
    submit = wait_element(form, '#comment-composer-submit-button')
    click_element(submit)


# ============================================================
# CONTACTED POSTS
# ============================================================

def _add_contacted_post(href):

    CONTACTED_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    existing = set()

    if CONTACTED_PATH.exists():

        with open(
            CONTACTED_PATH,
            "r",
            encoding="utf-8"
        ) as file:

            existing = {
                line.strip()
                for line in file
                if line.strip()
            }

    if href not in existing:

        with open(
            CONTACTED_PATH,
            "a",
            encoding="utf-8"
        ) as file:

            file.write(
                href + "\n"
            )


# ============================================================
# COMMENT PERMALINK
# ============================================================

def _comment_permalink(
    post_href,
    comment_id
):

    clean_id = comment_id

    if clean_id.startswith(
        "t1_"
    ):

        clean_id = clean_id[3:]

    return (
        post_href.rstrip("/")
        + "/"
        + clean_id
        + "/"
    )




def _add_our_message_to_thread(source_post, action, reply_to, message):
    if action == "comment":
        source_post.setdefault("comments", []).append(message)
        return True

    if action == "reply":
        def add_reply(comments):
            for comment in comments:
                if comment.get("id") == reply_to:
                    comment.setdefault("replies", []).append(message)
                    return True

                if add_reply(comment.get("replies", [])):
                    return True

            return False

        return add_reply(source_post.get("comments", []))

    return False



def _append_our_message_to_thread(comments, decision, sent_at):
    """
    Adds our newly-sent message to the locally stored thread so ONGOING_PATH
    immediately reflects what we just posted, even before the next scrape.
    """

    message = {
        "id": None,
        "username": decision["targetUsername"],  # overwritten below
        "content": decision["content"],
        "replies": [],
        "isOurs": True,
        "sentAt": sent_at,
    }

    # This should be OUR username, not target username.
    # We set it when calling this helper via decision["_ourUsername"].
    message["username"] = decision["_ourUsername"]

    if decision["action"] == "comment":
        comments.append(message)
        return True

    if decision["action"] != "reply":
        return False

    reply_to = decision["replyTo"]

    def find_and_append(items):
        for comment in items:
            if comment.get("id") == reply_to:
                comment.setdefault("replies", []).append(message)
                return True

            if find_and_append(comment.get("replies", [])):
                return True

        return False

    return find_and_append(comments)



def _update_existing_conversation(
    ongoing_conversations,
    conversation,
    decision,
    post,
    executed=False,
):
    now = datetime.now(timezone.utc).isoformat()

    # Always refresh the Reddit thread with the newest scrape.
    conversation["thread"]["comments"] = post["comments"]

    # Store the latest AI decision.
    conversation["action"] = decision["action"]
    conversation["replyTo"] = decision["replyTo"]
    conversation["targetUsername"] = decision["targetUsername"]
    conversation["content"] = decision["content"]
    conversation["conversationStatus"] = decision["conversationStatus"]
    conversation["lastChecked"] = decision.get("lastChecked", now)
    conversation["reason"] = decision.get("reason", "")
    conversation["confidence"] = decision.get("confidence", 0.0)

    # --------------------------------------------------
    # NO ACTION
    # --------------------------------------------------

    if decision["action"] == "none":
        conversation["executionStatus"] = "NO_ACTION"

        _save_json(ONGOING_PATH, ongoing_conversations)
        return

    # --------------------------------------------------
    # MESSAGE WAS ACTUALLY SENT
    # --------------------------------------------------

    if executed:
        conversation["executionStatus"] = "EXECUTED"
        conversation["executedAt"] = now

        # Usually we're continuing with the same person.
        if decision.get("targetUsername"):
            conversation["youAreTalkingTo"] = decision["targetUsername"]

        conversation.setdefault("ourMessages", []).append({
            "action": decision["action"],
            "replyTo": decision["replyTo"],
            "targetUsername": decision["targetUsername"],
            "content": decision["content"],
            "sentAt": now,
        })

        # Also represent our new message inside thread.comments.
        thread_decision = dict(decision)
        thread_decision["_ourUsername"] = conversation["ourUsername"]

        added = _append_our_message_to_thread(
            conversation["thread"]["comments"],
            thread_decision,
            now,
        )

        if not added:
            print(
                f'Warning: could not find replyTo '
                f'{decision["replyTo"]} in stored thread.'
            )

    else:
        conversation["executionStatus"] = "PENDING"

    _save_json(ONGOING_PATH, ongoing_conversations)



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
