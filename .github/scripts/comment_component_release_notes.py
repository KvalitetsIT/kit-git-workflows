from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


def gh_api(token: str, path: str, method: str = "GET", payload: dict[str, str] | None = None) -> Any:
    """Call GitHub API via gh CLI with a specific token and return parsed JSON."""
    # Use a per-call token so we can read from source repo and write to target repo independently.
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    # Build gh command dynamically from method/payload.
    cmd = ["gh", "api", path]
    if method != "GET":
        cmd.extend(["--method", method])
    if payload:
        for key, value in payload.items():
            cmd.extend(["-f", f"{key}={value}"])
    # Capture output to provide actionable failure diagnostics.
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed for {path}: {result.stdout}{result.stderr}")
    return json.loads(result.stdout)


def clean_text_for_preview(value: str, max_len: int = 600) -> str:
    """Compress whitespace and trim preview length for markdown readability."""
    # Flatten multi-line markdown so preview lines remain compact in PR comments.
    single_line = re.sub(r"\s+", " ", value or "").strip()
    if len(single_line) <= max_len:
        return single_line
    return f"{single_line[: max_len - 1]}…"


def select_release_window(releases: list[dict[str, Any]], old_tag: str, new_tag: str) -> list[dict[str, Any]]:
    """
    Pick releases between old and new tag.

    Releases are expected in newest-first order.
    """
    if not releases:
        return []

    by_tag = {str(item.get("tag_name") or ""): idx for idx, item in enumerate(releases)}
    old_idx = by_tag.get(old_tag)
    new_idx = by_tag.get(new_tag)

    if new_idx is not None and old_idx is not None:
        # Normal case: both versions exist as releases.
        start, end = sorted((new_idx, old_idx))
        if start == end:
            window = [releases[start]]
        else:
            # Include new tag release; exclude old tag release.
            window = releases[start:end]
    elif new_idx is not None:
        # Old tag might be missing as a release; include newer releases from new tag onward.
        window = releases[new_idx:]
    elif old_idx is not None:
        # If new tag has no release entry yet, use newer releases above old tag.
        window = releases[:old_idx]
    else:
        # Fallback: if neither tag exists as release names, inspect all fetched releases.
        window = releases

    return window


def find_component_matches(releases: list[dict[str, Any]], component_name: str) -> list[dict[str, str]]:
    """Return releases where component name appears in release title/body."""
    # Case-insensitive substring search against release title and body text.
    needle = component_name.casefold()
    matches: list[dict[str, str]] = []
    for release in releases:
        tag = str(release.get("tag_name") or "")
        title = str(release.get("name") or "")
        body = str(release.get("body") or "")
        url = str(release.get("html_url") or "")
        haystack = f"{title}\n{body}".casefold()
        if needle not in haystack:
            continue
        matches.append(
            {
                "tag": tag,
                "title": title,
                "url": url,
                "preview": clean_text_for_preview(body),
            }
        )
    return matches


def main() -> int:
    # Read all runtime inputs from environment for predictable workflow wiring.
    source_owner = os.environ["SOURCE_OWNER"]
    source_repo = os.environ["SOURCE_REPO"]
    component_name = os.environ["COMPONENT_NAME"]
    old_tag = os.environ["OLD_TAG"]
    new_tag = os.environ["NEW_TAG"]
    target_owner = os.environ["TARGET_OWNER"]
    target_repo = os.environ["TARGET_REPO"]
    target_pr_number = os.environ["TARGET_PR_NUMBER"]
    source_token = os.environ["SOURCE_GH_TOKEN"]
    target_token = os.environ["TARGET_GH_TOKEN"]
    # Limit how many matched entries are shown in the final PR comment.
    max_release_notes = int(os.environ.get("MAX_RELEASE_NOTES", "5"))
    if max_release_notes < 1:
        max_release_notes = 1

    # Fetch up to 100 recent releases from source repo for matching.
    releases = gh_api(
        source_token,
        f"repos/{source_owner}/{source_repo}/releases?per_page=100",
    )
    # Focus search to releases in the version transition window.
    window = select_release_window(releases, old_tag=old_tag, new_tag=new_tag)
    # Find all component-related release-note matches in the selected window.
    matches = find_component_matches(window, component_name=component_name)
    displayed_matches = matches[:max_release_notes]

    # Marker prevents duplicate comments for same component/version transition.
    marker = f"<!-- k8s-components-release-notes:{component_name}:{old_tag}:{new_tag} -->"
    comments = gh_api(
        target_token,
        f"repos/{target_owner}/{target_repo}/issues/{target_pr_number}/comments?per_page=100",
    )
    if any(marker in str(comment.get("body") or "") for comment in comments):
        print("Release-note comment already exists for this component/version transition.")
        return 0

    # Start composing a human-readable PR comment.
    lines = [
        marker,
        f"### Component release-note matches: `{component_name}`",
        "",
        f"Searched **{len(window)}** releases between `{old_tag}` and `{new_tag}` in `{source_owner}/{source_repo}`.",
        "",
    ]
    if matches:
        # Add explicit warning when there are more matches than the configured display limit.
        if len(matches) > max_release_notes:
            lines.append(
                f"⚠️ **Found {len(matches)} matching release notes, but only showing the first {max_release_notes}.**"
            )
            lines.append("")
        lines.append("Found matches:")
        lines.append("")
        for item in displayed_matches:
            title = item["title"] or item["tag"]
            lines.append(f"- [{title}]({item['url']}) (`{item['tag']}`)")
            if item["preview"]:
                lines.append(f"  - {item['preview']}")
    else:
        lines.append("No release notes in the checked release window contained the component name.")

    # Post the assembled markdown comment to the target PR.
    gh_api(
        target_token,
        f"repos/{target_owner}/{target_repo}/issues/{target_pr_number}/comments",
        method="POST",
        payload={"body": "\n".join(lines)},
    )
    print("Posted component release-note comment on PR.")
    return 0


if __name__ == "__main__":
    # Exit code is surfaced directly in workflow logs.
    raise SystemExit(main())
