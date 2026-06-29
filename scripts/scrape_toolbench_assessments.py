#!/usr/bin/env python3
"""ToolBench assessment pages: discover URLs from search (with pagination) or scrape a URL list.

Intended for maintainers saving copies of pages relevant to their own servers (see repo README:
ToS, rate limits). The "discover" / "full" modes follow search results and may list many third-party
URLs — prefer "scrape" with a hand-written urls.txt of only your report URLs if you want minimal scope.

Respect the site: use --delay-seconds and --jitter-seconds; avoid parallel runs against production.

  python scrape_toolbench_assessments.py discover --search-url "..." --out-dir ./out
  python scrape_toolbench_assessments.py scrape --urls-file urls.txt --out-dir ./out
  python scrape_toolbench_assessments.py full --search-url "..." --out-dir ./out
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.sync_api import Page, sync_playwright
except ImportError as e:  # pragma: no cover
    print(
        "Install Playwright: pip install playwright (or pip install -e \".[scraper]\" from "
        "toolbench-mcp) ; python -m playwright install chromium",
        file=sys.stderr,
    )
    raise SystemExit(1) from e

TOOLBENCH_HOST = "toolbench.arcade.dev"
# Paths we never treat as per-server assessment pages.
EXCLUDE_PATH_SUBSTR = (
    "/methodology",
    "/improve",
    "/submit",
    "/integrations",
    "/api-access",
    "/sign-in",
    "/signin",
    "/privacy",
    "/terms",
    "/api/",  # OAuth / auth callbacks (false positives in link harvest)
    "/api/auth",
)
# If path contains one of these, more likely a server detail page (Arcade may change).
LINK_HINT_PATH_PARTS = ("/tools/", "/server/", "/servers/", "/mcp/", "/evaluate/", "/score/")


def _sleep_polite(base: float, jitter: float) -> None:
    extra = random.uniform(0.0, jitter) if jitter > 0 else 0.0
    time.sleep(base + extra)


def _is_candidate_assessment_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https"):
        return False
    if p.netloc != TOOLBENCH_HOST and not p.netloc.endswith("." + TOOLBENCH_HOST):
        return False
    path = (p.path or "/").rstrip("/") or "/"
    if path == "/":
        return False
    low = path.lower()
    if low.startswith("/api/"):
        return False
    for ex in EXCLUDE_PATH_SUBSTR:
        if ex in low:
            return False
    # Prefer links that look like entity pages; allow any multi-segment path if not excluded.
    if any(part in low for part in LINK_HINT_PATH_PARTS):
        return True
    segments = [s for s in path.split("/") if s]
    return len(segments) >= 2


def collect_links_from_results_page(page: Page) -> set[str]:
    """Links inside the results UI (table / rows). Falls back to all internal toolbench links."""
    found: set[str] = set()

    def add_from_js(selector: str) -> None:
        hrefs = page.evaluate(
            """(sel) => {
              const nodes = document.querySelectorAll(sel);
              const out = [];
              for (const a of nodes) {
                if (a.href) out.push(a.href.split('#')[0]);
              }
              return out;
            }""",
            selector,
        )
        for h in hrefs:
            if _is_candidate_assessment_url(h):
                found.add(h)

    for sel in (
        "table a[href]",
        '[role="row"] a[href]',
        "tbody a[href]",
        'main a[href^="https://toolbench.arcade.dev/"]',
    ):
        add_from_js(sel)
        if found:
            break

    if not found:
        hrefs = page.evaluate(
            """() => {
              const out = [];
              for (const a of document.querySelectorAll('a[href]')) {
                const h = a.href;
                if (h && h.includes('toolbench.arcade.dev')) out.push(h.split('#')[0]);
              }
              return out;
            }"""
        )
        for h in hrefs:
            if _is_candidate_assessment_url(h):
                found.add(h)

    return found


def click_next_page(page: Page) -> bool:
    selectors = (
        'button:has-text("Next")',
        'a:has-text("Next")',
        '[aria-label="Next page"]',
        'button[aria-label*="Next" i]',
        'a[aria-label*="next" i]',
        '[data-testid*="next" i]',
    )
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() == 0:
                continue
            if not loc.is_visible():
                continue
            if loc.is_disabled():
                continue
        except Exception:
            continue
        try:
            loc.click()
            page.wait_for_load_state("networkidle", timeout=60_000)
            return True
        except Exception:
            continue
    return False


def discover_urls(
    search_url: str,
    out_dir: Path,
    max_pages: int,
    delay_seconds: float,
    jitter_seconds: float,
    headless: bool,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_links: set[str] = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.goto(search_url, wait_until="domcontentloaded", timeout=120_000)
        try:
            page.wait_for_load_state("networkidle", timeout=90_000)
        except Exception:
            pass
        page.wait_for_timeout(2500)

        for page_num in range(max_pages):
            batch = collect_links_from_results_page(page)
            all_links |= batch
            if page_num + 1 < max_pages:
                _sleep_polite(delay_seconds, jitter_seconds)
                if not click_next_page(page):
                    break
                page.wait_for_timeout(1500)
                try:
                    page.wait_for_load_state("networkidle", timeout=60_000)
                except Exception:
                    pass

        browser.close()

    ordered = sorted(all_links)
    (out_dir / "urls.txt").write_text("\n".join(ordered) + ("\n" if ordered else ""), encoding="utf-8")
    return ordered


def _grade_guess(text: str) -> str | None:
    m = re.search(r"\bGrade\s*[:.]?\s*([A-F][+]?)\b", text, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b([A-F][+]?)\s*grade\b", text, re.I)
    if m:
        return m.group(1).upper()
    return None


def scrape_one_page(
    page: Page,
    url: str,
    save_html: bool,
    pages_dir: Path,
) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    try:
        page.wait_for_load_state("networkidle", timeout=90_000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    title = page.title()
    main = page.locator("main").first
    try:
        if main.count() and main.is_visible():
            main_text = main.inner_text()
            raw_html = main.evaluate("el => el.innerHTML")
        else:
            body = page.locator("body")
            main_text = body.inner_text()
            raw_html = body.evaluate("el => el.innerHTML")
    except Exception:
        main_text = page.content()
        raw_html = ""

    excerpt = (main_text or "")[:12000]
    internal = page.evaluate(
        """() => {
          const out = [];
          for (const a of document.querySelectorAll('a[href]')) {
            const h = a.href;
            if (h && h.includes('toolbench.arcade.dev')) out.push(h.split('#')[0]);
          }
          return [...new Set(out)];
        }"""
    )

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", urlparse(url).path.strip("/"))[:120] or "page"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"{stamp}_{slug}"

    payload = {
        "url": url,
        "title": title,
        "fetched_at": datetime.now(UTC).isoformat(),
        "grade_guess": _grade_guess(excerpt),
        "main_text_excerpt": excerpt,
        "links_internal": internal[:200],
    }
    json_path = pages_dir / f"{base}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if save_html and raw_html:
        gz_path = pages_dir / f"{base}.html.gz"
        gz_path.write_bytes(gzip.compress(raw_html.encode("utf-8", errors="replace")))

    md_path = pages_dir / f"{base}.md"
    md_lines = [
        f"# {title}",
        "",
        f"- **URL:** {url}",
        f"- **Grade (regex guess):** {payload['grade_guess'] or '—'}",
        "",
        "## Excerpt",
        "",
        "```",
        excerpt[:6000],
        "```",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return payload


def scrape_urls(
    urls: list[str],
    out_dir: Path,
    delay_seconds: float,
    jitter_seconds: float,
    headless: bool,
    save_html: bool,
) -> None:
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        for i, url in enumerate(urls):
            if i > 0:
                _sleep_polite(delay_seconds, jitter_seconds)
            try:
                scrape_one_page(page, url.strip(), save_html, pages_dir)
            except Exception as e:
                err = {"url": url, "error": str(e), "fetched_at": datetime.now(UTC).isoformat()}
                (pages_dir / f"error_{i}.json").write_text(json.dumps(err, indent=2) + "\n", encoding="utf-8")
        browser.close()


def _read_urls_file(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def main() -> None:
    ap = argparse.ArgumentParser(description="ToolBench assessment scraper (Playwright, rate-limited)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="Collect assessment URLs from a search results page (paginated)")
    d.add_argument("--search-url", required=True)
    d.add_argument("--out-dir", type=Path, default=Path("./toolbench_scrape_out"))
    d.add_argument("--max-pages", type=int, default=25)
    d.add_argument("--delay-seconds", type=float, default=3.0, help="Base pause between navigations")
    d.add_argument("--jitter-seconds", type=float, default=2.0, help="Random extra pause 0..N")
    d.add_argument("--headed", action="store_true", help="Show browser (debug)")

    s = sub.add_parser("scrape", help="Fetch each URL from a file and save JSON/MD")
    s.add_argument("--urls-file", type=Path, required=True)
    s.add_argument("--out-dir", type=Path, default=Path("./toolbench_scrape_out"))
    s.add_argument("--delay-seconds", type=float, default=3.0)
    s.add_argument("--jitter-seconds", type=float, default=2.0)
    s.add_argument("--save-html", action="store_true", help="Gzip inner HTML per page (large)")
    s.add_argument("--headed", action="store_true")

    f = sub.add_parser("full", help="discover then scrape")
    f.add_argument("--search-url", required=True)
    f.add_argument("--out-dir", type=Path, default=Path("./toolbench_scrape_out"))
    f.add_argument("--max-pages", type=int, default=25)
    f.add_argument("--delay-seconds", type=float, default=4.0)
    f.add_argument("--jitter-seconds", type=float, default=2.0)
    f.add_argument("--save-html", action="store_true")
    f.add_argument("--headed", action="store_true")

    args = ap.parse_args()
    headless = not getattr(args, "headed", False)

    if args.cmd == "discover":
        n = len(
            discover_urls(
                args.search_url,
                args.out_dir,
                args.max_pages,
                args.delay_seconds,
                args.jitter_seconds,
                headless,
            )
        )
        print(f"Discover done: {n} URLs -> {args.out_dir / 'urls.txt'}")

    elif args.cmd == "scrape":
        urls = _read_urls_file(args.urls_file)
        scrape_urls(urls, args.out_dir, args.delay_seconds, args.jitter_seconds, headless, args.save_html)
        print(f"Scrape done: {len(urls)} URLs -> {args.out_dir / 'pages'}")

    elif args.cmd == "full":
        urls = discover_urls(
            args.search_url,
            args.out_dir,
            args.max_pages,
            args.delay_seconds,
            args.jitter_seconds,
            headless,
        )
        if not urls:
            print("No URLs discovered; check --search-url or paste URLs into urls.txt and use scrape.", file=sys.stderr)
            raise SystemExit(2)
        scrape_urls(urls, args.out_dir, args.delay_seconds, args.jitter_seconds, headless, args.save_html)
        print(f"Full run done: {len(urls)} pages -> {args.out_dir / 'pages'}")


if __name__ == "__main__":
    main()
