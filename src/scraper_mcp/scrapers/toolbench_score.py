"""ToolBench assessment page scraper - parses detailed report from /tools/{id}.

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

# In-memory cache: server_id -> GitHub owner, populated on first page fetch.
# Resets on process restart (acceptable - avoids stale or cross-repo leaks).
_server_owner_cache: dict[str, str] = {}

# Tolerance for dimension-score weighted-sum reconciliation.
_RECONCILE_TOLERANCE = 1.5

# Unique per-dimension method strings, appearing exactly once per assessment page.
# The old labels ("Definition Quality", "Protocol Readiness", "Supportability") all
# appear first in the methodology blurb ("Local MCP - Scored on Definition Quality (50%),
# Protocol Readiness (20%), and Supportability (30%)").  _extract_pct scans forward from
# that anchor and always lands on the Definition score for all three, because Protocol
# and Supportability scores come later in the page and the scan hits the Definition
# number first every time.  The method strings below are unique to each dimension row.
_DIMENSION_METHOD_STRINGS = {
    "definition_score": "Pattern-based scoring",
    "protocol_score": "Static analysis",
    "supportability_score": "GitHub signals",
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


def _find_candidates(servers: list[dict], repo: str) -> list[dict]:
    """Return ALL servers matching the repo name, not just the first.

    The API returns every name collision across every author (observed: 3
    different "scraper-mcp" servers by different owners).  This function
    returns all of them.  Owner verification (via assessment page HTML)
    happens in `fetch_grade_with_details` - never guess which one is ours.

    Matching strategy (in order):
    1. Exact name match (case-insensitive), sorted SCORED first.
    2. full_name suffix match (e.g. ends with '/repo-name').
    3. slug match.

    Logs every unmatched candidate so false negatives stay visible.
    """
    repo_lower = repo.lower()
    if not servers:
        return []

    # 1. Exact name matches - prefer SCORED
    exact = [s for s in servers if s.get("name", "").lower() == repo_lower]
    if not exact:
        # 2. full_name suffix
        for s in servers:
            fn = s.get("full_name", "").lower()
            if fn and (fn == repo_lower or fn.endswith(f"/{repo_lower}")):
                exact.append(s)
        # 3. slug match
        if not exact:
            for s in servers:
                if s.get("slug", "").lower() == repo_lower:
                    exact.append(s)

    if exact:
        # Sort: SCORED first, then by overallScore descending
        return sorted(
            exact,
            key=lambda s: (
                0 if s.get("status") == "SCORED" else 1,
                -(s.get("overallScore") or 0),
            ),
        )

    log.warning(
        "no server match for %r in %d /api/servers results (names: %r)",
        repo,
        len(servers),
        [s.get("name", "?") for s in servers[:5]],
    )
    return []


def _owner_from_soup(soup: BeautifulSoup) -> str | None:
    """Extract GitHub owner from the assessment page header.

    The page header contains a link like:
      https://github.com/{owner}/{repo}
    or a text label like:
      mcp:{owner}/{repo}
    """
    # Try the GitHub link first
    link = soup.find("a", href=re.compile(r"github\.com"))
    if link:
        href = link.get("href", "")
        parts = [p for p in href.strip("/").split("/") if p]
        if len(parts) >= 2 and parts[-2] != "github.com":
            return parts[-2]

    # Fallback: mcp:owner/repo label
    label = soup.find(string=re.compile(r"mcp:"))
    if label:
        text = label.string or str(label)
        m = re.search(r"mcp:([^/]+)", text)
        if m:
            return m.group(1)

    return None


def _dimensions_reconcile(
    defn: float | None,
    proto: float | None,
    supp: float | None,
    overall: float | None,
    tol: float = _RECONCILE_TOLERANCE,
) -> bool:
    """Check that dimension scores reconcile to the overall score.

    Published formula: 0.5 * DQ + 0.2 * Protocol + 0.3 * Support = overall.
    If any dimension is None or the weighted sum deviates by more than
    `tol`, returns False.  A warning should be logged by the caller.
    """
    if None in (defn, proto, supp) or overall is None:
        return False
    expected = 0.5 * defn + 0.2 * proto + 0.3 * supp
    return abs(expected - overall) <= tol


def _parse_assessment_data(
    soup: BeautifulSoup,
    url: str,
    server_id: str,
) -> dict[str, Any]:
    """Extract dimension scores, top issues, tool details from page soup.

    Split from scrape_assessment so callers can parse without a second HTTP
    fetch (owner-verification path in fetch_grade_with_details).
    """
    text = soup.get_text(" ", strip=True)

    result: dict[str, Any] = {
        "url": url,
        "server_id": server_id,
    }

    for key, label in _DIMENSION_METHOD_STRINGS.items():
        result[key] = _extract_pct(text, label)

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

    tools = []
    tool_section = soup.find(string=re.compile(r"Tools\s*\("))
    if not tool_section:
        tool_section = soup.find(string=re.compile(r"Function\s+Description\s+Risk"))
    if tool_section:
        section = tool_section.find_parent(["div", "section"])
        if section:
            for row in section.find_all(
                ["tr", "div"],
                class_=lambda c: c and "row" in str(c).lower() if c else False,
            ):
                cells = row.find_all(["td", "div"])
                if len(cells) >= 2:
                    name = cells[0].get_text(strip=True)
                    score = 0
                    for c in cells:
                        rm = re.search(r"(\d+)", c.get_text(strip=True))
                        if rm:
                            score = float(rm.group(1))
                    if name and len(name) < 100:
                        tools.append({"name": name, "tool_score": score})
            if not tools:
                for row in section.find_all("tr"):
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        name = cells[0].get_text(strip=True)
                        score = _extract_number(cells[-1].get_text(strip=True)) if cells[-1] else 0
                        if name and len(name) < 100:
                            tools.append({"name": name, "tool_score": score})
    result["tools"] = len(tools)
    result["tool_details"] = tools
    return result


async def scrape_assessment(server_id: str) -> dict[str, Any] | None:
    """Scrape a ToolBench assessment page.

    Thin wrapper: fetches HTML, delegates to ``_parse_assessment_data``.
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
    return _parse_assessment_data(soup, url, server_id)


def _extract_number(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


async def fetch_grade_with_details(owner: str, repo: str) -> dict[str, Any] | None:
    """Two-stage fetch: resolve server by owner, scrape + reconcile.

    Stage 1 - API call: GET /api/servers?q=<repo>. Collect all name-matching
    candidates (ToolBench returns every author's server with the same name).
    Stage 2 - Owner verification: for each candidate, fetch the assessment
    page and extract the GitHub owner from the page header. Accept only the
    candidate whose owner matches the fleet owner. Cache results in
    ``_server_owner_cache`` so this costs one page fetch per server per
    process lifetime, not per refresh.

    After finding the correct server, parse dimension scores and run a
    weighted-sum reconciliation (0.5*DQ + 0.2*Protocol + 0.3*Support ≈
    overallScore). If dimensions fail the check, they are stored as None
    rather than propagating wrong numbers into the Part B worklist.
    """
    async with httpx.AsyncClient(timeout=15, http2=False) as client:
        r = await client.get(
            f"{TOOLBENCH_BASE}/api/servers",
            params={"q": repo},
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        servers_raw = data.get("servers", data.get("data", []))
        if not isinstance(servers_raw, list):
            return None

    candidates = _find_candidates(servers_raw, repo)
    if not candidates:
        return None

    server_id: str | None = None
    api_data: dict | None = None
    detail: dict | None = None

    for candidate in candidates:
        sid = candidate.get("id")
        if not sid:
            continue

        # Cache hit - skip verification page fetch
        cached_owner = _server_owner_cache.get(sid)
        if cached_owner:
            if cached_owner.lower() == owner.lower():
                server_id = sid
                api_data = candidate
                break
            continue

        # Cache miss - fetch the assessment page to verify owner
        page_url = f"{TOOLBENCH_BASE}/tools/{sid}"
        headers = {"User-Agent": _USER_AGENT, "Accept": "text/html"}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, http2=False) as client:
            try:
                resp = await client.get(page_url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                continue
            except Exception:
                continue

        soup = BeautifulSoup(resp.text, "lxml")
        page_owner = _owner_from_soup(soup)
        if page_owner:
            _server_owner_cache[sid] = page_owner

        if page_owner and page_owner.lower() == owner.lower():
            server_id = sid
            api_data = candidate
            # Parse assessment data from the already-fetched page
            detail = _parse_assessment_data(soup, page_url, server_id)

            # Reconciliation check
            defn = detail.get("definition_score")
            proto = detail.get("protocol_score")
            supp = detail.get("supportability_score")
            overall = detail.get("score") or api_data.get("overallScore")
            if not _dimensions_reconcile(defn, proto, supp, overall):
                log.warning(
                    "%s/%s: dims (%s, %s, %s) fail reconciliation against overall=%s - storing as None",
                    owner,
                    repo,
                    defn,
                    proto,
                    supp,
                    overall,
                )
                for key in ("definition_score", "protocol_score", "supportability_score"):
                    detail[key] = None
            break

    if not server_id or not api_data:
        log.warning(
            "owner=%s %s: no ToolBench candidate matched. Candidates checked: %d",
            owner,
            repo,
            len(candidates),
        )
        return None

    if detail is None:
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
