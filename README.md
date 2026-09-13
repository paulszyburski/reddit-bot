# reddit-bot

Posting controls use saved `data/ongoing_conversations.json` history across runs
and apps for the same account. Defaults in `reddit/conversations/posting_policy.py`:

- 3 new conversations and 10 total messages per rolling 24 hours.
- At least 30 minutes between sends. Deferred work is skipped, not slept on.
- No new outreach to a previously contacted person or post.
- Follow-ups only answer new target replies beneath our latest message;
  missing thread context causes a skip. Repeated follow-up text is suppressed.
- Notifications run before outreach. Deferred plans are resumed before creating
  more plans, and overlapping calls to `main()` are blocked with a process lock.

Keep saved history to preserve limits. These are application limits, not Reddit's
published quotas or a guarantee that posting is allowed in a community.
Message editors type at a fixed 40 ms per character, retaining multiline text.
Typing does not conceal automation. No VPN or detection bypass is involved.
