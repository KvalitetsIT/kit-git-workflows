"""
Responsibility: resolve the newest usable version identifier for the source repository.

This script reads SOURCE_OWNER/SOURCE_REPO and uses GitHub API calls via `gh` to:
1) Read latest release metadata.
2) Fail immediately if that API call fails.
3) Expose outputs for downstream workflow steps.

Outputs written to GITHUB_OUTPUT:
- tag
- name
- url
- notes
"""

from __future__ import annotations

import os
import subprocess
import uuid
from typing import Any


def gh_api(path: str) -> Any:
    """Call GitHub API via gh CLI and parse JSON response."""
    result = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed for {path}: {result.stdout}{result.stderr}")
    import json

    return json.loads(result.stdout)


def write_output(name: str, value: str) -> None:
    """Append one output value to GITHUB_OUTPUT with multiline safety."""
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


def resolve_latest_release(owner: str, repo: str) -> tuple[str, str, str, str]:
    """Resolve latest release metadata and return (tag, name, url, notes)."""
    release = gh_api(f"repos/{owner}/{repo}/releases/latest")
    tag = str(release.get("tag_name") or "")
    name = str(release.get("name") or "")
    url = str(release.get("html_url") or "")
    notes = str(release.get("body") or "")
    return tag, name, url, notes


def main() -> int:
    owner = os.environ["SOURCE_OWNER"]
    repo = os.environ["SOURCE_REPO"]

    tag, name, url, notes = resolve_latest_release(owner, repo)

    write_output("tag", tag)
    write_output("name", name)
    write_output("url", url)
    write_output("notes", notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
