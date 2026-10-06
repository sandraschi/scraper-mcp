"""Glama email tools - portmanteau for the email -> advice -> digest workflow (Phase 1: ingest)."""

from typing import Annotated

from pydantic import Field

from ... import email_ingest
from ..registry import mcp

FLEET_OWNER = "sandraschi"


@mcp.tool(annotations={"readOnly": False, "destructive": False})
async def scraper_email(
    operation: Annotated[
        str,
        Field(
            description="ingest: fetch Glama mails + persist events. events: read back stored events. pending_releases: B without follow-up R."
        ),
    ] = "ingest",
    service: Annotated[str, Field(description="email-mcp service. Default: graph.")] = "graph",
    folder: Annotated[str, Field(description="Mailbox folder. Default: Glama.")] = "Glama",
    limit: Annotated[int, Field(description="Max mails per ingest run.")] = 50,
    query: Annotated[
        str | None, Field(description="Optional $search query (uses folder-scoped search instead of folder listing).")
    ] = None,
    mark_read: Annotated[bool, Field(description="Mark consumed mails read. Default: off.")] = False,
    repo: Annotated[str | None, Field(description="Filter events by repo slug (events op).")] = None,
    type: Annotated[str | None, Field(description="Filter events by type R/B/F/O/unknown (events op).")] = None,
    days: Annotated[int, Field(description="Pending window in days (pending_releases op).")] = 7,
) -> dict:
    """Ingest Glama notification mails and track build -> release lifecycle.

    Phase 1 reads the Hotmail Glama folder via email-mcp, classifies mails
    (R release / B build ok / F build failed / O OTP / unknown), extracts
    repo + version + links, and persists idempotent events. Later phases
    build advice, competitor diffs, and the daily digest on top.

    ## Return Format
    ingest: {"success", "message", "data": {"ingested": int, "by_type": {...}, "pending_releases": [...]}}
    events: {"success", "message", "data": {"events": [...]}}
    pending_releases: {"success", "message", "data": {"pending": [...]}}

    ## Examples
    await scraper_email(operation="ingest")
    await scraper_email(operation="events", repo="onenote-mcp")
    await scraper_email(operation="pending_releases")
    """
    op = (operation or "ingest").strip().lower()
    if op == "ingest":
        return await email_ingest.ingest(service=service, folder=folder, limit=limit, query=query, mark_read=mark_read)
    if op == "events":
        events = email_ingest.list_events(repo=repo, type=type)
        return {
            "success": True,
            "message": f"{len(events)} stored Glama mail events.",
            "data": {"events": events},
        }
    if op == "pending_releases":
        pending = email_ingest.pending_releases(days=days)
        return {
            "success": True,
            "message": f"{len(pending)} repos built but unreleased in the last window.",
            "data": {"pending": pending},
        }
    return {
        "success": False,
        "message": f"Unknown operation '{operation}'. Use ingest, events, or pending_releases.",
        "data": {"operation": operation},
    }
