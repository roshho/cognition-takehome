#!/usr/bin/env python3
"""Generate a new internal app from templates/internal-app.

Usage: npm run new-app -- <app-name>   (lowercase letters, digits, hyphens)

Creates apps/<name>/{backend/router.py, backend/test_<name>.py,
frontend/Page.tsx}, mounted automatically on the next api/web restart —
no wiring edits needed.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "internal-app"


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z][a-z0-9-]*", sys.argv[1]):
        print("usage: npm run new-app -- <app-name>")
        print("       <app-name>: lowercase letters, digits, hyphens (e.g. it-assets)")
        return 2

    name = sys.argv[1]
    dest = ROOT / "apps" / name
    if dest.exists():
        print(f"error: apps/{name} already exists")
        return 1

    replacements = {
        "__APP__": name,
        "__APP_TITLE__": name.replace("-", " ").title(),
        "__APP_TABLE__": name.replace("-", "_") + "_items",
        "__APP_TEST__": "test_" + name.replace("-", "_"),
        "__APP_CLASS__": "".join(p.title() for p in re.split(r"[-_]", name)),
    }

    shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns("README.md"))
    for path in sorted(dest.rglob("*")):
        if path.is_file():
            text = path.read_text()
            for k, v in replacements.items():
                text = text.replace(k, v)
            path.write_text(text)
        # rename test file containing placeholder
        if "__APP_TEST__" in path.name:
            path.rename(path.with_name(path.name.replace("__APP_TEST__", replacements["__APP_TEST__"])))

    print(f"Created apps/{name}:")
    for path in sorted(dest.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(ROOT)}")
    print()
    print("Next: restart `npm start` (or just the api) — the app is mounted at")
    print(f"  API:   /api/{name}/items")
    print(f"  Page:  /apps/{name}  (also on the home dashboard)")
    print(f"Run its tests: cd backend && .venv/bin/python -m pytest ../apps/{name} -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
