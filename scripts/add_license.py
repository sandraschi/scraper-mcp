"""Add MIT LICENSE to a fleet repo.

Usage: uv run python scripts/add_license.py repo1 repo2 ... (max 5)

Restored 2026-07-29 after Opus review noted the original was deleted.
"""
import os
import subprocess
import textwrap

REPOS_ROOT = r"D:\Dev\repos"

LICENSE_TEXT = textwrap.dedent("""\
    MIT License

    Copyright (c) 2026 Sandra Schipal

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
""")


def add_license(repo: str) -> bool:
    repo_path = os.path.join(REPOS_ROOT, repo)
    license_path = os.path.join(repo_path, "LICENSE")
    if not os.path.isdir(repo_path):
        print(f"  SKIP {repo}: directory not found")
        return False
    if os.path.exists(license_path):
        print(f"  SKIP {repo}: LICENSE already exists")
        return False

    with open(license_path, "w", encoding="utf-8") as f:
        f.write(LICENSE_TEXT)

    os.chdir(repo_path)
    try:
        subprocess.run(["git", "add", "LICENSE"], check=True, capture_output=True, timeout=30)
        subprocess.run(
            ["git", "-c", "user.name=Sandra Schipal", "-c", "user.email=sandra@example.com",
             "commit", "-m", "Add MIT LICENSE"],
            check=True, capture_output=True, timeout=30,
        )
        result = subprocess.run(["git", "push"], capture_output=True, timeout=60)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            if "no upstream" in stderr.lower():
                branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=10,
                ).stdout.strip()
                subprocess.run(
                    ["git", "push", "--set-upstream", "origin", branch],
                    check=True, capture_output=True, timeout=60,
                )
                print(f"  OK  {repo}: LICENSE added (pushed with --set-upstream)")
                return True
            else:
                safe = stderr.encode("ascii", errors="replace").decode("ascii")
                print(f"  ERR {repo}: push failed: {safe[:200]}")
                return False
        print(f"  OK  {repo}: LICENSE added, committed, pushed")
        return True
    except subprocess.CalledProcessError as e:
        msg = (e.stderr.decode("utf-8", errors="replace")[:300] if e.stderr else str(e))
        safe = msg.encode("ascii", errors="replace").decode("ascii")
        print(f"  ERR {repo}: {safe}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  ERR {repo}: git timed out")
        return False


def main():
    repos = os.sys.argv[1:]
    if not repos:
        print("Usage: python add_license.py repo1 repo2 ... (max 5)")
        os.sys.exit(1)
    if len(repos) > 5:
        print(f"Batch limit is 5 repos, got {len(repos)}")
        os.sys.exit(1)
    for repo in repos:
        add_license(repo)


if __name__ == "__main__":
    main()
