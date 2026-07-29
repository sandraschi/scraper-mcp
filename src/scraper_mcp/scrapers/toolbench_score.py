"""ToolBench assessment page scraper — parses detailed report from /tools/{id}.

ToolBench assessment pages ARE server-rendered (can be fetched with plain HTTP).
The API at /api/servers?q=<repo> returns the server ID, then /tools/{id}
has the full report with dimension scores, top issues, and per-tool risk.
"""

import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

TOOLBENCH_BASE = "https://toolbench.arcade.dev"
_USER_AGENT = "scraper-mcp/0.1 (fleet monitor; polite daily scrape)"

# Full on-page labels. The short forms ("Definition") do not match, because the
# rendered text reads "Definition Quality 62", not "Definition 62".
_DIMENSION_LABELS = {
    "definition_score": "Definition Quality",
    "protocol_score": "Protocol Readiness",
    "supportability_score": "Supportability",
}

# Published at https://toolbench.arcade.dev/methodology
_GRADE_CUTS = ((90.0, "A+"), (80.0, "A"), (70.0, "B"), (60.0, "C"), (50.0, "D"))


def grade_from_score(score: float | None) -> str:
    """Map an overall score to a ToolBench letter grade.

    A+ >= 90, A >= 80, B >= 70, C >= 60, D >= 50, F below 50.
    """
    if score is None:
        return "?"
    for cut, letter in _GRADE_CUTS:
        if score >= cut:
            return letter
    return "F"


def resolve_grade(api_grade: str | None, score: float | None) -> str:
    """Prefer the API's own grade, else derive it from the score.

    The grade is never taken from page text. The previous implementation matched
    the first grade letter appearing anywhere on the page, in A-first order, so
    any stray standalone "A" in nav or prose won.
    """
    derived = grade_from_score(score)
    if api_grade and api_grade not in ("?", ""):
        if derived != "?" and derived != api_grade:
            log.warning(
                "ToolBench grade/score disagree: api_grade=%s score=%s derived=%s",
                api_grade,
                score,
                derived,
            )
        return api_grade
    return derived


def _extract_pct(text: str, label: str) -> float | None:
    """First non-percentage number after `label`. None when absent.

    The rendered page has the methodology weight (e.g. "50%") immediately
    after the label and the actual score (e.g. "79") further on.  This
    function skips numbers immediately followed by '%' so it returns the
    real score, not the weight.
    """
    idx = text.find(label)
    if idx == -1:
        return None
    tail = text[idx + len(label) :]
    for m in re.finditer(r"(\d+(?:\.\d+)?)", tail):
        end = m.end()
        if end < len(tail) and tail[end:].lstrip().startswith("%"):
            continue
        return float(m.group(1))
    return None


def _match_server(servers: list[dict], repo: str) -> dict | None:
    """Find a repo in the /api/servers result by matching on candidate fields.

    Tries exact name match (preferring SCORED), then full_name suffix match
    (e.g. 'sandraschi/blender-mcp' ends with '/blender-mcp'), then slug
    fallback. Logs the payload when every matcher misses so mis-matches are
    visible rather than silent.
    """
    repo_lower = repo.lower()
    if not servers:
        return None

    scored = [s for s in servers if s.get("name", "").lower() == repo_lower and s.get("status") == "SCORED"]
    if scored:
        return scored[0]

    # Exact name match (any status)
    for s in servers:
        if s.get("name", "").lower() == repo_lower:
            return s

    # full_name suffix or contains match
    for s in servers:
        fn = s.get("full_name", "").lower()
        if fn and (fn == repo_lower or fn.endswith(f"/{repo_lower}")):
            return s

    # slug match
    for s in servers:
        if s.get("slug", "").lower() == repo_lower:
            return s

    log.warning(
        "no server match for %r in %d /api/servers results (names: %r)",
        repo,
        len(servers),
        [s.get("name", "?") for s in servers[:5]],
    )
    return None


async def scrape_assessment(server_id: str) -> dict[str, Any] | None:
    """Scrape a ToolBench assessment page for detailed report data.

    Returns dict with grade, trust_score, dimension scores, top issues, tools.
    """
    url = f"{TOOLBENCH_BASE}/tools/{server_id}"
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html"}

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, http2=False) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 302):
                return None
            raise
        except Exception:
            return None

    soup = BeautifulSoup(resp.text, "lxml")
    # The separator is required. get_text(strip=True) concatenates with nothing
    # between nodes, so "Definition Quality 62" collapses to "DefinitionQuality62"
    # and every label regex misses.
    text = soup.get_text(" ", strip=True)

    result: dict[str, Any] = {
        "url": url,
        "server_id": server_id,
    }

    # The grade is deliberately NOT scraped here. It is resolved from the API
    # grade, or derived from the score, in fetch_grade_with_details().

    # Trust score comes from API overallScore, not scraped from HTML

    # Dimension scores, keyed by the full label as rendered on the page.
    for key, label in _DIMENSION_LABELS.items():
        result[key] = _extract_pct(text, label)

    # Top Issues — find the issues container (class="space-y-2" near "Top Issues")
    issues = []
    issues_header = soup.find(string=re.compile(r"Top Issues"))
    if issues_header:
        section = issues_header.find_parent(["div", "section"])
        if section:
            issues_container = section.find("div", class_=lambda c: c and "space-y-2" in str(c))
            if issues_container:
                for child in issues_container.find_all(["div", "li"], recursive=False):
                    txt = child.get_text(strip=True)
                    if len(txt) > 30:
                        issues.append(txt[:400])
                        if len(issues) >= 10:
                            break
            else:
                for child in section.find_all(["div", "li"], recursive=False):
                    txt = child.get_text(strip=True)
                    if len(txt) > 30 and any(sev in txt[:20].lower() for sev in ["critical", "high", "medium", "low"]):
                        issues.append(txt[:400])
                        if len(issues) >= 10:
                            break

    result["top_issues"] = issues[:10]

    # Tool table — find risk scores
    tools = []
    # Try finding the tools section
    tool_section = soup.find(string=re.compile(r"Tools\s*\("))
    if not tool_section:
        tool_section = soup.find(string=re.compile(r"Function\s+Description\s+Risk"))
    if tool_section:
        section = tool_section.find_parent(["div", "section"])
        if section:
            for row in section.find_all(["tr", "div"], class_=lambda c: c and "row" in str(c).lower() if c else False):
                cells = row.find_all(["td", "div"])
                if len(cells) >= 2:
                    name = cells[0].get_text(strip=True)
                    risk = 0
                    for c in cells:
                        rm = re.search(r"(\d+)", c.get_text(strip=True))
                        if rm:
                            risk = float(rm.group(1))
                    if name and len(name) < 100:
                        tools.append({"name": name, "risk_score": risk})
            if not tools:
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        name = cells[0].get_text(strip=True)
                        risk = _extract_number(cells[-1].get_text(strip=True)) if cells[-1] else 0
                        if name and len(name) < 100:
                            tools.append({"name": name, "risk_score": risk})

    result["tools"] = len(tools)
    result["tool_details"] = tools

    return result


def _extract_number(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


async def fetch_grade_with_details(owner: str, repo: str) -> dict[str, Any] | None:
    """Combined: search API for server ID, then scrape assessment page.

    Makes exactly one call to /api/servers?q=<repo>. The result is reused
    for both server-id discovery and API data fields (score, grade, status,
    tool count). The doubled-API-call defect is eliminated.
    """
    # Single API call — reused for both id lookup and data extraction
    async with httpx.AsyncClient(timeout=15, http2=False) as client:
        r = await client.get(
            f"{TOOLBENCH_BASE}/api/servers",
            params={"q": repo},
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        servers = data.get("servers", data.get("data", []))
        if not isinstance(servers, list):
            return None

    api_data = _match_server(servers, repo)
    if not api_data:
        return None

    server_id = api_data.get("id")
    if not server_id:
        return None

    # Scrape detailed assessment
    detail = await scrape_assessment(server_id)
    if not detail:
        return {
            "grade": resolve_grade(api_data.get("grade"), api_data.get("overallScore")),
            "score": api_data.get("overallScore"),
            "url": f"{TOOLBENCH_BASE}/tools/{server_id}",
            "status": api_data.get("status", "unknown"),
            "tools": api_data.get("toolCount", 0),
            "server_id": server_id,
        }

    if detail.get("score") is None:
        detail["score"] = api_data.get("overallScore")
    if detail.get("status") in (None, "", "unknown"):
        detail["status"] = api_data.get("status", "unknown")
    if not detail.get("tools"):
        detail["tools"] = api_data.get("toolCount", 0)
    detail["grade"] = resolve_grade(api_data.get("grade"), detail.get("score"))
    detail["url"] = f"{TOOLBENCH_BASE}/tools/{server_id}"
    return detail
