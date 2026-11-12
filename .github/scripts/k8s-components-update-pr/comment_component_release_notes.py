"""
Responsibility: post one deduplicated component release-note comment on the target PR.

This script:
- fetches releases from the source repository
- narrows the search to the version transition window
- finds release-note entries that mention the component
- posts a concise markdown comment with mention-neutralized text

Important behavior:
- mention safety: every ASCII '@' is replaced with fullwidth '＠'
- duplicate protection: a hidden marker prevents duplicate comments for same component transition
- summary fallback: each listed match always gets a non-empty text summary

Reusable parameters (optional):
- COMMENT_MARKER_PREFIX (default: k8s-components-release-notes)
- COMMENT_HEADER_TEMPLATE (default: Component release-note matches: `{component}`)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


def gh_api(token: str, path: str, method: str = "GET", payload: dict[str, str] | None = None) -> Any:
    """Call GitHub API via gh CLI with an explicit token context."""
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    cmd = ["gh", "api", path]
    if method != "GET":
        cmd.extend(["--method", method])
    if payload:
        for key, value in payload.items():
            cmd.extend(["-f", f"{key}={value}"])
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed for {path}: {result.stdout}{result.stderr}")
    return json.loads(result.stdout)


def neutralize_mentions(value: str) -> str:
    """Hard-disable mentions by replacing ASCII @ with fullwidth ＠."""
    return (value or "").replace("@", "＠")


def compact_release_text(value: str, max_len: int = 180) -> str:
    """Build a short single-line markdown-safe snippet from arbitrary text."""
    text = value or ""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*`]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = neutralize_mentions(text)
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}…"


def release_text_snippet(body: str, component_name: str, title: str) -> str:
    """Extract a component-relevant summary line with safe fallback behavior."""
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    component_key = component_name.casefold()
    prioritized = [line for line in lines if component_key in line.casefold()]
    candidate = prioritized[0] if prioritized else (lines[0] if lines else "")

    snippet = compact_release_text(candidate)
    if snippet:
        return snippet

    title_fallback = compact_release_text(title)
    if title_fallback:
        return title_fallback

    return "No short summary available in release text."


def select_release_window(releases: list[dict[str, Any]], old_tag: str, new_tag: str) -> list[dict[str, Any]]:
    """Pick releases between old and new tag in newest-first release lists."""
    if not releases:
        return []

    by_tag = {str(item.get("tag_name") or ""): idx for idx, item in enumerate(releases)}
    old_idx = by_tag.get(old_tag)
    new_idx = by_tag.get(new_tag)

    if new_idx is not None and old_idx is not None:
        start, end = sorted((new_idx, old_idx))
        if start == end:
            return [releases[start]]
        return releases[start:end]
    if new_idx is not None:
        return releases[new_idx:]
    if old_idx is not None:
        return releases[:old_idx]
    return releases


def find_component_matches(releases: list[dict[str, Any]], component_name: str) -> list[dict[str, str]]:
    """Return release entries where component name appears in title/body."""
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
                "title": neutralize_mentions(title),
                "url": url,
                "summary": release_text_snippet(body, component_name, title),
            }
        )
    return matches


def render_template(template: str, component: str) -> str:
    """Render supported placeholders in comment templates."""
    return template.replace("{component}", component)


def main() -> int:
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

    marker_prefix = os.environ.get("COMMENT_MARKER_PREFIX", "k8s-components-release-notes")
    header_template = os.environ.get(
        "COMMENT_HEADER_TEMPLATE",
        "Component release-note matches: `{component}`",
    )

    max_release_notes = int(os.environ.get("MAX_RELEASE_NOTES", "5"))
    if max_release_notes < 1:
        max_release_notes = 1

    releases = gh_api(source_token, f"repos/{source_owner}/{source_repo}/releases?per_page=100")
    window = select_release_window(releases, old_tag=old_tag, new_tag=new_tag)
    matches = find_component_matches(window, component_name=component_name)
    displayed_matches = matches[:max_release_notes]

    marker = f"<!-- {marker_prefix}:{component_name}:{old_tag}:{new_tag} -->"
    comments = gh_api(
        target_token,
        f"repos/{target_owner}/{target_repo}/issues/{target_pr_number}/comments?per_page=100",
    )
    if any(marker in str(comment.get("body") or "") for comment in comments):
        print("Release-note comment already exists for this component/version transition.")
        return 0

    lines = [
        marker,
        f"### {render_template(header_template, component_name)}",
        "",
        f"Searched **{len(window)}** releases between `{old_tag}` and `{new_tag}` in `{source_owner}/{source_repo}`.",
        "",
    ]

    if matches:
        if len(matches) > max_release_notes:
            lines.append(
                f"⚠️ **Found {len(matches)} matching release notes, but only showing the first {max_release_notes}.**"
            )
            lines.append("")

        lines.append("Found matches:")
        lines.append("")
        for item in displayed_matches:
            title = item["title"] or item["tag"]
            summary = item.get("summary") or ""
            if summary:
                lines.append(f"- [{title}]({item['url']}) (`{item['tag']}`) — {summary}")
            else:
                lines.append(f"- [{title}]({item['url']}) (`{item['tag']}`)")
    else:
        lines.append("No release notes in the checked release window contained the component name.")

    gh_api(
        target_token,
        f"repos/{target_owner}/{target_repo}/issues/{target_pr_number}/comments",
        method="POST",
        payload={"body": "\n".join(lines)},
    )
    print("Posted component release-note comment on PR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
