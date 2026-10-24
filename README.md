# Reddit Outreach Assistant

A Playwright automation project for finding Android testing exchanges, managing
Reddit conversations, and generating context-aware replies with OpenAI models.

## Features

- Searches selected Android testing communities
- Ranks relevant posts before scraping full discussions
- Builds compact prompts from posts and nested comment threads
- Handles new outreach and follow-up conversations
- Stores conversation state between runs
- Prevents duplicate outreach to the same person or post
- Enforces rolling message limits and a minimum send interval
- Uses a process lock to prevent overlapping runs

## Technology

- Python
- Playwright
- OpenAI Responses API
- JSON-based local persistence
- `unittest` test suite

## Setup

Create a virtual environment and install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Create the local configuration files:

```bash
cp .env.example .env
mkdir -p data/apps
cp data/apps.example.json data/apps/apps.json
```

Fill in the Reddit and OpenAI credentials in `.env`, then describe the Android
apps in `data/apps/apps.json`.

## Usage

```bash
python main.py
```

The browser runs in visible mode. Runtime data is stored under `data/` and is
excluded from Git. Keep that directory between runs because it contains the
history used for duplicate prevention and posting limits.

## Tests

```bash
python -m unittest discover -s tests -v
```

The test suite uses local stubs and does not require Reddit or OpenAI credentials.

## Responsible use

The built-in limits reduce accidental duplicate or excessive posting, but they
do not replace Reddit's rules or individual community policies. Review the target
communities and generated messages before using the automation.

## License

Copyright 2026 Paul Szyburski. All rights reserved. See [LICENSE](LICENSE).
