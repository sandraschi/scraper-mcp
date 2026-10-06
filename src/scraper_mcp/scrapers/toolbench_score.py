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

# v2 assessment pages (rubric v2, ~2026-09) are Next.js flight-data pages. The v1
# method-string anchors ("Pattern-based scoring", ...) no longer exist on live
# pages. Robust anchors are the data strings themselves, matched on FLATTENED
# page text (soup.get_text(" ", strip=True) joins everything with spaces, so
# there are no pipe separators — verified live 2026-10-06):
#   header:  "6 tools C 68 /100 Definition Quality 70 Protocol Readiness 82 ..."
#   history: "2026-09-22: 68/100 (C) · v2 rubric"
#   tools:   "tool_extract_links read only source verified 72 /100 Extract ..."
# (see docs/TOOLBENCH_V2_REWRITE_20261006.md). The grade letter is deliberately
# NOT captured (A.2 gate: grade from API only).
_HEADER_RE = re.compile(
    r"(\d+)\s*/100\s*Definition Quality\s*(\d+)"
    r"\s*Protocol Readiness\s*(\d+)"
    r"\s*Supportability\s*(\d+)"
)
_HISTORY_RE = re.compile(r"(\d{4}-\d{2}-\d{2}):\s*(\d+)/100\s*\(([A-Z]\+?)\)\s*·\s*(v\d+)\s*rubric")
_TOOL_ROW_STRICT_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]{2,})\s+read only\s+source verified\s+(\d+)\s*/100")
_TOOLS_COUNT_RE = re.compile(r"Tools\s*\((\d+)\)")

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

    # v2 header strip: overall + 3 dimensions in one unambiguous sequence.
    # Grade letter deliberately not captured (A.2 gate: grade from API only).
    header = _HEADER_RE.search(text)
    if header:
        result["overall_score"] = float(header.group(1))
        result["definition_score"] = float(header.group(2))
        result["protocol_score"] = float(header.group(3))
        result["supportability_score"] = float(header.group(4))
    else:
        result["overall_score"] = None
        result["definition_score"] = None
        result["protocol_score"] = None
        result["supportability_score"] = None

    # Score history: dated entries, newest last; latest rubric tag surfaced.
    history = [{"date": d, "score": float(s), "grade": g, "rubric": r} for d, s, g, r in _HISTORY_RE.findall(text)]
    result["score_history"] = history
    result["rubric"] = history[-1]["rubric"] if history else None

    issues: list[str] = []
    # v2: severity badges are SSR'd DOM (span.sev in div.issue-head).
    for head in soup.find_all("div", class_=lambda c: c and "issue-head" in str(c)):
        block = head.find_parent("div")
        if block is not None:
            txt = block.get_text(" ", strip=True)
            if len(txt) > 30:
                issues.append(txt[:400])
                if len(issues) >= 10:
                    break
    if not issues:
        # Fallback: severity-badge neighborhoods in flattened text.
        for badge in re.finditer(r"(HIGH|MEDIUM|LOW|CRITICAL)", text, re.I):
            window = text[max(0, badge.start() - 40) : badge.end() + 360].strip()
            if len(window) > 60:
                issues.append(window[:400])
                if len(issues) >= 10:
                    break
    result["top_issues"] = issues[:10]

    tools = []
    # Scope row search to the catalog region (after "Tools (N)") so header and
    # score-history numbers can never match as tool rows.
    count_match = _TOOLS_COUNT_RE.search(text)
    result["expected_tool_count"] = int(count_match.group(1)) if count_match else None
    tools_text = text[count_match.end() :] if count_match else text
    for row in _TOOL_ROW_STRICT_RE.finditer(tools_text):
        name, score = row.group(1), float(row.group(2))
        if len(name) < 100:
            tools.append({"name": name, "tool_score": score})
    # Dedupe (flight payloads may repeat rows), preserving order.
    seen: set[str] = set()
    uniq_tools = []
    for tool in tools:
        if tool["name"] not in seen:
            seen.add(tool["name"])
            uniq_tools.append(tool)
    tools = uniq_tools
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
        detail["score"] = api_data.get("overallScore") or detail.get("overall_score")
    if detail.get("status") in (None, "", "unknown"):
        detail["status"] = api_data.get("status", "unknown")
    if not detail.get("tools"):
        detail["tools"] = api_data.get("toolCount", 0)
    detail["grade"] = resolve_grade(api_data.get("grade"), detail.get("score"))
    detail["url"] = f"{TOOLBENCH_BASE}/tools/{server_id}"
    return detail
