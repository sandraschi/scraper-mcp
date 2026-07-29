"""Capture live ToolBench API responses as test fixtures.

One-shot: fetches /api/servers?q=scraper-mcp and the corresponding
assessment page HTML, saving both under tests/fixtures/toolbench/.
"""
import asyncio
import json
import pathlib

import httpx

OUT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "toolbench"
UA = "scraper-mcp/0.1 (fixture capture; one-shot)"


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=15, http2=False) as client:
        r = await client.get(
            "https://toolbench.arcade.dev/api/servers",
            params={"q": "scraper-mcp"},
            headers={"Accept": "application/json", "User-Agent": UA},
        )
        print(f"API  status: {r.status_code}")
        api_data = r.json()
        api_path = OUT / "api_servers_scraper-mcp.json"
        api_path.write_text(json.dumps(api_data, indent=2), encoding="utf-8")
        print(f"API  saved:  {api_path} ({len(json.dumps(api_data))} bytes)")

        servers: list[dict] = api_data.get("servers", api_data.get("data", []))
        if not servers:
            print("WARNING: no servers in API response — fixture is empty list")
            return

        s = servers[0]
        sid = s.get("id", "")
        print(f"ID:   {sid}  name={s.get('name', '?')}")

        r2 = await client.get(
            f"https://toolbench.arcade.dev/tools/{sid}",
            headers={"Accept": "text/html", "User-Agent": UA},
            follow_redirects=True,
        )
        print(f"HTML status: {r2.status_code} ({len(r2.text)} bytes)")
        html_path = OUT / f"tools_{sid}.html"
        html_path.write_text(r2.text, encoding="utf-8")
        print(f"HTML saved:  {html_path}")


if __name__ == "__main__":
    asyncio.run(main())
