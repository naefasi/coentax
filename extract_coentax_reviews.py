import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


MAPS_URL = (
    "https://www.google.com/maps/place/Coentax/"
    "@-34.1870283,22.112506,17z/data=!4m17!1m8!3m7!1s0x1dd6698d7537518f:0x7ec77fd578266682!"
    "2sCoentax!8m2!3d-34.1870328!4d22.1150809!10e1!16s%2Fg%2F11zj34c464!3m7!1s0x1dd6698d7537518f:"
    "0x7ec77fd578266682!8m2!3d-34.1870328!4d22.1150809!9m1!1b1!16s%2Fg%2F11zj34c464?entry=ttu&"
    "g_ep=EgoyMDI2MDMyNC4wIKXMDSoASAFQAw%3D%3D"
)

DEFAULT_OUTPUT = Path("coentax_reviews.json")


def find_brave_executable() -> str:
    candidates = [
        Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
        Path(r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    brave_on_path = shutil.which("brave") or shutil.which("brave.exe")
    if brave_on_path:
        return brave_on_path

    raise FileNotFoundError(
        "Brave browser was not found. Install Brave or pass --browser-path explicitly."
    )


def click_first_visible(page, selectors: list[str], timeout: int = 4000) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=timeout):
                locator.click()
                return True
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return False


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def parse_rating(label: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", label)
    return float(match.group(1)) if match else None


def wait_for_reviews(page, timeout_ms: int = 15000) -> None:
    review_card_selectors = [
        "[data-review-id]",
        "div.jftiEf",
    ]
    for selector in review_card_selectors:
        try:
            page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
            return
        except PlaywrightTimeoutError:
            continue
    raise RuntimeError("Could not find any visible review cards on the Google Maps page.")


def maybe_handle_google_prompts(page) -> None:
    click_first_visible(
        page,
        [
            "button:has-text('Reject all')",
            "button:has-text('Accept all')",
            "button:has-text('I agree')",
            "button:has-text('No thanks')",
        ],
        timeout=2500,
    )


def open_reviews_if_needed(page) -> None:
    already_showing_reviews = page.locator("[data-review-id], div.jftiEf").count() > 0
    if already_showing_reviews:
        return

    click_first_visible(
        page,
        [
            "button[jsaction*='pane.reviewChart.moreReviews']",
            "button[aria-label*='reviews']",
            "button[aria-label*='Reviews']",
        ],
        timeout=4000,
    )


def expand_full_review_if_present(card) -> None:
    for selector in [
        "button:has-text('More')",
        "button.w8nwRe",
        "button[aria-label*='Full review']",
    ]:
        button = card.locator(selector).first
        try:
            if button.is_visible(timeout=500):
                button.click()
                return
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue


def first_non_empty_text(card, selectors: list[str]) -> str:
    for selector in selectors:
        locator = card.locator(selector).first
        try:
            text = normalize_text(locator.inner_text(timeout=1000))
            if text:
                return text
        except Exception:
            continue
    return ""


def first_non_empty_attribute(card, selectors: list[str], attribute: str) -> str:
    for selector in selectors:
        locator = card.locator(selector).first
        try:
            value = normalize_text(locator.get_attribute(attribute, timeout=1000))
            if value:
                return value
        except Exception:
            continue
    return ""


def extract_top_reviews(page, limit: int) -> list[dict]:
    cards = page.locator("[data-review-id], div.jftiEf")
    review_count = min(cards.count(), limit)
    results = []

    for index in range(review_count):
        card = cards.nth(index)
        expand_full_review_if_present(card)

        customer_name = first_non_empty_text(
            card,
            [
                ".d4r55",
                ".TSUbDb",
                ".WNxzHc",
            ],
        )
        rating_label = first_non_empty_attribute(
            card,
            [
                "span[role='img'][aria-label]",
                "span.kvMYJc[aria-label]",
            ],
            "aria-label",
        )
        review_text = first_non_empty_text(
            card,
            [
                ".wiI7pd",
                ".MyEned",
                ".review-full-text",
            ],
        )

        results.append(
            {
                "customer_name": customer_name,
                "rating_stars": parse_rating(rating_label),
                "review_text": review_text,
            }
        )

    return results


def build_payload(reviews: list[dict]) -> dict:
    return {
        "place": "Coentax",
        "source_url": MAPS_URL,
        "review_count": len(reviews),
        "reviews": reviews,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract the top Google Maps reviews for Coentax and write them to JSON."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Where to write the JSON output. Defaults to coentax_reviews.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="How many reviews to extract. Defaults to 3.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Brave in headless mode.",
    )
    parser.add_argument(
        "--browser-path",
        default=None,
        help="Optional explicit path to brave.exe or another Chromium-based browser.",
    )
    args = parser.parse_args()

    browser_path = args.browser_path or find_brave_executable()
    output_path = Path(args.output)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=browser_path,
            headless=args.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            locale="en-US",
        )
        page = context.new_page()

        try:
            page.goto(MAPS_URL, wait_until="domcontentloaded", timeout=45000)
            maybe_handle_google_prompts(page)
            open_reviews_if_needed(page)
            wait_for_reviews(page)
            page.wait_for_timeout(2000)
            reviews = extract_top_reviews(page, args.limit)
        finally:
            context.close()
            browser.close()

    payload = build_payload(reviews)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(reviews)} review(s) to {output_path.resolve()}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
