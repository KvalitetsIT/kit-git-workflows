"""
Responsibility: find one open PR by exact title and expose lookup outputs.

Outputs written to GITHUB_OUTPUT:
- found=true|false
- number=<pr_number> (when found)
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from typing import Any


def gh_api(path: str) -> Any:
    """Call GitHub API via gh CLI and parse JSON payload."""
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed for {path}: {result.stdout}{result.stderr}")
    return json.loads(result.stdout)


def write_output(name: str, value: str) -> None:
    """Write one step output value in multiline-safe format."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        raise RuntimeError("GITHUB_OUTPUT is not set")

    text = value or ""
    if "\n" not in text:
        with open(output_file, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={text}\n")
        return

    marker = f"EOF_{uuid.uuid4().hex}"
    with open(output_file, "a", encoding="utf-8") as fh:
        fh.write(f"{name}<<{marker}\n")
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")
        fh.write(f"{marker}\n")


def main() -> int:
    owner = os.environ["TARGET_OWNER"]
    repo = os.environ["TARGET_REPO"]
    expected_title = os.environ["EXPECTED_TITLE"]

    page = 1
    pr = None
    while True:
        pulls = gh_api(f"repos/{owner}/{repo}/pulls?state=open&per_page=100&page={page}")
        if not isinstance(pulls, list):
            break
        pr = next((item for item in pulls if item.get("title") == expected_title), None)
        if pr is not None or len(pulls) < 100:
            break
        page += 1

    if not pr:
        write_output("found", "false")
        print(f"No open PR found for title: {expected_title}")
        return 0

    write_output("found", "true")
    write_output("number", str(pr["number"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
