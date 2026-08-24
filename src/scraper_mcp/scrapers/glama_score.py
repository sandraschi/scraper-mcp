"""Glama score page scraper - parses per-tool TDQS dimensions from the /score page.

Ported from glama-status-mcp's scraper.py - fetches the HTML score page
and extracts per-tool grades, 6 TDQS dimension scores, and metadata.
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

    soup = BeautifulSoup(resp.text, "lxml")

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

    # Grade badges
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
            elif "Tool Definition Quality" in ptext:
                result["tdqs_grade"] = badge_text

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

    # TDQS mean/min
    for el in soup.find_all(["p", "div", "span"]):
        txt = el.get_text(strip=True)
        if "Average" in txt and "Lowest" in txt:
            m_mean = re.search(r"Average\s*([\d.]+)\s*/?\s*5", txt)
            m_min = re.search(r"Lowest:\s*([\d.]+)\s*/?\s*5", txt)
            if m_mean:
                result["tdqs_mean"] = float(m_mean.group(1))
            if m_min:
                result["tdqs_min"] = float(m_min.group(1))
            break

    # Per-tool scores
    tools = []
    for btn in soup.find_all("button"):
        classes = " ".join(btn.get("class", []))
        if "ULqjq" not in classes:
            continue
        link = btn.find("a", href=re.compile(r"/tools/"))
        if not link:
            continue

        tool_name = link.get_text(strip=True)
        btn_text = btn.get_text(strip=True)
        tool: dict[str, Any] = {
            "name": tool_name,
            "grade": _parse_grade(btn_text),
            "score": _parse_score(btn_text),
        }

        detail = btn.find_next_sibling("div")
        if detail:
            for dim_label, attr in [
                ("Purpose", "purpose"),
                ("Usage Guidelines", "usage_guidelines"),
                ("Behavior", "behavior"),
                ("Parameters", "parameters"),
                ("Conciseness", "conciseness"),
                ("Completeness", "completeness"),
            ]:
                dim_el = detail.find(string=re.compile(f"^{re.escape(dim_label)}$"))
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
