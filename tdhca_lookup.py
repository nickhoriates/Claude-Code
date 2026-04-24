#!/usr/bin/env python3
"""
TDHCA Manufactured Home Lookup
Usage: python tdhca_lookup.py <label_number> [<label_number> ...]
       python tdhca_lookup.py --json <label_number>

Examples:
    python tdhca_lookup.py ABC123456
    python tdhca_lookup.py ABC123456 DEF789012
    python tdhca_lookup.py --json ABC123456

Requires: pip install playwright && playwright install chromium
"""

import sys
import json
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://mhweb.tdhca.state.tx.us/mhweb/title_view.jsp"
NAV_TIMEOUT = 30_000   # ms — page navigation
IDLE_TIMEOUT = 15_000  # ms — networkidle wait


async def lookup_label(page, label_number: str) -> dict | None:
    """Look up a single label number. Returns a data dict or None if not found."""
    print(f"\nSearching TDHCA for label number: {label_number}...\n")

    try:
        await page.goto(BASE_URL, timeout=NAV_TIMEOUT)
    except PlaywrightTimeoutError:
        print(f"ERROR: Timed out loading {BASE_URL}")
        return None

    # Fill search form
    try:
        await page.fill('input[name="labelNum"]', label_number)
        await page.select_option('select[name="sortOrder"]', 'label')
    except Exception as e:
        print(f"ERROR: Could not interact with search form: {e}")
        return None

    # Submit and wait for results
    try:
        await page.click('input[type="submit"], button[type="submit"], input[value="Submit"]')
        await page.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT)
    except PlaywrightTimeoutError:
        print("WARNING: Page did not fully idle after submit — continuing anyway.")
    except Exception as e:
        print(f"ERROR: Submit failed: {e}")
        return None

    # Find result links in the results table
    results = await page.query_selector_all('table a')
    if not results:
        print(f"No results found for label number: {label_number}")
        return None

    first_link = results[0]
    link_text = (await first_link.inner_text()).strip()
    print(f"Found result: {link_text}")

    # Navigate to detail page
    try:
        await first_link.click()
        await page.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT)
    except PlaywrightTimeoutError:
        print("WARNING: Detail page did not fully idle — continuing anyway.")
    except Exception as e:
        print(f"ERROR: Could not open detail page: {e}")
        return None

    detail_url = page.url
    data: dict[str, str] = {"_url": detail_url, "_label_searched": label_number}

    # Extract all table key-value pairs; handle both 2-cell and 4-cell rows
    rows = await page.query_selector_all("tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        pairs: list[tuple[str, str]] = []

        if len(cells) >= 2:
            pairs.append((
                (await cells[0].inner_text()).strip().rstrip(":"),
                (await cells[1].inner_text()).strip(),
            ))
        if len(cells) >= 4:
            pairs.append((
                (await cells[2].inner_text()).strip().rstrip(":"),
                (await cells[3].inner_text()).strip(),
            ))

        for label, value in pairs:
            if label and value and label not in data:
                data[label] = value

    return data


def print_record(data: dict, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
        return

    url = data.pop("_url", None)
    data.pop("_label_searched", None)

    print(f"\n{'─' * 50}")
    print("TDHCA Manufactured Home Details")
    print(f"{'─' * 50}")
    for label, value in data.items():
        print(f"  {label}: {value}")
    if url:
        print(f"\n  Verify at TDHCA: {url}")
    print(f"{'─' * 50}\n")


async def run(label_numbers: list[str], as_json: bool) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        all_results = []
        for label in label_numbers:
            data = await lookup_label(page, label)
            if data:
                all_results.append(data)
                if not as_json:
                    print_record(data, as_json=False)
            else:
                if as_json:
                    all_results.append({"_label_searched": label, "error": "not found"})

        if as_json:
            output = all_results[0] if len(all_results) == 1 else all_results
            print(json.dumps(output, indent=2))

        await context.close()
        await browser.close()


def main() -> None:
    args = sys.argv[1:]

    as_json = False
    if "--json" in args:
        as_json = True
        args = [a for a in args if a != "--json"]

    if not args:
        print("Usage: python tdhca_lookup.py [--json] <label_number> [<label_number> ...]")
        print("Example: python tdhca_lookup.py ABC123456")
        sys.exit(1)

    asyncio.run(run(args, as_json))


if __name__ == "__main__":
    main()
