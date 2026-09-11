"""Manual Selenium login check: python test.py."""
from reddit.browser import create_driver


def main():
    driver = create_driver()
    try:
        driver.get("https://reddit.com")
        input("Try logging in MANUALLY and press Enter afterwards...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
