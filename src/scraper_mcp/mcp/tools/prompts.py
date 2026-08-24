"""@mcp.prompt() and @mcp.resource() registrations."""

from ..registry import mcp


@mcp.prompt()
def scraper_workflow() -> str:
    """Standard scraper-mcp workflow: check status, refresh, review, improve, reassess."""
    return """## Scraper MCP Workflow

1. Check current coverage: `scraper_status()` or `show_status_card()`
2. View coverage matrix: `scraper_matrix()` or `show_matrix_card()`
3. Refresh grades: `scraper_refresh()`
4. Review a specific repo: `scraper_repo(repo="name")`
5. Get improvement suggestions: `scraper_improve_suggest(repo="name")`
6. Request rescoring: `scraper_reassess(repo="name", platform="toolbench")`
"""


@mcp.prompt()
def toolbench_rescore() -> str:
    """Steps to request a ToolBench rescore after making improvements."""
    return """## ToolBench Rescoring Steps

1. Make improvements based on ToolBench findings
2. Push changes to GitHub
3. Run `scraper_refresh(repo="your-repo-name")` to verify updated grades
4. Visit https://toolbench.arcade.dev/submit to request official rescore
5. Grades typically update within 24-48 hours
"""


GRADE_HELP_MD = """# scraper-mcp Grade Help

## ToolBench (arcade.dev)
- **A+** (90-100): Excellent - all criteria met
- **A** (80-89): Strong - minor gaps
- **B** (70-79): Good - meets most criteria
- **C** (60-69): Fair - needs work
- **D-F** (<60): Poor - significant gaps

## Glama.ai
- **A** (>=3.5): Excellent docstrings
- **B** (>=3.0): Good
- **C** (>=2.0): Fair
- **D-F** (<2.0): Needs significant docstring improvement

## LobeHub
- Presence only - no letter grades
"""


@mcp.resource("scraper://help/grades")
def grade_help_resource() -> str:
    """Grade meaning across platforms (ToolBench, Glama, LobeHub)."""
    return GRADE_HELP_MD
