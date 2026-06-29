"""Test ToolBench scraper."""
import asyncio
from scraper_mcp.scrapers.toolbench_score import fetch_grade_with_details

r = asyncio.run(fetch_grade_with_details("sandraschi", "tailscale-mcp"))
if r:
    print(f"Grade: {r.get('grade')} Score: {r.get('score')}")
    print(f"Trust: {r.get('trust_score')}")
    print(f"Def: {r.get('definition_score')} Proto: {r.get('protocol_score')} Supp: {r.get('supportability_score')}")
    print(f"Tools: {r.get('tools')} Status: {r.get('status')}")
    issues = r.get("top_issues", [])
    print(f"Top issues: {len(issues)}")
    for t in issues[:3]:
        print(f"  - {t[:100]}")
    details = r.get("tool_details", [])
    print(f"Tool details: {len(details)}")
    for t in details[:3]:
        print(f"  {t.get('name')}: risk={t.get('risk_score')}")
else:
    print("No result")
