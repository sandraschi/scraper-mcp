"""Find top issues HTML structure."""
import httpx, re
from bs4 import BeautifulSoup

client = httpx.Client(timeout=15, follow_redirects=True, http2=False)
resp = client.get(
    "https://toolbench.arcade.dev/tools/cmmiudisr04w1fqqwpdizyebc",
    headers={"User-Agent": "test/1.0"},
)
soup = BeautifulSoup(resp.text, "lxml")

# Find "Top Issues" header
hdr = soup.find(string=re.compile(r"Top Issues"))
if hdr:
    section = hdr.find_parent(["div", "section"])
    if section:
        for i, child in enumerate(section.children):
            if hasattr(child, 'name') and child.name:
                txt = child.get_text(strip=True)[:120]
                if txt and len(txt) > 10:
                    print(f"  <{child.name}> class={str(child.get('class',''))[:30]}")
                    print(f"    '{txt}'")
                    m = re.search(r'(critical|high|medium|low)\b', txt, re.I)
                    if m:
                        print(f"    SEVERITY: {m.group(1)}")
else:
    for sev in ("critical", "high", "medium", "low"):
        for el in soup.find_all(string=re.compile(rf"^{sev}\b", re.I)):
            p = el.parent
            if p:
                txt = p.get_text(strip=True)[:100]
                print(f"  severity '{sev}' in <{p.name}>: '{txt}'")
                grand = p.parent
                if grand:
                    print(f"    parent: <{grand.name}> class={grand.get('class','')}")
