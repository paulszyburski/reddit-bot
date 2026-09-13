"""Local posting limits based on saved successful messages, shared across apps."""
from datetime import datetime, timedelta, timezone

from AI.prompts import post_key

MAX_NEW_CONVERSATIONS = 3
MAX_MESSAGES = 10
MIN_SEND_INTERVAL = timedelta(minutes=30)


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def posting_limit_reason(history, our_username, *, new_conversation=False, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    sent = []
    starts = []
    for conversation in history:
        if (conversation.get("ourUsername") or "").casefold() != our_username.casefold():
            continue
        messages = conversation.get("ourMessages") or []
        # Legacy records may contain only the last execution timestamp.
        dates = [_timestamp(message.get("sentAt")) for message in messages]
        if not dates:
            dates = [_timestamp(conversation.get("executedAt"))]
        if any(date is None for date in dates):
            return "Saved send time is missing or invalid; cannot safely enforce posting limits."
        sent.extend(dates)
        starts.append(min(dates))
    if len([date for date in sent if date > cutoff]) >= MAX_MESSAGES:
        return "Rolling 24-hour message limit reached."
    if new_conversation and len([date for date in starts if date > cutoff]) >= MAX_NEW_CONVERSATIONS:
        return "Rolling 24-hour new-conversation limit reached."
    if sent and now - max(sent) < MIN_SEND_INTERVAL:
        return "Waiting for the 30-minute interval between messages."
    return None


def outreach_reason(history, decision):
    ours = (decision.get("ourUsername") or "").casefold()
    target = (decision.get("targetUsername") or "").casefold()
    for conversation in history:
        if (conversation.get("ourUsername") or "").casefold() != ours:
            continue
        if post_key(conversation.get("postHref") or "") == post_key(decision.get("postHref") or ""):
            return "Already started a conversation under this post."
        previous_target = conversation.get("youAreTalkingTo") or conversation.get("targetUsername") or ""
        if target and previous_target.casefold() == target:
            return "Already approached this person; continue the existing conversation only."
    return None


def eligible_reply_ids(conversation, post):
    """Accept only target replies descended from our latest saved message.

    Reddit ranking is not chronological. Follow the tree rather than list order.
    If that message is absent from the scrape, wait instead of guessing.
    """
    messages = conversation.get("ourMessages") or []
    if not messages:
        return set()
    ours = (conversation.get("ourUsername") or "").casefold()
    target = (conversation.get("youAreTalkingTo") or "").casefold()
    latest = messages[-1].get("content", "").strip()
    answered = {message.get("replyTo") for message in messages}
    eligible = set()

    def visit(comments, below_latest=False):
        for comment in comments:
            author = (comment.get("username") or "").casefold()
            content = (comment.get("content") or "").strip()
            is_latest = bool(latest) and author == ours and content == latest
            if below_latest and author == target and content and comment.get("id") not in answered:
                eligible.add(comment.get("id"))
            visit(comment.get("replies", []), below_latest or is_latest)

    visit(post.get("comments", []))
    return eligible - {None}
