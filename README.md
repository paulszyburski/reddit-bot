# reddit-bot

Install dependencies into your virtual environment:

```sh
python -m pip install -r requirements.txt
```

Browser automation uses Selenium 4 with Chromium. It detects `chromium` or
`chromium-browser` on PATH, or reuses a previously downloaded Chromium in the
local browser cache. You can set `CHROMIUM_BINARY=/path/to/chromium` in `.env`
to select a specific executable. Missing Chromium produces an error.

Selenium's Chrome driver also supports Chromium. Selenium Manager resolves the
browser driver automatically; initial setup may require network access.
See the [Selenium Manager documentation](https://www.selenium.dev/documentation/selenium_manager/).

Configure `REDDIT_USERNAME`, `REDDIT_PASSWORD`, and `CHATGPT_API_KEY` in `.env`,
then run `python main.py`. This runs the bot's existing outreach and reply flows.
For a manual browser/login check, run `python test.py`.

Run automated tests without contacting Reddit:

```sh
python -m unittest discover -s tests -v
```
