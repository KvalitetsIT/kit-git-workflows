"""
Responsibility: prepare all PR metadata and lifecycle decisions for one component update.

This script centralizes:
- deterministic branch/title naming
- deduplication and superseding behavior (close older component PRs)
- label output assembly
- PR body composition (diffs + organization search link)

Reusable parameters (all optional, with safe defaults):
- PR_BRANCH_PREFIX
- PR_TITLE_TEMPLATE
- SUPERSEDED_PR_COMMENT
- ORG_SEARCH_LINK_TEXT
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import uuid
from typing import Any


def gh_api(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    """Call GitHub API with gh CLI and return parsed JSON when possible."""
    cmd = ["gh", "api", path]
    if method != "GET":
        cmd.extend(["--method", method])
    if payload:
        for key, value in payload.items():
            cmd.extend(["-f", f"{key}={value}"])

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed for {path}: {result.stdout}{result.stderr}")

    text = (result.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def write_output(name: str, value: str) -> None:
    """Write a workflow output with multiline-safe formatting."""
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


def sanitize(value: str) -> str:
    """Build safe branch-suffix fragments from free-form text."""
    text = (value or "")
    text = re.sub(r"[/:@ ]", "-", text)
    text = re.sub(r"[^a-zA-Z0-9._-]", "", text)
    return text


def render_template(template: str, component_name: str, old_tag: str, new_tag: str) -> str:
    """Render supported placeholders for branch/title/comment templates."""
    return (
        template.replace("{component}", component_name)
        .replace("{old_tag}", old_tag)
        .replace("{new_tag}", new_tag)
    )


def list_open_pull_requests(owner: str, repo: str) -> list[dict[str, Any]]:
    """Read all open PRs via explicit pagination."""
    page = 1
    pulls: list[dict[str, Any]] = []
    while True:
        path = f"repos/{owner}/{repo}/pulls?state=open&per_page=100&page={page}"
        chunk = gh_api(path)
        if not isinstance(chunk, list):
            break
        pulls.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return pulls


def has_component_label(pr: dict[str, Any], component_name: str) -> bool:
    """Return true when PR labels include the component label exactly."""
    labels = pr.get("labels") or []
    for label in labels:
        if str((label or {}).get("name") or "") == component_name:
            return True
    return False


def body_mentions_component(pr: dict[str, Any], component_name: str) -> bool:
    """Match workflow-generated PR bodies that include the component bullet line."""
    body = str(pr.get("body") or "")
    return f"- `{component_name}`" in body


def compose_pr_body(
    *,
    component_name: str,
    old_tag: str,
    new_tag: str,
    compare_url: str,
    target_repo_url: str,
    release_name: str,
    release_url: str,
    path_links: list[dict[str, str]],
    org: str,
    labels: list[str],
    org_search_link_text: str,
) -> str:
    """Build stable PR body markdown for this component update."""
    path_lines = [f"- [`{item['filename']}`]({item['compare_sha256_url']})" for item in path_links]

    sorted_labels = sorted(labels, key=lambda s: s.lower())
    label_terms = [f'label:"{label.replace("\"", "\\\"")}"' for label in sorted_labels]
    base_org_query = f"org:{org} is:pr {' '.join(label_terms)}".strip()
    completed_query = f"{base_org_query} is:merged sort:updated-desc"
    completed_search_url = (
        f"https://github.com/search?q={urllib.parse.quote(completed_query, safe='')}&type=issues"
    )

    release_line = (
        f"Release: [{release_name} ({new_tag})]({release_url})"
        if release_name
        else f"Release: [{new_tag}]({release_url})"
    )

    return "\n".join(
        [
            f"This PR updates one component from `{old_tag}` to `{new_tag}`.",
            "",
            "Component:",
            "",
            f"- `{component_name}`",
            "",
            "Version transition:",
            "",
            f"- `{old_tag}` => `{new_tag}`",
            "",
            "Matched source repository:",
            "",
            f"- `{target_repo_url}`",
            "",
            "Diff:",
            "",
            f"- [`{old_tag}...{new_tag}`]({compare_url})",
            "",
            "Per-file compare links (best effort):",
            "",
            *path_lines,
            "",
            release_line,
            "",
            "Organization search:",
            "",
            f"- [{org_search_link_text}](<{completed_search_url}>)",
        ]
    )


def main() -> int:
    repo_full_name = os.environ.get("GITHUB_REPOSITORY", "").strip()
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY_NAME", "").strip()
    if "/" in repo:
        repo = repo.split("/", 1)[1].strip()
    if repo_full_name and "/" in repo_full_name:
        parsed_owner, parsed_repo = repo_full_name.split("/", 1)
        if not owner:
            owner = parsed_owner.strip()
        if not repo:
            repo = parsed_repo.strip()
    if not owner or not repo:
        raise RuntimeError("Unable to resolve repository owner/name from workflow environment")

    component_name = os.environ.get("COMPONENT_NAME", "").strip()
    old_tag = os.environ.get("OLD_TAG", "").strip()
    new_tag = os.environ.get("NEW_TAG", "").strip()
    compare_url = os.environ.get("COMPARE_URL", "").strip()
    target_repo_url = os.environ.get("TARGET_REPO_URL", "").strip()
    release_name = os.environ.get("RELEASE_NAME", "").strip()
    release_url = os.environ.get("RELEASE_URL", "").strip()

    pr_branch_prefix = os.environ.get("PR_BRANCH_PREFIX", "chore/update-k8s-component-")
    pr_title_template = os.environ.get("PR_TITLE_TEMPLATE", "Update {component} ({old_tag} => {new_tag})")
    superseded_comment_template = os.environ.get(
        "SUPERSEDED_PR_COMMENT",
        "Superseded by a newer k8s-components update for this component.",
    )
    org_search_link_text = os.environ.get("ORG_SEARCH_LINK_TEXT", "Similar merged PRs (same labels)").strip()

    path_links = json.loads(os.environ.get("PATH_DIFF_LINKS_JSON", "[]"))

    component_suffix = sanitize(component_name)
    tag_suffix = sanitize(new_tag)
    suffix = f"{component_suffix}-{tag_suffix}" or "latest"
    branch_name = f"{pr_branch_prefix}{suffix}"
    expected_title = render_template(pr_title_template, component_name, old_tag, new_tag)
    branch_prefix = f"{pr_branch_prefix}{component_suffix}-"
    expected_head_repo = f"{owner}/{repo}"
    expected_base_branch = (os.environ.get("TARGET_BRANCH") or os.environ.get("GITHUB_REF_NAME") or "").strip()

    write_output("branch_name", branch_name)
    write_output("pr_title", expected_title)

    open_pulls = list_open_pull_requests(owner, repo)
    component_open_pulls = []
    for pr in open_pulls:
        head_ref = str(pr.get("head", {}).get("ref", ""))
        if not head_ref.startswith(branch_prefix):
            continue
        head_repo = str((((pr.get("head") or {}).get("repo") or {}).get("full_name")) or "")
        if head_repo != expected_head_repo:
            continue
        base_branch = str(((pr.get("base") or {}).get("ref")) or "")
        if expected_base_branch and base_branch != expected_base_branch:
            continue
        if not has_component_label(pr, component_name) and not body_mentions_component(pr, component_name):
            continue
        component_open_pulls.append(pr)

    existing_same_title_pr = next((pr for pr in component_open_pulls if pr.get("title") == expected_title), None)
    if existing_same_title_pr:
        write_output("skip_create", "true")
        write_output("existing_pr_number", str(existing_same_title_pr.get("number", "")))
        milestone = existing_same_title_pr.get("milestone") or {}
        write_output("milestone_title", str(milestone.get("title") or ""))
        print(
            f"Found existing open PR #{existing_same_title_pr.get('number')} with same title. "
            "Skipping close/reopen."
        )
        return 0

    previous_with_milestone = next((pr for pr in component_open_pulls if (pr.get("milestone") or {}).get("title")), None)
    milestone_title = ""
    if previous_with_milestone:
        milestone_title = str((previous_with_milestone.get("milestone") or {}).get("title") or "")
    write_output("milestone_title", milestone_title)

    superseded_comment = render_template(superseded_comment_template, component_name, old_tag, new_tag)
    for pr in component_open_pulls:
        number = pr.get("number")
        if not number:
            continue
        gh_api(
            f"repos/{owner}/{repo}/pulls/{number}",
            method="PATCH",
            payload={"state": "closed"},
        )
        gh_api(
            f"repos/{owner}/{repo}/issues/{number}/comments",
            method="POST",
            payload={"body": superseded_comment},
        )

    write_output("skip_create", "false")

    base_labels = [x.strip() for x in os.environ.get("BASE_LABELS", "").split(",") if x.strip()]
    auto_label = os.environ.get("AUTOUPDATE_LABEL", "").strip()
    version_label = new_tag

    final_labels: list[str] = []
    if auto_label:
        final_labels.append(auto_label)
    final_labels.extend(base_labels)
    if version_label:
        final_labels.append(version_label)
    if component_name:
        final_labels.append(component_name)

    deduped_labels: list[str] = []
    for label in final_labels:
        if label and label not in deduped_labels:
            deduped_labels.append(label)

    write_output("labels", ",".join(deduped_labels))

    body = compose_pr_body(
        component_name=component_name,
        old_tag=old_tag,
        new_tag=new_tag,
        compare_url=compare_url,
        target_repo_url=target_repo_url,
        release_name=release_name,
        release_url=release_url,
        path_links=path_links,
        org=owner,
        labels=deduped_labels,
        org_search_link_text=org_search_link_text,
    )
    write_output("body", body)
    write_output("template_path", "pr-template.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
