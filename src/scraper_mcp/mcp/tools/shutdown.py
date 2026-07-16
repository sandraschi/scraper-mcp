"""Self-termination tool — allows agents to shut down the server gracefully."""

import os
import signal

from ..registry import mcp


@mcp.tool(annotations={"destructive": True, "readOnly": False})
async def scraper_shutdown() -> dict:
    """Gracefully shut down the scraper-mcp server.

    Triggers SIGTERM on the current process, allowing uvicorn/FastMCP
    to clean up connections and close the SQLite database.

    ## Return Format
    {"success": bool, "message": str}

    ## Examples
    await scraper_shutdown()
    """
    os.kill(os.getpid(), signal.SIGTERM)
    return {"success": True, "message": "SIGTERM sent — server shutting down."}
