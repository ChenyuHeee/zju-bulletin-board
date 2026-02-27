#!/usr/bin/env python3
"""
ZJU College Bulletin Board Scraper
Scrapes the latest notices from ZJU college websites and outputs docs/data.json

WebVPN support (for intranet-only pages):
  Set env vars ZJU_USERNAME and ZJU_PASSWORD (as GitHub Secrets).
  The scraper will log in to webvpn.zju.edu.cn and access intranet URLs.
  If credentials are absent or login fails, a public fallback URL is used.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ─── College configuration ────────────────────────────────────────────────────
# Fields:
#   list_url      – primary notice list URL (public, no auth required)
#   base_url      – base domain for resolving relative links on list_url/fallback_url
#   intranet_url  – (optional) campus-only URL; accessed via WebVPN when available
#   intranet_base – base domain for resolving relative links from intranet pages
#   fallback_url  – public URL used when WebVPN is unavailable
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
        # Original intranet notices (即时更新) – campus network only, accessed via WebVPN
        "intranet_url": "http://cspo.zju.edu.cn/86671/list.htm",
        "intranet_base": "http://cspo.zju.edu.cn",
        # Public fallback: college news (新闻动态) – globally accessible
        "list_url":     "http://www.cs.zju.edu.cn/csen/xwdt_38564/list.htm",
        "base_url":     "http://www.cs.zju.edu.cn",
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

# Global WebVPN session (populated by init_webvpn())
WEBVPN_SESSION: requests.Session | None = None
WEBVPN_AVAILABLE = False


# ─── WebVPN helpers ───────────────────────────────────────────────────────────

def _build_webvpn_url(original_url: str) -> str:
    """http://cspo.zju.edu.cn/86671/list.htm
       → https://webvpn.zju.edu.cn/http/cspo.zju.edu.cn/86671/list.htm"""
    m = re.match(r"(https?)://(.+)", original_url)
    if not m:
        raise ValueError(f"Unrecognised URL: {original_url}")
    return f"https://webvpn.zju.edu.cn/{m.group(1)}/{m.group(2)}"


def _webvpn_login(username: str, password: str) -> requests.Session:
    """Authenticate against ZJU CAS, return a session with WebVPN cookies."""
    sess = requests.Session()
    sess.headers.update(HEADERS)

    cas_url = (
        "https://ids.zju.edu.cn/cas/login"
        "?service=https://webvpn.zju.edu.cn/wengine-vpn/cas"
    )
    log.info("  → Fetching CAS login page …")
    resp = sess.get(cas_url, timeout=20, allow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form", id="cas-form") or soup.find("form")
    if not form:
        raise RuntimeError("CAS login form not found")

    action = form.get("action") or cas_url
    if not action.startswith("http"):
        action = "https://ids.zju.edu.cn" + action

    payload: dict[str, str] = {}
    for inp in form.find_all("input"):
        n, v = inp.get("name", ""), inp.get("value", "")
        if n:
            payload[n] = v
    payload["username"] = username
    payload["password"] = password
    payload.setdefault("_eventId", "submit")

    log.info("  → Submitting credentials …")
    resp = sess.post(action, data=payload, timeout=20, allow_redirects=True)
    resp.raise_for_status()

    if "ids.zju.edu.cn/cas/login" in resp.url:
        err_soup = BeautifulSoup(resp.text, "html.parser")
        err_el = err_soup.find(class_=re.compile(r"errors?|message|alert", re.I))
        msg = err_el.get_text(strip=True) if err_el else "check credentials"
        raise RuntimeError(f"CAS rejected login: {msg}")

    log.info("  → WebVPN login succeeded ✓")
    time.sleep(1)
    return sess


def init_webvpn() -> bool:
    """Try to login to WebVPN. Returns True on success."""
    global WEBVPN_SESSION, WEBVPN_AVAILABLE
    username = os.environ.get("ZJU_USERNAME", "")
    password = os.environ.get("ZJU_PASSWORD", "")
    if not username or not password:
        log.info("[WebVPN] ZJU_USERNAME/ZJU_PASSWORD not set – skipping.")
        return False
    try:
        WEBVPN_SESSION = _webvpn_login(username, password)
        WEBVPN_AVAILABLE = True
        return True
    except Exception as exc:
        log.warning("[WebVPN] Login failed: %s → using fallback URLs.", exc)
        WEBVPN_SESSION = None
        WEBVPN_AVAILABLE = False
        return False


def _effective_url_and_base(college: dict) -> tuple[str, str]:
    """Return (list_url, base_url) to actually use, based on WebVPN availability."""
    if "intranet_url" in college and WEBVPN_AVAILABLE:
        return college["intranet_url"], college["intranet_base"]
    return college["list_url"], college["base_url"]


# ─── Page fetching ─────────────────────────────────────────────────────────────

def make_page_url(base_list_url: str, page: int) -> str:
    """Convert list.htm → list2.htm → list3.htm …"""
    if page == 1:
        return base_list_url
    return base_list_url.replace("/list.htm", f"/list{page}.htm")


def fetch_page(
    url: str, via_webvpn: bool = False, retries: int = 3
) -> BeautifulSoup | None:
    """Fetch a page and return parsed HTML."""
    fetch_url = _build_webvpn_url(url) if via_webvpn else url
    sess = (WEBVPN_SESSION if via_webvpn and WEBVPN_SESSION else SESSION)
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(fetch_url, timeout=25)
            resp.encoding = resp.apparent_encoding or "utf-8"
            if via_webvpn and "ids.zju.edu.cn/cas/login" in resp.url:
                raise RuntimeError("WebVPN session expired")
            return BeautifulSoup(resp.text, "html.parser")
        except RuntimeError:
            raise
        except Exception as exc:
            log.warning("  [WARN] attempt %d/%d failed for %s: %s",
                        attempt, retries, fetch_url, exc)
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
    list_url, base_url = _effective_url_and_base(college)
    via_webvpn = WEBVPN_AVAILABLE and "intranet_url" in college
    mode = "intranet via WebVPN" if via_webvpn else "public"
    log.info("\n[INFO] Scraping %s (%s) …", college["name"], mode)

    all_items: list[dict] = []
    seen_urls: set[str] = set()

    for page_no in range(1, PAGES_TO_FETCH + 1):
        page_url = make_page_url(list_url, page_no)
        log.info("  → %s", page_url)
        soup = fetch_page(page_url, via_webvpn=via_webvpn)
        if soup is None:
            log.error("  [ERROR] Could not fetch page %d, skipping.", page_no)
            break

        items = parse_items(soup, base_url)
        new_items = [i for i in items if i["url"] not in seen_urls]
        seen_urls.update(i["url"] for i in new_items)
        all_items.extend(new_items)

        if not items:
            log.warning("  [WARN] No items on page %d, stopping.", page_no)
            break

        if page_no < PAGES_TO_FETCH:
            time.sleep(1)

    log.info("  ✓ collected %d items", len(all_items))

    result: dict = {
        "id": college["id"],
        "name": college["name"],
        "source_url": list_url,
        "items": all_items,
    }
    # Warn in UI when showing fallback news instead of real notices
    if "intranet_url" in college and not via_webvpn:
        result["note"] = "⚠️ WebVPN 不可用，当前显示公开新闻（非通知公告）"
    return result


def main() -> None:
    log.info("=== ZJU Bulletin Board Scraper ===")
    webvpn_ok = init_webvpn()
    log.info("[WebVPN] %s", "Session ready ✓" if webvpn_ok else "Not available – using public URLs.")

    results = []
    for college in COLLEGES:
        data = scrape_college(college)
        results.append(data)
        time.sleep(2)

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
    log.info("\n✅  Wrote %d items to %s", total, out_path)
    log.info("   Updated at: %s", updated_at)


if __name__ == "__main__":
    main()
