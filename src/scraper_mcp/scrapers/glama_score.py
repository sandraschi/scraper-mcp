"""Glama score page scraper - parses per-tool TDQS dimensions from the server page.

Rewritten 2026-09-15 for Glama's 2026-07 site redesign. The dedicated `/score`
sub-page now 302-redirects to the main server page (`/mcp/servers/{owner}/{repo}`),
and TDQS data moved there. Verified against live HTML on 2026-09-15:

- Per-tool entries are `<details id="{tool_name}">` (was `<button class="ULqjq">`
  pre-redesign) whose `<summary>` holds the tool-name `<a href=".../tools/...">`
  and a grade badge (`<span class="...kIIaya...">` with bare-letter text). Each
  tool's own TDQS mini-section (overall score + 6 dimension cards) lives nested
  inside the same `<details>`, not as a following sibling `<div>`.
- The server-level overall TDQS lives in `<div id="tool-definition-quality">`,
  with an `<h2>TDQS</h2>` next to a grade badge + `X/5.0` score, plus a
  "Scored <date> across N tools" line giving a real freshness timestamp.
- The `czikZZ` (dimension score span) and `gMBAYo` (dimension card wrapper)
  classes survived the redesign unchanged; only the per-tool container markup
  changed. The old "Average X/5 ... Lowest: X/5" summary text is gone - overall
  mean/min are now derived from the server-level score plus the collected
  per-tool scores instead of scraped from that sentence.

Class names are Glama's build-hashed CSS-module output and WILL drift again on
their next redesign - if this breaks, re-verify against a live page fetch
before assuming the site removed the data outright (it moved once already).
"""

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

GLAMA_BASE = "https://glama.ai"
_USER_AGENT = "scraper-mcp/0.1 (fleet monitor; polite daily scrape)"


def _parse_grade(text: str) -> str:
    m = re.search(r"\b[ABCDF]\b", text)
    return m.group(0) if m else ""


def _parse_score(text: str) -> float:
    m = re.search(r"([\d.]+)\s*/\s*5", text)
    return float(m.group(1)) if m else 0.0


async def scrape_score_page(owner: str, repo: str, slug: str = "") -> dict[str, Any] | None:
    """Fetch and parse a Glama score page.

    Returns dict with:
      grade, score, url, status, tools (count),
      tdqs_mean, tdqs_min, coherence_grade, maintenance_grade,
      tool_details (list of per-tool breakdowns).
    Returns None if 404 or unreachable.
    """
    path = slug or repo
    url = f"{GLAMA_BASE}/mcp/servers/{owner}/{path}/score"
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html"}

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, http2=False) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception:
            return None

    return parse_score_html(resp.text, url=url)


def parse_score_html(html: str, url: str = "") -> dict[str, Any]:
    """Parse a Glama server-page HTML string into the score dict.

    Split out from scrape_score_page so tests can run against a committed
    HTML fixture with no live HTTP call - see tests/test_glama_parser.py.
    """
    soup = BeautifulSoup(html, "lxml")

    result: dict[str, Any] = {
        "url": url,
        "status": "indexed",
    }

    # Profile completion %
    el = soup.find(string=re.compile(r"(\d+)%"))
    if el:
        m = re.search(r"(\d+)%", str(el))
        if m:
            result["profile_completion"] = int(m.group(1))

    # Latest release
    el = soup.find(string=re.compile(r"Latest release", re.I))
    if el and el.parent:
        m = re.search(r"v?[\d]+\.[\d]+\.[\d]+[^\s]*", el.parent.get_text(strip=True))
        if m:
            result["latest_release"] = m.group(0)

    # Server-level overall TDQS: <div id="tool-definition-quality"> holds an
    # <h2>TDQS</h2>, a grade badge + X/5.0 score, and a "Scored <date> across
    # N tools" line. Post-redesign this replaces the old flat grade-badge scan
    # for "Tool Definition Quality" (that heading is now a sibling, not a
    # shared-parent of the badge, so text-in-parent no longer matches it).
    tdqs_section = soup.find(id="tool-definition-quality")
    if tdqs_section:
        badge = tdqs_section.find("span", class_=lambda c: c and "kIIaya" in str(c))
        if badge:
            bt = badge.get_text(strip=True)
            if bt in ("A", "B", "C", "D", "F"):
                result["tdqs_grade"] = bt
        score_span = tdqs_section.find("span", class_=lambda c: c and "czikZZ" in str(c) and "jrPWok" in str(c))
        if score_span:
            result["tdqs_mean"] = _parse_score(score_span.get_text(strip=True))
        scored_text = tdqs_section.get_text(" ", strip=True)
        m_date = re.search(r"Scored\s+([\d-]+\s+[\d:]+)", scored_text)
        if m_date:
            result["scored_at"] = m_date.group(1)

    # Maintenance / coherence-style grade badges elsewhere on the page (best
    # effort - "Server Coherence" as a distinct labeled grade no longer
    # appears post-redesign; kept for forward compatibility if it returns).
    for badge in soup.find_all("span", class_=lambda c: c and "kIIaya" in str(c)):
        badge_text = badge.get_text(strip=True)
        if badge_text not in ("A", "B", "C", "D", "F"):
            continue
        parent = badge.parent
        if parent:
            ptext = parent.get_text(strip=True)
            if "Server Coherence" in ptext:
                result["coherence_grade"] = badge_text
            elif "Maintenance" in ptext:
                result["maintenance_grade"] = badge_text

    # Coherence sub-scores
    coherence_labels = {"Disambiguation", "Naming Consistency", "Tool Count", "Completeness"}
    for span in soup.find_all("span", class_=lambda c: c and "czikZZ" in str(c)):
        st = span.get_text(strip=True)
        m = re.search(r"^(\d+(?:\.\d+)?)\s*/\s*5$", st)
        if not m:
            continue
        parent = span.parent
        if not parent:
            continue
        parent_text = parent.get_text(strip=True)
        for label in coherence_labels:
            if label in parent_text:
                val = float(m.group(1))
                key = f"coherence_{label.lower().replace(' ', '_')}"
                result[key] = val
                break

    # Per-tool scores. Post-redesign each tool is a <details id="{tool_name}">
    # whose <summary> holds the name link + grade badge; its own TDQS overall
    # score and 6 dimension cards are nested INSIDE the same <details>, not a
    # following sibling <div> (that was the pre-redesign <button> layout).
    tools = []
    for det in soup.find_all("details"):
        link = det.find("a", href=re.compile(r"/tools/"))
        if not link:
            continue

        tool_name = link.get_text(strip=True)
        summary = det.find("summary")

        grade = ""
        search_scope = summary or det
        for span in search_scope.find_all("span", class_=lambda c: c and "kIIaya" in str(c)):
            t = span.get_text(strip=True)
            if t in ("A", "B", "C", "D", "F"):
                grade = t
                break

        score = 0.0
        score_span = det.find("span", class_=lambda c: c and "czikZZ" in str(c) and "jrPWok" in str(c))
        if score_span:
            score = _parse_score(score_span.get_text(strip=True))

        tool: dict[str, Any] = {"name": tool_name, "grade": grade, "score": score}

        for dim_label, attr in [
            ("Purpose", "purpose"),
            ("Usage Guidelines", "usage_guidelines"),
            ("Behavior", "behavior"),
            ("Parameters", "parameters"),
            ("Conciseness", "conciseness"),
            ("Completeness", "completeness"),
        ]:
            dim_el = det.find(string=re.compile(f"^{re.escape(dim_label)}$"))
            if dim_el:
                card = dim_el.find_parent("div", class_=lambda c: c and "gMBAYo" in str(c))
                if card:
                    span = card.find("span", class_=lambda c: c and "czikZZ" in str(c))
                    if span:
                        tool[attr] = _parse_score(span.get_text(strip=True))

        if tool.get("score", 0) > 0 or tool.get("grade", ""):
            tools.append(tool)

    result["tools"] = len(tools)
    result["tool_details"] = tools

    # tdqs_min: no longer available as scraped text (the old "Lowest: X/5"
    # sentence is gone from the redesign) - derive it from the per-tool
    # scores we just collected instead, which is more robust anyway.
    if tools:
        tool_scores = [t["score"] for t in tools if t.get("score", 0) > 0]
        if tool_scores:
            result["tdqs_min"] = min(tool_scores)
            result.setdefault("tdqs_mean", round(sum(tool_scores) / len(tool_scores), 2))

    # Compute overall from TDQS
    tdqs_mean = result.get("tdqs_mean")
    tdqs_min = result.get("tdqs_min")
    if tdqs_mean and tdqs_min:
        overall = 0.6 * tdqs_mean + 0.4 * tdqs_min
        result["score"] = round(overall, 2)
        result["grade"] = (
            "A"
            if overall >= 3.5
            else "B"
            if overall >= 3.0
            else "C"
            if overall >= 2.0
            else "D"
            if overall >= 1.0
            else "F"
        )
    elif tools:
        scores = [t["score"] for t in tools if t.get("score", 0) > 0]
        if scores:
            overall = 0.6 * (sum(scores) / len(scores)) + 0.4 * min(scores)
            result["score"] = round(overall, 2)
            result["grade"] = (
                "A"
                if overall >= 3.5
                else "B"
                if overall >= 3.0
                else "C"
                if overall >= 2.0
                else "D"
                if overall >= 1.0
                else "F"
            )

    return result
