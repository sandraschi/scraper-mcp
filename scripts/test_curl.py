"""Test with urllib since httpx has issues."""
import urllib.request, urllib.error

url = "https://glama.ai/mcp/servers/sandraschi/virtualization-mcp/score"
req = urllib.request.Request(url, headers={"User-Agent": "test/1.0"})
try:
    resp = urllib.request.urlopen(req, timeout=15)
    data = resp.read().decode()
    print(f"Status: {resp.status}, Len: {len(data)}")
    print(f"Has 'Tool Scores': {'Tool Scores' in data}")
except Exception as e:
    print(f"Error: {e}")
