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


# ============================================================
# DEBUG HELPERS
# ============================================================

def _debug_buttons(
    scope,
    title="VISIBLE BUTTONS"
):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)

    locator = scope.locator(
        "button, "
        "[role='button'], "
        "faceplate-tracker, "
        "faceplate-button"
    )

    for i in range(
        locator.count()
    ):

        element = locator.nth(i)

        try:

            visible = element.is_visible()

            text = (
                element.inner_text(
                    timeout=500
                )
                or ""
            ).strip()

            aria = (
                element.get_attribute(
                    "aria-label"
                )
            )

            element_id = (
                element.get_attribute(
                    "id"
                )
            )

            source = (
                element.get_attribute(
                    "source"
                )
            )

            tag = element.evaluate(
                "(el) => el.tagName.toLowerCase()"
            )

            print(
                i,
                f"TAG={tag}",
                f"VISIBLE={visible}",
                f"ID={repr(element_id)}",
                f"TEXT={repr(text)}",
                f"ARIA={repr(aria)}",
                f"SOURCE={repr(source)}"
            )

        except Exception:
            pass

    print("=" * 70)
    print()


def _debug_editors(scope):

    print()
    print("=" * 70)
    print("EDITORS")
    print("=" * 70)

    selectors = [
        "textarea",
        '[contenteditable="true"]',
        '[role="textbox"]',
        '[data-lexical-editor="true"]',
        "shreddit-composer",
        "faceplate-textarea-input",
        "faceplate-form"
    ]

    for selector in selectors:

        loc = scope.locator(selector)

        print(
            selector,
            "count=",
            loc.count()
        )

        for i in range(
            loc.count()
        ):

            try:

                element = loc.nth(i)

                print(
                    " ",
                    i,
                    "visible=",
                    element.is_visible(),
                    "id=",
                    repr(
                        element.get_attribute(
                            "id"
                        )
                    ),
                    "name=",
                    repr(
                        element.get_attribute(
                            "name"
                        )
                    ),
                    "disabled=",
                    repr(
                        element.get_attribute(
                            "disabled"
                        )
                    )
                )

            except Exception:
                pass

    print("=" * 70)


# ============================================================
# GENERIC PLAYWRIGHT HELPERS
# ============================================================

def _visible_elements(locator):

    result = []

    for i in range(
        locator.count()
    ):

        element = locator.nth(i)

        try:

            if element.is_visible():
                result.append(element)

        except Exception:
            pass

    return result


def _click_first(scope, selectors):

    for selector in selectors:

        locator = scope.locator(
            selector
        )

        for element in _visible_elements(
            locator
        ):

            try:
                element.scroll_into_view_if_needed()
            except Exception:
                pass

            try:

                element.click()

                return element

            except Exception:

                try:

                    element.click(
                        force=True
                    )

                    return element

                except Exception:
                    pass

    return None


# ============================================================
# REDDIT COMMENT FINDER
# ============================================================

def _find_reddit_comment(
    page,
    comment_id
):

    selectors = [
        f'shreddit-comment[thingid="{comment_id}"]',
        f'shreddit-comment[id="{comment_id}"]',
        f'shreddit-comment[data-fullname="{comment_id}"]',

        f'[thingid="{comment_id}"]',
        f'[data-thingid="{comment_id}"]',
        f'[data-fullname="{comment_id}"]',
        f'[id="{comment_id}"]',
    ]

    for selector in selectors:

        locator = page.locator(
            selector
        )

        if locator.count():

            comment = locator.first

            try:
                comment.scroll_into_view_if_needed()
            except Exception:
                pass

            return comment

    return None


# ============================================================
# REPLY EDITOR HELPERS
# ============================================================

REPLY_EDITOR_SELECTOR = (
    '[contenteditable="true"]'
    '[role="textbox"]'
    '[data-lexical-editor="true"], '
    'textarea:not([disabled]), '
    '[role="textbox"]:not([aria-disabled="true"])'
)


def _find_reply_editor(scope):

    locator = scope.locator(
        REPLY_EDITOR_SELECTOR
    )

    visible = _visible_elements(
        locator
    )

    if visible:
        return visible[-1]

    return None


def _find_new_reply_editor(
    page,
    old_count
):

    for _ in range(30):

        visible = _visible_elements(
            page.locator(
                REPLY_EDITOR_SELECTOR
            )
        )

        if len(visible) > old_count:
            return visible[-1]

        page.wait_for_timeout(
            100
        )

    visible = _visible_elements(
        page.locator(
            REPLY_EDITOR_SELECTOR
        )
    )

    if visible:
        return visible[-1]

    return None


def _editor_has_content(
    editor,
    content
):

    try:

        tag = editor.evaluate(
            "(el) => el.tagName.toLowerCase()"
        )

        if tag in (
            "textarea",
            "input"
        ):

            value = editor.input_value()

        else:

            value = editor.inner_text()

        return content.strip() in value.strip()

    except Exception:
        return False


def _fill_exact_editor(
    editor,
    content
):

    """
    IMPORTANT:

    We ONLY type into the Locator supplied here.

    There is intentionally NO:
        page.keyboard.insert_text(...)

    fallback.

    That prevents text accidentally going into Reddit Search.
    """

    editor.scroll_into_view_if_needed()

    editor.wait_for(
        state="visible",
        timeout=10000
    )

    editor.click()

    editor.fill(
        content
    )

    if not _editor_has_content(
        editor,
        content
    ):

        raise RuntimeError(
            "Editor was found, but Reddit "
            "did not accept the supplied text."
        )


# ============================================================
# REPLY BUTTON
# ============================================================

def _click_reply_button(comment):

    # --------------------------------------------------------
    # Accessibility selector
    # --------------------------------------------------------

    try:

        buttons = comment.get_by_role(
            "button",
            name=re.compile(
                r"^\s*reply\s*$",
                re.I
            )
        )

        for button in _visible_elements(
            buttons
        ):

            try:

                button.click()

                return True

            except Exception:

                try:

                    button.click(
                        force=True
                    )

                    return True

                except Exception:
                    pass

    except Exception:
        pass

    # --------------------------------------------------------
    # CSS fallbacks
    # --------------------------------------------------------

    selectors = [
        'button:has-text("Reply")',
        '[role="button"]:has-text("Reply")',

        'button[aria-label*="reply" i]',
        '[role="button"][aria-label*="reply" i]',

        'faceplate-tracker:has-text("Reply") button',
        'faceplate-tracker:has-text("Reply")'
    ]

    result = _click_first(
        comment,
        selectors
    )

    if result is not None:
        return True

    return False


# ============================================================
# FIND COMPOSER AROUND REPLY EDITOR
# ============================================================

def _find_composer_scope(editor):

    ancestors = [
        "xpath=ancestor::shreddit-composer[1]",
        "xpath=ancestor::faceplate-form[1]",
        "xpath=ancestor::form[1]"
    ]

    for xpath in ancestors:

        try:

            scope = editor.locator(
                xpath
            )

            if scope.count():
                return scope.first

        except Exception:
            pass

    return None


# ============================================================
# REPLY SUBMIT
# ============================================================

def _click_reply_submit(
    page,
    editor
):

    scope = _find_composer_scope(
        editor
    )

    if scope is not None:

        selectors = [
            'button[type="submit"]',
            'button:has-text("Reply")',
            'button:has-text("Comment")'
        ]

        for selector in selectors:

            buttons = scope.locator(
                selector
            )

            for button in _visible_elements(
                buttons
            ):

                try:

                    if button.is_enabled():

                        button.click()

                        return True

                except Exception:
                    pass

    # --------------------------------------------------------
    # Global fallback
    # --------------------------------------------------------

    buttons = page.get_by_role(
        "button",
        name=re.compile(
            r"^\s*(reply|comment)\s*$",
            re.I
        )
    )

    visible = []

    for button in _visible_elements(
        buttons
    ):

        try:

            if button.is_enabled():
                visible.append(button)

        except Exception:
            pass

    if visible:

        visible[-1].click()

        return True

    return False


# ============================================================
# POST REPLY
# ============================================================

def _post_reply(
    page,
    reply_to,
    content
):

    print(
        f"Looking for comment "
        f"{reply_to}..."
    )

    comment = _find_reddit_comment(
        page,
        reply_to
    )

    if comment is None:

        raise RuntimeError(
            f"Could not find Reddit "
            f"comment {reply_to}"
        )

    print("Found comment.")

    comment.scroll_into_view_if_needed()

    page.wait_for_timeout(
        300
    )

    old_editors = _visible_elements(
        page.locator(
            REPLY_EDITOR_SELECTOR
        )
    )

    old_count = len(
        old_editors
    )

    print(
        f"Editors before Reply click: "
        f"{old_count}"
    )

    if not _click_reply_button(
        comment
    ):

        _debug_buttons(
            comment,
            "COMMENT BUTTONS"
        )

        raise RuntimeError(
            f"Could not find Reply "
            f"button for {reply_to}"
        )

    print("Clicked Reply.")

    page.wait_for_timeout(
        400
    )

    # Prefer editor inside target comment.
    editor = _find_reply_editor(
        comment
    )

    if editor is None:

        editor = _find_new_reply_editor(
            page,
            old_count
        )

    if editor is None:

        _debug_editors(
            page
        )

        raise RuntimeError(
            "Reply button was clicked, "
            "but reply editor was not found."
        )

    print("Found reply editor.")

    _fill_exact_editor(
        editor,
        content
    )

    print("Filled reply.")

    page.wait_for_timeout(
        250
    )

    if not _click_reply_submit(
        page,
        editor
    ):

        _debug_buttons(
            page,
            "BUTTONS AFTER FILLING REPLY"
        )

        raise RuntimeError(
            "Reply text was entered, "
            "but submit button was not found."
        )

    print("Reply submitted.")


# ============================================================
# TOP LEVEL COMMENT
# ============================================================

def _find_top_level_trigger(page):

    """
    Reddit collapsed composer, before opening.

    We click the PARENT faceplate-tracker.

    Known Reddit variants:

    source="comment_composer"

    or:

    source="shreddit_comment_count_button"
    """

    selectors = [
        (
            'faceplate-tracker'
            '[source="comment_composer"]'
            ':has('
            'faceplate-textarea-input'
            '[data-testid="trigger-button"]'
            ')'
        ),

        (
            'faceplate-tracker'
            '[source="shreddit_comment_count_button"]'
            ':has('
            'faceplate-textarea-input'
            '[data-testid="trigger-button"]'
            ')'
        ),

        (
            'faceplate-tracker:has('
            'faceplate-textarea-input'
            '[data-testid="trigger-button"]'
            ')'
        )
    ]

    for selector in selectors:

        locator = page.locator(
            selector
        )

        for i in range(
            locator.count()
        ):

            trigger = locator.nth(i)

            try:

                if trigger.is_visible():
                    return trigger

            except Exception:
                pass

    # attached fallback
    for selector in selectors:

        locator = page.locator(
            selector
        )

        if locator.count():
            return locator.first

    return None


def _open_top_level_comment_box(page):

    print(
        "Looking for top-level comment trigger..."
    )

    trigger = _find_top_level_trigger(
        page
    )

    if trigger is None:

        _debug_editors(page)
        _debug_buttons(
            page,
            "PAGE ELEMENTS - COMMENT TRIGGER NOT FOUND"
        )

        raise RuntimeError(
            "Could not find Reddit "
            "top-level comment trigger."
        )

    print(
        "Found top-level comment trigger."
    )

    try:
        trigger.scroll_into_view_if_needed()
    except Exception:
        pass

    # --------------------------------------------------------
    # Before click, remember existing create-comment forms.
    # --------------------------------------------------------

    forms_before = page.locator(
        'faceplate-form'
        '[action*="/create-comment"]'
    ).count()

    try:

        trigger.click()

    except Exception:

        trigger.click(
            force=True
        )

    print(
        "Clicked top-level comment trigger."
    )

    # --------------------------------------------------------
    # Wait for Reddit's REAL create-comment form.
    # --------------------------------------------------------

    form = None

    for _ in range(50):

        forms = page.locator(
            'faceplate-form'
            '[action*="/create-comment"]'
        )

        if forms.count():

            # Usually the newly-created form is the last one.
            candidate = forms.last

            try:

                composer = candidate.locator(
                    'shreddit-composer'
                    '[name="content"]'
                )

                if composer.count():

                    form = candidate

                    break

            except Exception:
                pass

        page.wait_for_timeout(
            100
        )

    if form is None:

        print(
            "Create-comment forms before click:",
            forms_before
        )

        print(
            "Create-comment forms after click:",
            page.locator(
                'faceplate-form'
                '[action*="/create-comment"]'
            ).count()
        )

        _debug_editors(
            page
        )

        raise RuntimeError(
            "Clicked comment trigger, "
            "but Reddit's real "
            "create-comment form did not appear."
        )

    print(
        "Real Reddit comment form appeared."
    )

    return form


def _get_top_level_editor(form):

    """
    EXACT editor based on the DOM supplied:

    faceplate-form[action*=create-comment]
        shreddit-composer[name=content]
            div[
                slot=rte
                name=body
                contenteditable=true
                role=textbox
                data-lexical-editor=true
            ]
    """

    editor = form.locator(
        'shreddit-composer[name="content"] '
        'div[slot="rte"]'
        '[name="body"]'
        '[contenteditable="true"]'
        '[role="textbox"]'
        '[data-lexical-editor="true"]'
    ).first

    editor.wait_for(
        state="visible",
        timeout=10000
    )

    return editor


def _fill_top_level_editor(
    editor,
    content
):

    """
    IMPORTANT:

    No page.keyboard fallback.

    It can ONLY type into this exact Reddit
    Lexical editor.
    """

    editor.scroll_into_view_if_needed()

    editor.wait_for(
        state="visible",
        timeout=10000
    )

    print(
        "Clicking exact Reddit Lexical editor..."
    )

    editor.click()

    print(
        "Filling exact Reddit Lexical editor..."
    )

    editor.fill(
        content
    )

    entered = (
        editor.inner_text()
        .strip()
    )

    if content.strip() not in entered:

        raise RuntimeError(
            "Reddit comment editor was found, "
            "but text was not entered correctly."
        )


def _submit_top_level_comment(
    page,
    form
):

    """
    Exact button from supplied DOM:

    #comment-composer-submit-button
    """

    submit = form.locator(
        "#comment-composer-submit-button"
    ).first

    submit.wait_for(
        state="visible",
        timeout=10000
    )

    # --------------------------------------------------------
    # Wait until Reddit enables Comment button.
    # --------------------------------------------------------

    for _ in range(50):

        try:

            if submit.is_enabled():
                break

        except Exception:
            pass

        page.wait_for_timeout(
            100
        )

    if not submit.is_enabled():

        _debug_buttons(
            form,
            "BUTTONS INSIDE CREATE-COMMENT FORM"
        )

        raise RuntimeError(
            "Comment button appeared, "
            "but it never became enabled."
        )

    print(
        "Found exact Reddit Comment button."
    )

    submit.click()

    print(
        "Clicked Comment button."
    )


def _post_top_level_comment(
    page,
    content
):

    print()
    print(
        "Opening top-level Reddit comment box..."
    )

    # ========================================================
    # STEP 1
    # Click Reddit's collapsed trigger.
    # ========================================================

    form = _open_top_level_comment_box(
        page
    )

    # ========================================================
    # STEP 2
    # Get the EXACT Lexical editor inside that form.
    # ========================================================

    editor = _get_top_level_editor(
        form
    )

    print(
        "Found real Reddit Lexical editor."
    )

    # ========================================================
    # STEP 3
    # Fill only that exact editor.
    # ========================================================

    _fill_top_level_editor(
        editor,
        content
    )

    print(
        "Entered top-level comment text."
    )

    page.wait_for_timeout(
        250
    )

    # ========================================================
    # STEP 4
    # Exact submit button.
    # ========================================================

    _submit_top_level_comment(
        page,
        form
    )

    page.wait_for_timeout(
        700
    )

    print(
        "Top-level comment submitted."
    )


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