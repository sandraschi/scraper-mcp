"""Debug httpx connection."""
import asyncio, httpx, sys, traceback

async def main():
    url = "https://glama.ai/mcp/servers/sandraschi/virtualization-mcp/score"
    headers = {"User-Agent": "test/1.0", "Accept": "text/html"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            r = await client.get(url, headers=headers)
            print(f"Status: {r.status_code}")
            print(f"Content: {len(r.text)} chars")
        except httpx.ConnectError as e:
            print(f"ConnectError: {e}")
            traceback.print_exc()
        except httpx.HTTPStatusError as e:
            print(f"HTTPStatusError: {e}")
        except Exception as e:
            print(f"{type(e).__name__}: {e!s}")
            traceback.print_exc()

asyncio.run(main())
