"""Quick test with timeout."""
import asyncio
from scraper_mcp.scrapers.engine import GlamaScraper

scraper = GlamaScraper()
scraper.timeout = 10.0
try:
    row = asyncio.wait_for(scraper.fetch_grade("sandraschi", "virtualization-mcp"), timeout=15)
    if row:
        print(f"Grade: {row.get('grade')} Score: {row.get('score')}")
        print(f"Tools: {row.get('tools')}")
        print(f"TDQS: mean={row.get('tdqs_mean')} min={row.get('tdqs_min')}")
        details = row.get("tool_details", [])
        print(f"Tool details: {len(details)} tools")
    else:
        print("No result")
except asyncio.TimeoutError:
    print("TIMEOUT")
except Exception as e:
    print(f"ERROR: {e}")
