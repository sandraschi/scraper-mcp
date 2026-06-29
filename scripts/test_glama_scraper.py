"""Test the upgraded Glama scraper."""
import asyncio
from scraper_mcp.scrapers.engine import GlamaScraper, _normalize_row

scraper = GlamaScraper()
row = asyncio.run(scraper.fetch_grade("sandraschi", "virtualization-mcp"))
if row:
    print(f"Grade: {row.get('grade')} Score: {row.get('score')}")
    print(f"Tools: {row.get('tools')} Status: {row.get('status')}")
    print(f"TDQS: mean={row.get('tdqs_mean')} min={row.get('tdqs_min')} grade={row.get('tdqs_grade')}")
    print(f"Coherence: {row.get('coherence_grade')} Maint: {row.get('maintenance_grade')}")
    print(f"Release: {row.get('latest_release')}")
    details = row.get("tool_details", [])
    print(f"Tool details: {len(details)} tools")
    for t in sorted(details, key=lambda x: x.get("score", 5))[:3]:
        print(f"  {t['name']}: {t.get('grade','?')} {t.get('score',0)}")
else:
    print("No result")
