#!/usr/bin/env python3
"""Check the static site for broken internal links and missing assets.

Scans every .html file in the repository (excluding .git and build output),
resolves relative href/src references against the file that contains them,
and reports any target that does not exist on disk. External URLs (http,
https, mailto, #fragments, data:) are skipped.

Usage:
    python3 tools/check_site_links.py

Exit codes:
    0 - no broken internal references
    1 - at least one broken reference found
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_ROOT = os.path.join(REPO_ROOT, "site")

SKIP_DIRS = {".git", "node_modules", "build", "dist", "__pycache__",
             "web-ui-design(skill)"}
# href/src attributes; also data-download-url which drives the T&C modal.
ATTR_RE = re.compile(
    r"""(?:href|src|data-download-url)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
EXTERNAL_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|#)", re.IGNORECASE)


def html_files():
    for dirpath, dirnames, filenames in os.walk(SITE_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".html"):
                yield os.path.join(dirpath, name)


def check():
    broken = []
    checked = 0
    for page in html_files():
        with open(page, encoding="utf-8") as fh:
            content = fh.read()
        for match in ATTR_RE.finditer(content):
            ref = match.group(1).strip()
            if not ref or EXTERNAL_RE.match(ref):
                continue
            checked += 1
            target = ref.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue  # pure fragment like "#main"
            resolved = os.path.normpath(os.path.join(os.path.dirname(page), target))
            if not os.path.exists(resolved):
                rel = os.path.relpath(page, REPO_ROOT)
                broken.append(f"{rel}: {ref}")
    return checked, broken


def main():
    checked, broken = check()
    print(f"Checked {checked} internal references across the static site.")
    if broken:
        print(f"\nBROKEN ({len(broken)}):")
        for item in broken:
            print(f"  {item}")
        return 1
    print("All internal links and assets resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
