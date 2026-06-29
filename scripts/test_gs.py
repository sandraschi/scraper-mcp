"""Test Glama scraper."""
import asyncio
from scraper_mcp.scrapers.glama_score import scrape_score_page

async def main():
    result = await scrape_score_page("sandraschi", "virtualization-mcp")
    if result:
        print(f"Grade: {result.get('grade')} Score: {result.get('score')}")
        print(f"Tools: {result.get('tools')}")
        print(f"TDQS: mean={result.get('tdqs_mean')} min={result.get('tdqs_min')}")
        details = result.get("tool_details", [])
        print(f"Tool details: {len(details)} tools")
        for t in sorted(details, key=lambda x: x.get("score", 5))[:3]:
            print(f"  {t['name']}: {t.get('grade','?')} {t.get('score',0)}")
    else:
        print("No result")

asyncio.run(main())
