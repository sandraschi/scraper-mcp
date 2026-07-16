\"\"\"PyInstaller entry point - dual transport (stdio/HTTP).\"\"\"
import os, sys
sys.path.insert(0, "src")

from scraper_mcp.server import app
import uvicorn

port = int(os.getenv("MCP_PORT") or os.getenv("PORT") or "10998")
host = os.getenv("MCP_HOST", "127.0.0.1")
uvicorn.run(app, host=host, port=port, log_level="info")
