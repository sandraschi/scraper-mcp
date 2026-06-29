"""Debug Glama scraper."""
import asyncio, httpx

async def main():
    url = "https://glama.ai/mcp/servers/sandraschi/virtualization-mcp/score"
    headers = {"User-Agent": "test/1.0", "Accept": "text/html"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            r = await client.get(url, headers=headers)
            print(f"Status: {r.status_code}")
            print(f"Content length: {len(r.text)}")
            if "Tool Scores" in r.text:
                print("Found 'Tool Scores' in response")
            else:
                print("'Tool Scores' NOT found")
                print(r.text[:500])
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(main())
