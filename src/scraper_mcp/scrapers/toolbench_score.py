"""ToolBench assessment page scraper — parses detailed report from /tools/{id}.

ToolBench assessment pages ARE server-rendered (can be fetched with plain HTTP).
The API at /api/servers?q=<repo> returns the server ID, then /tools/{id}
has the full report with dimension scores, top issues, and per-tool risk.
"""

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

TOOLBENCH_BASE = "https://toolbench.arcade.dev"
_USER_AGENT = "scraper-mcp/0.1 (fleet monitor; polite daily scrape)"


def _extract_pct(text: str, label: str) -> float:
    m = re.search(rf"{re.escape(label)}\s*(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


async def search_server_id(repo: str) -> str | None:
    """Search ToolBench API for a repo's server ID."""
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
        # Find our repo by exact name match, prefer SCORED
        scored = [s for s in servers if s.get("name", "").lower() == repo.lower() and s.get("status") == "SCORED"]
        if scored:
            return scored[0]["id"]
        for s in servers:
            if s.get("name", "").lower() == repo.lower():
                return s.get("id", "")
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
    text = soup.get_text(strip=True)

    result: dict[str, Any] = {
        "url": url,
        "server_id": server_id,
    }

    # Grade — find e.g. "F" in grade badge
    for grade in ("A+", "A", "B", "C", "D", "F"):
        m = re.search(rf"\b{re.escape(grade)}\b", text)
        if m:
            result["grade"] = grade
            break

    # Trust score comes from API overallScore, not scraped from HTML

    # Dimension scores: percentages next to "Definition", "Protocol", "Supportability"
    for label in ("Definition", "Protocol", "Supportability"):
        result[f"{label.lower()}_score"] = _extract_pct(text, label)

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

    Returns detailed grade dict or None if not found.
    """
    server_id = await search_server_id(repo)
    if not server_id:
        return None

    # Get basic info from API first
    async with httpx.AsyncClient(timeout=15, http2=False) as client:
        r = await client.get(
            f"{TOOLBENCH_BASE}/api/servers",
            params={"q": repo},
            headers={"Accept": "application/json"},
        )
        api_data = None
        if r.status_code == 200:
            data = r.json()
            servers = data.get("servers", data.get("data", []))
            for s in servers:
                if s.get("id") == server_id:
                    api_data = s
                    break

    # Scrape detailed assessment
    detail = await scrape_assessment(server_id)
    if not detail:
        # Fall back to API data
        if api_data:
            return {
                "grade": api_data.get("grade", "?"),
                "score": api_data.get("overallScore"),
                "url": f"{TOOLBENCH_BASE}/tools/{server_id}",
                "status": api_data.get("status", "unknown"),
                "tools": api_data.get("toolCount", 0),
                "server_id": server_id,
            }
        return None

    # Merge API data into detail
    if api_data:
        detail.setdefault("grade", api_data.get("grade", "?"))
        detail.setdefault("score", api_data.get("overallScore"))
        detail.setdefault("status", api_data.get("status", "unknown"))
        if not detail.get("tools"):
            detail["tools"] = api_data.get("toolCount", 0)
    elif not detail.get("grade"):
        detail["grade"] = "?"
        detail["score"] = None
        detail["status"] = "unknown"

    detail["url"] = f"{TOOLBENCH_BASE}/tools/{server_id}"
    return detail
