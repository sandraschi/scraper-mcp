"""scraper_help - multi-level help with basic, advanced, and platform detail."""

from typing import Annotated, Literal

from pydantic import Field

from ..registry import mcp

BASIC = """## scraper-mcp Help (Basic)

This server monitors fleet MCP repo grades across **ToolBench**, **Glama.ai**, and **LobeHub**.

### Quick commands
- `scraper_matrix()` - See all repos and their grades across platforms
- `scraper_refresh()` - Pull fresh grades from all platforms
- `scraper_repo(repo="email-mcp")` - Details for one repo
- `scraper_improve_suggest(repo="email-mcp")` - Get concrete code fixes

### Grade meaning
- **ToolBench**: A+ (90-100) to F (<50). Weighs definition quality 50%, protocol 20%, supportability 30%.
- **Glama**: A (>=3.5) to F (<1.0). 100% docstring quality. 60% mean + 40% minimum across tools.
- **LobeHub**: Presence only - no grades.
"""

ADVANCED = """## scraper-mcp Help (Advanced)

### All MCP Tools

| Tool | Purpose |
|------|---------|
| `scraper_matrix()` | Coverage matrix: repos x platforms with grades |
| `scraper_repo(repo)` | Single-repo detail with history, TDQS dims, risk scores |
| `scraper_refresh(repo=)` | Refresh all (or one) repo grades from platforms |
| `scraper_status()` | Server health, last fetch times, grade distribution |
| `scraper_improvement_plan(repo)` | Prioritized fix list from ToolBench criticisms |
| `scraper_improve_suggest(repo)` | Concrete Python code snippets for each issue |
| `scraper_reassess(repo, platform=)` | Request rescoring on platforms |
| `scraper_platforms(operation)` | List/info/add grading platforms |
| `scraper_help(level)` | This help system |
| `toolbench_guide(operation)` | ToolBench-specific context and links |

### Fleet exceptions (we ignore these ToolBench rules)
- **Portmanteau tools**: ToolBench wants one action per tool. We use typed `operation` params instead. See TOOL_DESIGN_STANDARDS.md.
- **Stdio-only penalty**: ToolBench caps protocol score at 50 for stdio servers. Dual transport (stdio+HTTP) can reach 100.

### Improvement workflow
1. `scraper_improve_suggest(repo="...")` - get concrete fixes
2. Apply fixes in the repo
3. `scraper_refresh(repo="...")` - verify grades updated
4. `scraper_reassess(repo="...", platform="toolbench")` - request rescore
"""

PLATFORM_DETAIL = """## Platform Detail

### ToolBench (toolbench.arcade.dev)
- **Methodology**: Definition Quality 50%, Protocol Readiness 20%, Supportability 30%
- **Grades**: A+ (90-100), A (80-89), B (70-79), C (60-69), D (50-59), F (<50)
- **Rescore**: https://toolbench.arcade.dev/submit (requires Arcade login)
- **Per-tool risk scores**: Higher = more urgent to fix
- **Key patterns**: constrained-input, response-shaper, recovery-guide, param-validation-rules

### Glama.ai (glama.ai)
- **Methodology**: Tool Definition Quality 70% (6 dimensions) + Server Coherence 30%
- **Grades**: A (>=3.5), B (>=3.0), C (>=2.0), D (>=1.0), F (<1.0)
- **6 TDQS dims**: Purpose 25%, Usage 20%, Behavior 20%, Params 15%, Conciseness 10%, Completeness 10%
- **Formula**: 60% mean + 40% minimum across all tools - one bad tool pulls score down
- **Rescore**: Click "Sync Server" on glama.ai admin page (auto-rescans daily)

### LobeHub (lobehub.com)
- **Grades**: None - presence only
- **Purpose**: Discoverability in open-source MCP marketplace
"""


@mcp.tool(annotations={"readOnly": True})
async def scraper_help(
    level: Annotated[
        Literal["basic", "advanced", "platform"],
        Field(
            description="Detail level: basic = commands, advanced = all tools + workflow, platform = per-platform grading detail"
        ),
    ] = "basic",
) -> dict:
    """Multi-level help for scraper-mcp.

    Provides tiered documentation:
    - basic: Quick commands, grade meaning
    - advanced: All MCP tools, fleet exceptions, improvement workflow
    - platform: Per-platform grading methodology, rescore links, dimensions

    ## Return Format
    {"success": bool, "data": {"level": str, "markdown": str}}

    ## Examples
    await scraper_help()
    await scraper_help(level="advanced")
    await scraper_help(level="platform")
    """
    content = {"basic": BASIC, "advanced": ADVANCED, "platform": PLATFORM_DETAIL}.get(level, BASIC)
    return {
        "success": True,
        "data": {"level": level, "markdown": content.strip()},
        "message": f"Help ({level}): {len(content.split(chr(10)))} lines.",
    }
