import time
from reddit.browser import wait_element
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from reddit.conversations.notifications import notification_state_key, mark_notification_handled
from reddit.posts import scrape_post
from AI.chatgpt import generate_response
from reddit.conversations.utils import (
    _find_post,
    _find_comment_path,
    _find_reddit_comment,
    _post_reply,
    _post_top_level_comment,
    _add_contacted_post,
    _comment_permalink,
    _append_our_message_to_thread,
    _update_existing_conversation
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


def plan_conversations(file_path, our_username, app):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    contacted_posts = set()
    if CONTACTED_PATH.exists():
        with open(CONTACTED_PATH, "r", encoding="utf-8") as file:
            contacted_posts = {line.strip() for line in file if line.strip()}

    decisions = []

    for post in data:
        href = post.get("href")
        if href in contacted_posts:
            continue

        now = datetime.now(timezone.utc).isoformat()

        prompt = f"""
You are recruiting Android closed-testing testers on Reddit for OUR app.

OUR REDDIT USERNAME:

{our_username}

YOUR JOB:

Analyze this ONE Reddit post, including all comments and nested replies, and
choose the SINGLE BEST person to approach RIGHT NOW.

Then write the exact Reddit message we should post.

Do not merely analyze opportunities.
Do not give advice.
Do not explain what we could do.

TAKE ACTION.

Your goal is to recruit a real tester for OUR Android app as efficiently and
naturally as possible.

==================================================
OUR APP
==================================================

The following is authoritative information about the app we are recruiting
testers for:

{json.dumps(app, ensure_ascii=False, indent=2)}

Use ONLY information contained in this app object.

You MAY use:
- the real app name
- the real app description
- the real testing / opt-in link
- the Google Group link if provided
- any other real information contained in the app object

Do NOT invent any app information.

IMPORTANT:

If the app object contains the information needed for someone to join the test,
USE IT DIRECTLY when appropriate.

Do NOT say:

"I'll send you my testing details."

if the testing details are already available in the app object.

Instead, give them the relevant link/details immediately.

==================================================
PRIMARY GOAL
==================================================

The goal is to get ONE person from this Reddit post to test OUR app.

Prefer people who are already clearly interested in:

- test-for-test
- reciprocal testing
- finding Android testers
- exchanging closed tests
- helping other developers
- testing another person's app

If somebody is already offering test-for-test, do not waste time asking whether
they are interested.

Move directly toward the exchange.

For example, instead of:

"Would you be interested in testing mine too?"

prefer something like:

"Happy to test yours too. Here's my testing link: [REAL LINK]"

when that naturally fits the conversation.

==================================================
ACTION MEANINGS
==================================================

"reply" and "comment" describe WHERE we post the message.

ACTION: "reply"

Use this when a SPECIFIC existing comment is the best recruitment opportunity.

We reply directly to that comment.

The commenter does NOT need to:
- have spoken to us before
- mention us
- know us
- have tested our app already

If action == "reply":

- replyTo MUST exactly match the ID of the comment being answered
- targetUsername MUST exactly match that comment author's username


ACTION: "comment"

Use this when the ORIGINAL POST itself is the best opportunity and there is no
specific comment that is clearly better.

This creates a NEW TOP-LEVEL comment under the post.

If action == "comment":

- replyTo MUST be null
- targetUsername MUST normally be the original poster


ACTION: "none"

Use this only when there is genuinely no useful recruitment opportunity.

Do NOT choose "none" merely because:
- nobody mentioned us
- nobody directly asked us
- another person was speaking to OP

We are allowed to naturally enter an existing discussion.

==================================================
BE PROACTIVE
==================================================

Do not be overly passive.

If someone:
- asks for testers
- offers test-for-test
- posts their own testing links
- says they will test other apps
- asks people to exchange testing

then they are a strong recruitment target.

When appropriate:

1. Acknowledge their offer briefly.
2. Offer to test their app if truthful as a future action.
3. Give OUR actual testing information immediately.
4. Ask them to join/test OUR app only when needed.

Avoid unnecessary intermediate messages.

BAD:

"I'm also looking for testers. Let me know if you're interested and I'll send
you my link."

GOOD:

"I'm happy to do test-for-test. Here's my opt-in link: [REAL TEST LINK]. I'll
check yours out too."

The exact wording should depend on the conversation.

==================================================
CRITICAL PERSPECTIVE
==================================================

You are acting ONLY as:

{our_username}

Do NOT assume we are OP.

Do NOT pretend another user's actions toward OP were actions toward us.

Before choosing a message, determine internally:

1. Who is OP?
2. Who wrote the target comment?
3. Who were they speaking to?
4. What are they offering or asking for?
5. Can our account naturally enter the conversation?
6. What message would make sense from OUR perspective?

We MAY reply to someone who was originally speaking to OP.

But we must enter as a NEW participant.

==================================================
EXAMPLE OF PERSPECTIVE
==================================================

Suppose:

OP:
"Test mine and I'll test yours."

Another user:
"Done! Please test mine too."

That user is telling OP they tested OP's app.

WE MUST NOT say:

"Thanks for testing mine!"

because they did not test ours.

We MAY say:

"I'm doing test-for-test too. Happy to test yours — here's my testing link:
[REAL LINK]."

==================================================
TRUTHFULNESS
==================================================

Never invent:

- app names
- links
- package names
- Google Groups
- emails
- screenshots
- installations
- tests completed
- reviews
- feedback already given
- prior conversations
- promises already completed

Never say:

"I tested your app."
"I installed it."
"I joined your group."
"I left a review."

unless the supplied data explicitly shows OUR account did that.

Future-looking statements ARE allowed:

"I can test yours."
"Happy to return the test."
"I'll check yours out too."
"I can keep it installed for the testing period."

Only make future promises that are reasonable from the context.

==================================================
USE THEIR LINKS
==================================================

If the target user already provided:

- their testing link
- their Google Group
- their Play Store link
- their package information

do NOT ask them to send it again.

They already gave us what we need.

Move the conversation forward.

==================================================
USE OUR APP INFORMATION
==================================================

If OUR app object contains:

- app name
- testing link
- Google Group
- app description

use those exact values where useful.

Keep the description short.

Do not dump the entire app description into Reddit.

Usually one short phrase explaining the app is enough.

Example structure:

"Happy to do test-for-test. Mine is [APP NAME], [very short description].
Here's the test link: [LINK]. I'll check yours out too."

Adapt naturally to the actual thread.

==================================================
CHOOSE THE BEST TARGET
==================================================

When several opportunities exist, prioritize:

1. Someone explicitly offering test-for-test.
2. Someone who needs testers and provides their links.
3. Someone explicitly volunteering to test apps.
4. OP asking for reciprocal testing.
5. OP simply asking for testers.
6. Other relevant opportunities.

Prefer the person most likely to actually reciprocate.

Do NOT contact AutoModerator.

Do NOT target deleted users.

Do NOT target OUR OWN account.

==================================================
MESSAGE STYLE
==================================================

Write concise, natural Reddit messages.

Usually 1-3 sentences.

The message should:

- sound human
- be casual
- be friendly
- get to the point quickly
- clearly communicate the exchange
- include OUR real testing link when useful
- not sound like marketing
- not sound automated
- not mention AI
- not over-explain
- avoid generic filler

Avoid excessive phrases like:

"Let me know if you're interested"

when the other person already clearly expressed interest in test-for-test.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

No markdown.
No ```json.
No text outside the JSON.

Return exactly:

{{
    "action": "comment" | "reply" | "none",
    "replyTo": "existing reddit comment id" | null,
    "targetUsername": "reddit username" | null,
    "content": "exact Reddit message we should post",
    "conversationStatus": "ACTIVE" | "NO_ACTION",
    "lastChecked": "{now}",
    "reason": "short explanation of why this person and action were chosen",
    "confidence": 0.0
}}

==================================================
OUTPUT RULES
==================================================

If action == "reply":

- replyTo MUST exactly match an existing comment ID
- targetUsername MUST exactly match that comment author's username
- content MUST be non-empty
- conversationStatus MUST be "ACTIVE"


If action == "comment":

- replyTo MUST be null
- targetUsername MUST normally be the original post username
- content MUST be non-empty
- conversationStatus MUST be "ACTIVE"


If action == "none":

- replyTo MUST be null
- targetUsername MUST be null
- content MUST be ""
- conversationStatus MUST be "NO_ACTION"


confidence must be between 0.0 and 1.0.

==================================================
FINAL INTERNAL CHECK
==================================================

Before returning JSON, verify:

1. Did I choose the person most likely to become a tester?
2. Am I taking action rather than being unnecessarily passive?
3. Am I speaking as {our_username}, not as OP?
4. Does replyTo exactly match a real comment?
5. Does targetUsername match that comment's author?
6. Did I avoid pretending somebody tested OUR app when they actually tested OP's?
7. Did I use OUR real app information instead of inventing anything?
8. If our testing link is available and useful here, did I include it now?
9. Did I avoid asking for links the other user already provided?
10. Does the message naturally move toward an actual test-for-test exchange?
11. Is the message short and human?

==================================================
REDDIT POST
==================================================

{json.dumps(post, ensure_ascii=False, indent=2)}
"""


        response = generate_response(prompt)

        try:
            decision = json.loads(response)
            decision["id"] = str(uuid.uuid4())
            decision["postHref"] = post.get("href")
            decision["community"] = post.get("community")
            decision["postUsername"] = post.get("username")
            decision["ourUsername"] = our_username
            decision["sourcePath"] = file_path
            decision["appName"] = app["name"]
            decisions.append(decision)
        except json.JSONDecodeError:
            print("Invalid JSON returned by ChatGPT:")
            print(response)

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
        conversation.get("id")
        for conversation in ongoing
        if conversation.get("id")
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
            target_comment = _find_comment_path(
                source_post.get("comments", []),
                reply_to
            )

            if target_comment is None:
                print(f"Could not find {reply_to} in source JSON.")
                continue

        if action == "reply":
            destination = _comment_permalink(href, reply_to)
            print("Opening comment permalink:")
        else:
            destination = href
            print("Opening post:")

        print(destination)

        try:
            page.get(destination)

            wait_element(page, "shreddit-post", timeout=15.0, visible_only=False)

            time.sleep(1.0)

            if action == "reply":
                try:
                    wait_element(page, "shreddit-comment", timeout=10.0, visible_only=False)
                except Exception:
                    pass

            elif action == "comment":
                try:
                    wait_element(page, 'faceplate-textarea-input[data-testid="trigger-button"]', timeout=10.0, visible_only=False)
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
                    page.get(href)
                    time.sleep(1.5)

                _post_reply(page, reply_to, content)

            else:
                print(f"Writing top-level comment to {target_username}")
                _post_top_level_comment(page, content)

            time.sleep(1.2)

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
            "sentAt": executed_at
        }

        added_to_thread = add_message_to_thread(
            source_post,
            action,
            reply_to,
            sent_message
        )

        if not added_to_thread:
            print(
                "WARNING: Message was sent, but could not "
                "be inserted into saved thread."
            )

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
                    "sentAt": executed_at
                }
            ]
        }

        ongoing.append(ongoing_conversation)
        _save_json(ONGOING_PATH, ongoing)

        _add_contacted_post(href)

        planned = [
            item
            for item in planned
            if item.get("id") != conversation_id
        ]

        _save_json(PLANNED_PATH, planned)

        already_executed.add(conversation_id)

        print()
        print("Successfully executed.")
        print()

def handle_conversation_reply(page, href):
    # Resolve the conversation before scraping its complete thread. Notification
    # links may point at different comment permalinks under the same post.
    ongoing_conversations = _load_json(
        ONGOING_PATH,
        []
    )

    conversations = [
        item
        for item in ongoing_conversations
        if item.get("postHref") and (
            href.split("?", 1)[0].rstrip("/") == item["postHref"].rstrip("/")
            or href.startswith(item["postHref"].rstrip("/") + "/")
        )
    ]

    if not conversations:
        print("Conversation not found.")
        return

    if len(conversations) > 1:
        print("Many conversations under 1 post. Fix that!")
        return

    conversation = conversations[0]

    app = conversation["appName"]

    page.get(conversation["postHref"])
    post = scrape_post(page)
    notification_key = notification_state_key(
        post, conversation["ourUsername"], conversation["postHref"]
    )
    handled = set()
    if CONTACTED_NOTIFICATIONS_PATH.exists():
        handled = set(CONTACTED_NOTIFICATIONS_PATH.read_text(encoding="utf-8").splitlines())
    # Legacy URL entries cannot tell which reply was handled. Keep them as
    # history, but never use them to block future replies in the same thread.
    if notification_key in handled:
        print(f"Incoming thread content already handled: {href}")
        return

    # Replace old thread with newest scrape
    conversation["thread"] = post

    _save_json(
        ONGOING_PATH,
        ongoing_conversations
    )

    # ==================================================
    # PREPARE CHATGPT PROMPT
    # ==================================================

    our_username = conversation["ourUsername"]
    now = datetime.now(timezone.utc).isoformat()


    prompt = f"""
You are continuing an EXISTING Reddit conversation on behalf of an Android app developer.

Your job is to continue the conversation naturally and move the person we are
already talking to toward actually testing OUR Android app.

You are NOT choosing a new person to contact.
You are NOT starting a new outreach conversation.
You are continuing ONE existing conversation.

==================================================
OUR IDENTITY
==================================================

Our Reddit username:

{our_username}

Always write from the perspective of this Reddit account.

Never pretend to be:
- the original poster
- another commenter
- the developer of somebody else's app

==================================================
OUR APP
==================================================

The following object contains the authoritative information about OUR app:

{json.dumps(app, ensure_ascii=False, indent=2)}

Use ONLY information contained in this object.

You may use:
- the real app name
- the real app description
- the real testing / opt-in link
- the real Google Group / testers group link
- package information
- any other real app information present in the object

DO NOT invent any missing information.

IMPORTANT:

If the user asks for:
- our app link
- testing details
- app name
- how to join the test
- the testers group
- the Google Group

and that information exists in the app object, GIVE IT DIRECTLY.

Do NOT say:

"I'll send you the link."
"I'll send you my testing details."
"I'll send it later."

if the information is already available in the app object.

Move the conversation forward immediately.

==================================================
PRIMARY GOAL
==================================================

The goal is to get the person we are already talking to to actually join and
test OUR Android app.

The person we are talking to is:

{conversation.get("youAreTalkingTo")}

This is usually a reciprocal test-for-test conversation.

Typical progression:

1. We offer test-for-test.
2. They respond.
3. We confirm the exchange.
4. We explain exactly how to join OUR closed test.
5. They join the testers Google Group FIRST.
6. They open the Google Play testing / opt-in link SECOND.
7. They join the test and install the app.
8. We continue the conversation naturally if needed.

Do not unnecessarily repeat earlier steps.

==================================================
VERY IMPORTANT: CLOSED TEST JOINING ORDER
==================================================

When OUR app uses a Google Group / testers group for closed testing, the user
MUST be instructed to join the testers group BEFORE opening the app testing link.

If BOTH of these exist in the app object:

- Google Group / testers group link
- Google Play testing / opt-in / app testing link

then ALWAYS present them in this order:

STEP 1:
Join the testers Google Group.

STEP 2:
After joining the group, open the Google Play testing / opt-in link.

NEVER give the Play testing link first and the Google Group second.

NEVER make the instructions ambiguous.

The tester should understand that joining the Google Group is a prerequisite
for accessing the closed test.

==================================================
HOW TO EXPLAIN JOINING THE TEST
==================================================

When the target user:
- agrees to test our app
- asks for our link
- asks how to join
- asks for testing details
- asks for the Google Group
- otherwise reaches the point where they need our testing information

write a SHORT, CLEAR TUTORIAL explaining exactly what they need to do.

If both links exist, the tutorial should normally communicate:

1. Join our testers Google Group using the REAL group link from the app object.
2. Make sure you are signed into the Google account you use for Google Play.
3. After joining the group, open the REAL Google Play testing / opt-in link.
4. Tap the option to join / become a tester if Google Play asks.
5. Install the app from Google Play.
6. Test the app.

The wording does NOT have to match these sentences exactly.

Make it:
- casual
- easy to follow
- short
- suitable for Reddit
- clear enough that someone unfamiliar with Google Play closed testing can follow it

The message should preferably use numbered steps or separate short lines when
giving testing instructions.

Example STYLE ONLY:

"Sure! Here's how to join:

1. First join my testers group: [REAL GROUP LINK]
2. Make sure you're using the same Google account as your Play Store account.
3. Then open the testing link: [REAL TESTING LINK]
4. Tap 'Become a tester' and install the app from Google Play.

Thanks!"

DO NOT copy fake placeholder links.

Always use the REAL links from the app object.

==================================================
DO NOT REPEAT COMPLETED STEPS
==================================================

Read the conversation before sending the tutorial.

If the conversation clearly shows that the target user has ALREADY joined our
Google Group, do NOT tell them to join it again.

Instead, move them to the next step, for example the Google Play testing link.

If they already received the testing instructions and there is no new reason
to repeat them, do not send the same tutorial again.

Take the next unfinished step only.

==================================================
THIS IS AN EXISTING CONVERSATION
==================================================

Read the entire conversation carefully.

In particular, read:

- "ourMessages"
- "thread"
- "youAreTalkingTo"

The field "ourMessages" contains messages OUR account already sent.

Treat it as authoritative history.

DO NOT:
- choose another commenter
- switch to OP
- restart the conversation
- repeat our introduction
- repeat an offer we already made
- ask again for something they already answered
- send the same testing link repeatedly without reason
- repeat the Google Group link if they already joined
- repeat the full tutorial if they already completed those steps

Your response must make sense immediately after the existing conversation.

==================================================
DO NOT DOUBLE MESSAGE
==================================================

If OUR most recent message has NOT received a meaningful response from:

{conversation.get("youAreTalkingTo")}

return action "none".

Do not send:
- reminders
- another invitation
- another test-for-test offer
- "just checking"
- follow-up spam
- the same app link again
- the same joining tutorial again

Wait for them to respond.

==================================================
DETERMINE THE NEXT STEP
==================================================

Before responding, internally determine:

1. What did OUR account last say?
2. What was the latest message from the target user AFTER that?
3. Did they actually respond to us?
4. What are they asking for or agreeing to?
5. What is the next natural step toward getting them to test our app?
6. Do we already have the information needed to take that step?
7. Has this step already been completed?
8. Have they joined our testers group already?
9. Have they already received our Google Play testing link?
10. Do they currently need the full joining tutorial or only the next step?

Take only ONE natural next step.

==================================================
IF THEY AGREE TO TEST
==================================================

If the target user agrees to test our app:

- acknowledge briefly
- immediately give the information needed to join
- use the real data from the app object
- do not ask whether they are interested again

If our app requires joining a Google Group and BOTH links exist:

DO NOT simply write:

"Here's my app: [testing link]"

Instead give the joining instructions in the correct order:

1. Google Group FIRST
2. Google Play test link SECOND

Example behavior:

BAD:

"Perfect! Here's my testing link:
[TEST LINK]

And here's my Google Group:
[GROUP LINK]"

BAD because the tester may open the testing link before joining the required group.

GOOD:

"Perfect, thanks! Here's how to join:

1. First join the testers group: [REAL GROUP LINK]
2. Then open the testing link: [REAL TEST LINK]
3. Join the test and install it from Google Play."

==================================================
IF THEY ASK FOR OUR LINK OR APP DETAILS
==================================================

Answer directly using the app object.

If they ask:
- "What's your app?"
- "Send me your link."
- "What's the testing link?"
- "How do I join?"
- "Do you have a Google Group?"
- "How can I test yours?"
- anything equivalent

then provide the actual relevant information.

If a Google Group is required for the test, do NOT send only the Play link.

Give them the required group link first and explain the steps.

Do NOT be vague when the answer exists in the app object.

==================================================
IF THEY PROVIDE THEIR APP DETAILS
==================================================

If the target user gives us:
- their app name
- testing link
- Google Group
- Play Store link
- package name

do not ask them to send those details again.

You may refer to those details naturally.

==================================================
TRUTHFULNESS
==================================================

Never invent:
- testing completed
- installations
- joining their Google Group
- reviews
- feedback
- screenshots
- prior actions
- app information not present in the provided data

Never say:

"I tested your app."
"I installed it."
"I joined your group."
"I left a review."

unless the supplied conversation explicitly proves OUR account did that.

Future-looking statements are allowed:

"I can test yours too."
"I'll check yours out."
"Happy to return the test."

==================================================
REPLY TARGET
==================================================

Normally use action "reply".

Reply to the NEWEST relevant comment from:

{conversation.get("youAreTalkingTo")}

that came AFTER our most recent message.

If action == "reply":

- replyTo MUST exactly match the ID of that existing Reddit comment
- targetUsername MUST exactly match that comment author's username
- normally targetUsername should be:
  {conversation.get("youAreTalkingTo")}

Do not reply to an older comment merely because it contains useful links.

Reply to the newest relevant message in the actual conversation.

==================================================
ACTION: COMMENT
==================================================

A new top-level comment should be extremely rare here.

The conversation already exists.

Normally do NOT use "comment".

Use "comment" only if the supplied conversation clearly requires a new
top-level comment and there is no appropriate existing comment to reply to.

==================================================
ACTION: NONE
==================================================

Return "none" when:

- they have not replied to our latest message
- only OP or unrelated users replied
- their newest message does not require a response
- we'd repeat ourselves
- they declined
- the conversation has naturally ended
- there is currently nothing useful to say

Silence is better than duplicate messaging.

==================================================
MESSAGE STYLE
==================================================

Write natural Reddit messages.

Normally:
- 1-3 sentences
- casual
- friendly
- human-sounding

HOWEVER:

When giving instructions for joining our closed test, you MAY use a slightly
longer message with approximately 3-6 short numbered steps or short lines.

Clarity is more important than forcing the joining tutorial into 1-3 sentences.

The message should:
- sound human
- be casual and friendly
- respond directly to what they just said
- move the exchange forward
- include real app/testing information when useful
- clearly explain Google Group FIRST, testing link SECOND when required
- not sound like marketing
- not sound automated
- not mention AI
- not over-explain

Avoid unnecessary filler such as:

"Let me know if you're interested"

when they already said they are interested.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

No markdown.
No ```json.
No text outside the JSON.

Return exactly:

{{
    "action": "comment" | "reply" | "none",
    "replyTo": "existing reddit comment id" | null,
    "targetUsername": "reddit username" | null,
    "content": "exact Reddit message we should post",
    "conversationStatus": "ACTIVE" | "NO_ACTION",
    "lastChecked": "{now}",
    "reason": "short explanation of the next conversational step",
    "confidence": 0.0
}}

==================================================
OUTPUT RULES
==================================================

If action == "reply":

- replyTo MUST exactly match an existing comment ID
- targetUsername MUST exactly match that comment author's username
- content MUST be non-empty
- conversationStatus MUST be "ACTIVE"

If action == "comment":

- replyTo MUST be null
- content MUST be non-empty
- conversationStatus MUST be "ACTIVE"

If action == "none":

- replyTo MUST be null
- targetUsername MUST be null
- content MUST be ""
- conversationStatus MUST be "NO_ACTION"

confidence must be between 0.0 and 1.0.

==================================================
FINAL INTERNAL CHECK
==================================================

Before returning JSON, verify:

1. Am I continuing the SAME conversation?
2. Did I read all of ourMessages?
3. Did the target user actually respond after our latest message?
4. Am I replying to the newest relevant message?
5. Am I avoiding repeating something we already said?
6. Am I moving the person closer to actually testing our app?
7. If they asked for our link/details, did I use the REAL app object?
8. If a testers Google Group is required, did I put the GROUP LINK FIRST?
9. Did I put the Google Play testing link AFTER the group link?
10. Did I clearly explain how to join the test?
11. Did I avoid saying "I'll send it later" when the information is available?
12. Did I avoid inventing anything?
13. Did I avoid claiming we already tested their app unless proven?
14. Did I avoid repeating steps they already completed?
15. Does the message sound natural immediately after the existing thread?

==================================================
EXISTING CONVERSATION DATA
==================================================

{json.dumps(conversation, ensure_ascii=False, indent=2)}

==================================================
CURRENT NOTIFICATION URL
==================================================

{href}
"""



    # ==================================================
    # ASK CHATGPT
    # ==================================================

    # CHANGE THIS LINE to whatever your existing
    # ChatGPT function is actually called.
    response = generate_response(prompt)

    if isinstance(response, str):
        decision = json.loads(response)
    else:
        decision = response

    print()
    print("AI DECISION:")
    print(
        json.dumps(
            decision,
            ensure_ascii=False,
            indent=2
        )
    )
    print()

    # ==================================================
    # READ DECISION
    # ==================================================

    action = decision.get("action")
    content = decision.get("content", "")
    reply_to = decision.get("replyTo")
    target_username = decision.get("targetUsername")

    conversation["lastChecked"] = decision.get(
        "lastChecked",
        datetime.now(timezone.utc).isoformat()
    )

    conversation["reason"] = decision.get(
        "reason",
        ""
    )

    conversation["confidence"] = decision.get(
        "confidence",
        0.0
    )

    # ==================================================
    # NO ACTION
    # ==================================================

    if action == "none":
        print("No action required.")

        conversation["conversationStatus"] = "ACTIVE"
        conversation["executionStatus"] = "WAITING_FOR_REPLY"

        _save_json(
            ONGOING_PATH,
            ongoing_conversations
        )

        mark_notification_handled(CONTACTED_NOTIFICATIONS_PATH, notification_key)

        return

    # ==================================================
    # VALIDATE DECISION
    # ==================================================

    if action not in ("reply", "comment"):
        print(f"Unknown action: {action}")
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

    # ==================================================
    # OPEN REDDIT DESTINATION
    # ==================================================

    if action == "reply":
        destination = _comment_permalink(
            post_href,
            reply_to
        )

        print("Opening comment permalink:")
        print(destination)

    else:
        destination = post_href

        print("Opening post:")
        print(destination)

    try:
        page.get(destination)

        wait_element(page, "shreddit-post", timeout=15.0, visible_only=False)

        time.sleep(1.0)

        if action == "reply":
            try:
                wait_element(page, "shreddit-comment", timeout=10.0, visible_only=False)
            except Exception:
                pass

        elif action == "comment":
            try:
                wait_element(page, 'faceplate-textarea-input[data-testid="trigger-button"]', timeout=10.0, visible_only=False)
            except Exception:
                pass

    except Exception as e:
        print(f"Failed opening Reddit: {e}")
        return

    # ==================================================
    # SEND REDDIT MESSAGE
    # ==================================================

    try:
        if action == "reply":
            print(
                f"Replying to {reply_to} "
                f"({target_username})"
            )

            if _find_reddit_comment(
                page,
                reply_to
            ) is None:
                print(
                    "Comment not loaded on permalink. "
                    "Trying main post..."
                )

                page.get(post_href)

                time.sleep(1.5)

            _post_reply(
                page,
                reply_to,
                content
            )

        else:
            print(
                f"Writing top-level comment "
                f"to {target_username}"
            )

            _post_top_level_comment(
                page,
                content
            )

        time.sleep(1.2)

    except Exception as e:
        print()
        print("FAILED sending conversation reply")
        print(f"Reason: {e}")
        print()
        return

    # ==================================================
    # MESSAGE WAS SUCCESSFULLY SENT
    # ==================================================

    executed_at = datetime.now(
        timezone.utc
    ).isoformat()

    sent_message = {
        "id": None,
        "username": conversation.get(
            "ourUsername",
            "OUR_ACCOUNT"
        ),
        "content": content,
        "replies": [],
        "isOurs": True,
        "sentAt": executed_at
    }

    # ==================================================
    # ADD OUR NEW MESSAGE TO SAVED THREAD
    # ==================================================

    def add_message_to_thread(comments):
        if action == "comment":
            comments.append(sent_message)
            return True

        for comment in comments:
            if comment.get("id") == reply_to:
                comment.setdefault(
                    "replies",
                    []
                ).append(sent_message)

                return True

            if add_message_to_thread(
                comment.get("replies", [])
            ):
                return True

        return False

    added_to_thread = add_message_to_thread(
        conversation["thread"].setdefault(
            "comments",
            []
        )
    )

    if not added_to_thread:
        print(
            "WARNING: Message was sent, but could "
            "not be inserted into saved thread."
        )

    # ==================================================
    # UPDATE SAME ONGOING CONVERSATION
    # ==================================================

    conversation["action"] = action
    conversation["replyTo"] = reply_to
    conversation["targetUsername"] = target_username
    conversation["content"] = content

    conversation["conversationStatus"] = "ACTIVE"
    conversation["executionStatus"] = "EXECUTED"
    conversation["executedAt"] = executed_at

    conversation["youAreTalkingTo"] = target_username

    conversation.setdefault(
        "ourMessages",
        []
    ).append({
        "action": action,
        "replyTo": reply_to,
        "targetUsername": target_username,
        "content": content,
        "sentAt": executed_at
    })

    # ==================================================
    # SAVE ONGOING JSON
    # ==================================================

    _save_json(
        ONGOING_PATH,
        ongoing_conversations
    )

    mark_notification_handled(CONTACTED_NOTIFICATIONS_PATH, notification_key)

    print()
    print("Conversation reply successfully executed.")
    print()