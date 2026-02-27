#!/usr/bin/env python3
"""
ZJU College Bulletin Board Scraper
Scrapes the latest notices from ZJU college websites and outputs docs/data.json
"""

import json
import os
import time
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

# ─── College configuration ────────────────────────────────────────────────────
COLLEGES = [
    {
        "id": "sis",
        "name": "外国语学院",
        "list_url": "http://www.sis.zju.edu.cn/sischinese/12577/list.htm",
        "base_url": "http://www.sis.zju.edu.cn",
    },
    {
        "id": "cs",
        "name": "计算机科学与技术学院",
        "list_url": "http://cspo.zju.edu.cn/86671/list.htm",
        "base_url": "http://cspo.zju.edu.cn",
    },
    {
        "id": "ckc",
        "name": "竺可桢学院",
        "list_url": "http://ckc.zju.edu.cn/54005/list.htm",
        "base_url": "http://ckc.zju.edu.cn",
    },
]

# How many list pages to fetch per college (each page has ~14-15 items)
PAGES_TO_FETCH = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Regex: ZJU WebPlus article URL pattern  e.g. /2026/0213/c12577a3134640/page.htm
ARTICLE_URL_RE = re.compile(r"/\d{4}/\d{4}/[^/]+/page\.htm$")

# Date pattern in text:  YYYY-MM-DD
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def make_page_url(base_list_url: str, page: int) -> str:
    """Convert list.htm → list2.htm → list3.htm ..."""
    if page == 1:
        return base_list_url
    # e.g.  .../12577/list.htm  →  .../12577/list2.htm
    return base_list_url.replace("/list.htm", f"/list{page}.htm")


def fetch_page(url: str, retries: int = 3) -> BeautifulSoup | None:
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(url, timeout=20)
            # ZJU sites may declare charset in meta; let requests/bs4 handle it
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:
            print(f"  [WARN] attempt {attempt}/{retries} failed for {url}: {exc}")
            time.sleep(3 * attempt)
    return None


def parse_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Extract notice items from a list page.
    ZJU WebPlus CMS structure:  <li><a href="...page.htm">title</a><span>date</span></li>
    """
    items = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=ARTICLE_URL_RE):
        href = a_tag["href"].strip()
        title = a_tag.get_text(strip=True)

        if not title:
            continue

        # Build absolute URL
        if href.startswith("http"):
            full_url = href
        else:
            full_url = base_url.rstrip("/") + href

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Date: look in sibling/parent text for YYYY-MM-DD
        date = ""
        parent = a_tag.parent  # <li>
        if parent:
            # Prefer a <span> sibling containing digits
            for span in parent.find_all("span"):
                m = DATE_RE.search(span.get_text())
                if m:
                    date = m.group()
                    break
            # Fallback: raw text of parent
            if not date:
                m = DATE_RE.search(parent.get_text())
                if m:
                    date = m.group()

        items.append({"title": title, "url": full_url, "date": date})

    return items


def scrape_college(college: dict) -> dict:
    print(f"\n[INFO] Scraping {college['name']} …")
    all_items: list[dict] = []
    seen_urls: set[str] = set()

    for page_no in range(1, PAGES_TO_FETCH + 1):
        page_url = make_page_url(college["list_url"], page_no)
        print(f"  → {page_url}")
        soup = fetch_page(page_url)
        if soup is None:
            print(f"  [ERROR] Could not fetch page {page_no}, skipping.")
            break

        items = parse_items(soup, college["base_url"])
        new_items = [i for i in items if i["url"] not in seen_urls]
        seen_urls.update(i["url"] for i in new_items)
        all_items.extend(new_items)

        if not items:
            print(f"  [WARN] No items found on page {page_no}, stopping pagination.")
            break

        if page_no < PAGES_TO_FETCH:
            time.sleep(1)  # be polite

    print(f"  ✓ collected {len(all_items)} items")
    return {
        "id": college["id"],
        "name": college["name"],
        "source_url": college["list_url"],
        "items": all_items,
    }


def main():
    results = []
    for college in COLLEGES:
        data = scrape_college(college)
        results.append(data)
        time.sleep(2)  # polite delay between colleges

    # China Standard Time (UTC+8)
    cst = timezone(timedelta(hours=8))
    updated_at = datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S CST")

    output = {
        "updated_at": updated_at,
        "colleges": results,
    }

    # Write to docs/data.json (relative to repo root)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(repo_root, "docs", "data.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(c["items"]) for c in results)
    print(f"\n✅  Wrote {total} items to {out_path}")
    print(f"   Updated at: {updated_at}")


if __name__ == "__main__":
    main()
