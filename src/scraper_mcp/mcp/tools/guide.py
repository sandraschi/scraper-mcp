"""toolbench_guide - ported from deprecated toolbench-mcp."""

from __future__ import annotations

from typing import Annotated, Any, Literal, assert_never

from pydantic import Field

from scraper_mcp import content

from ..registry import mcp

GuideOperation = Literal[
    "get_help",
    "list_official_links",
    "rescoring_after_improvements",
    "glama_vs_toolbench",
    "arcade_mcp_product",
]


@mcp.tool()
async def toolbench_guide(
    operation: Annotated[
        GuideOperation,
        Field(
            description=(
                "get_help | list_official_links | rescoring_after_improvements | "
                "glama_vs_toolbench | arcade_mcp_product"
            )
        ),
    ],
) -> dict[str, Any]:
    """Curated ToolBench context for agents (links, rescoring, Glama contrast, Arcade product)."""
    rec: list[str] = [
        "Open methodology before large refactors: https://toolbench.arcade.dev/methodology",
        "Grade matrix + archiver: https://github.com/sandraschi/scraper-mcp",
    ]
    if operation == "get_help":
        return {"success": True, "result": content.help_text(), "recommendations": rec}
    if operation == "list_official_links":
        return {"success": True, "result": dict(content.LINKS), "recommendations": rec}
    if operation == "rescoring_after_improvements":
        return {
            "success": True,
            "result": content.RESCORING_STEPS.strip(),
            "recommendations": rec + ["Submit: https://toolbench.arcade.dev/submit"],
        }
    if operation == "glama_vs_toolbench":
        return {
            "success": True,
            "result": content.GLAMA_VS_TOOLBENCH.strip(),
            "recommendations": rec,
        }
    if operation == "arcade_mcp_product":
        return {
            "success": True,
            "result": (
                "Arcade.dev ships an MCP runtime / integrations platform (Gmail, Slack, GitHub, …). "
                "Optional when you need hosted tools with Arcade auth - separate from ToolBench grading."
            ),
            "recommendations": [
                "https://docs.arcade.dev/en/get-started/mcp-clients",
                "https://docs.arcade.dev/en/get-started/quickstarts/call-tool-client",
            ],
        }
    assert_never(operation)
