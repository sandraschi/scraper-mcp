import asyncio, sys
sys.path.insert(0, "src")
from scraper_mcp.mcp.tools.autofix import scraper_fix_repo

r = asyncio.run(scraper_fix_repo(repo="database-operations-mcp"))
print(r["message"])
for k, v in r["fixes"].items():
    print(f"  [{k}] {len(v['details'])} items")
print("Issues:", len(r.get("issues_used", [])))
