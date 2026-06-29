"""Find trust score HTML pattern."""
import httpx, re
resp = httpx.get(
    "https://toolbench.arcade.dev/api/servers?q=tailscale-mcp",
    headers={"Accept": "application/json"},
)
data = resp.json()
for s in data["servers"]:
    name = s.get("name", "")
    grade = s.get("grade", "?")
    score = s.get("overallScore", 0)
    print(f"{name}: grade={grade} score={score} id={s['id']}")
