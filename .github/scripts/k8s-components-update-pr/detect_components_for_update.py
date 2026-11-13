#!/usr/bin/env python3
"""
Detect which components should get update PRs.

This script focuses only on "who should be updated".
It writes:
- changed component count
- changed component JSON payload
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
import hashlib
from pathlib import Path
from typing import Any

import yaml

# Why this exists:
# The workflow runs scripts with `python -I` (isolated mode). In isolated mode,
# Python does not include the script directory on `sys.path`.
# We add it explicitly so this script can import shared local helpers.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from component_update_shared import normalize_component_path, normalize_repo_ref


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


# Why this exists:
# GitHub compare API returns changed files. We only need file names here.
def get_compare_files(source_owner: str, source_repo: str, source_tag: str, current_tag: str) -> list[str]:
    compare = f"{current_tag}...{source_tag}"
    cmd = ["gh", "api", f"repos/{source_owner}/{source_repo}/compare/{compare}", "--jq", ".files[].filename"]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        fail(result.stderr.strip() or "Failed to fetch compare data from GitHub API.")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def write_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_file:
        fail("GITHUB_OUTPUT is not set")
    if "\n" not in value:
        with open(output_file, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")
        return
    marker = f"EOF_{uuid.uuid4().hex}"
    with open(output_file, "a", encoding="utf-8") as fh:
        fh.write(f"{name}<<{marker}\n{value}")
        if not value.endswith("\n"):
            fh.write("\n")
        fh.write(f"{marker}\n")


def render_title_template(template: str, component_name: str, old_tag: str, new_tag: str) -> str:
    return (
        template.replace("{component}", component_name)
        .replace("{old_tag}", old_tag)
        .replace("{new_tag}", new_tag)
    )


def resolve_target_repo_identity() -> tuple[str, str]:
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").strip()
    name = os.environ.get("GITHUB_REPOSITORY_NAME", "").strip()
    repo_full = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if (not owner or not name) and "/" in repo_full:
        full_owner, full_name = repo_full.split("/", 1)
        owner = owner or full_owner
        name = name or full_name
    return owner, name


def list_open_pr_titles(owner: str, repo: str) -> set[str]:
    if not owner or not repo:
        return set()
    titles: set[str] = set()
    page = 1
    while True:
        cmd = [
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls",
            "-f",
            "state=open",
            "-f",
            "per_page=100",
            "-f",
            f"page={page}",
        ]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            break
        try:
            pulls = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            break
        if not isinstance(pulls, list):
            break
        for pr in pulls:
            title = str((pr or {}).get("title") or "")
            if title:
                titles.add(title)
        if len(pulls) < 100:
            break
        page += 1
    return titles


# Why this exists:
# We walk the YAML tree and collect both:
# - source: {repoURL, targetRevision, path}
# - sources: [{repoURL, targetRevision, path}, ...]
def collect_source_entries(data: Any) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            source = node.get("source")
            if isinstance(source, dict):
                entry = build_entry(source)
                if entry:
                    entries.append(entry)

            sources = node.get("sources")
            if isinstance(sources, list):
                for item in sources:
                    if isinstance(item, dict):
                        entry = build_entry(item)
                        if entry:
                            entries.append(entry)

            for value in node.values():
                visit(value)
            return

        if isinstance(node, list):
            for item in node:
                visit(item)

    visit(data)
    return entries


def build_entry(source: dict[str, Any]) -> dict[str, str] | None:
    repo_url = str(source.get("repoURL", "")).strip()
    target_revision = str(source.get("targetRevision", "")).strip()
    path_value = normalize_component_path(str(source.get("path", "")))
    if not repo_url or not target_revision or not path_value:
        return None
    return {"repo_url": repo_url, "target_revision": target_revision, "path": path_value}


def main() -> None:
    source_owner = os.getenv("SOURCE_OWNER", "").strip()
    source_repo = os.getenv("SOURCE_REPO", "").strip()
    source_tag = os.getenv("NEW_TARGET_REVISION", "").strip()
    target_repo_url = os.getenv("TARGET_REPO_URL", "").strip()
    values_file_path = os.getenv("PROD_APP_OF_APPS_FILE_PATH", "").strip()
    max_prs_raw = os.getenv("MAX_PRS_PER_RUN", "0").strip()
    max_prs_per_run = int(max_prs_raw) if max_prs_raw.isdigit() else 0
    pr_title_template = os.getenv("PR_TITLE_TEMPLATE", "Update {component} ({old_tag} => {new_tag})")
    verbose = os.getenv("VERBOSE", "").lower() == "1"

    required_env = {
        "SOURCE_OWNER": source_owner,
        "SOURCE_REPO": source_repo,
        "NEW_TARGET_REVISION": source_tag,
        "TARGET_REPO_URL": target_repo_url,
        "PROD_APP_OF_APPS_FILE_PATH": values_file_path,
    }
    missing = [name for name, value in required_env.items() if not value]
    if missing:
        fail(f"Missing required environment variable(s): {', '.join(missing)}")

    values_path = Path(values_file_path)
    if not values_path.exists():
        fail(f"Values file not found: {values_file_path}")

    try:
        yaml_data = yaml.safe_load(values_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        fail(f"Could not parse YAML file '{values_file_path}': {exc}")

    source_entries = collect_source_entries(yaml_data)
    target_repo_ref = normalize_repo_ref(target_repo_url)
    target_owner, target_repo = resolve_target_repo_identity()
    open_pr_titles = list_open_pr_titles(target_owner, target_repo)

    changed_components: list[dict[str, str]] = []
    seen_components: set[str] = set()

    for entry in source_entries:
        repo_ref = normalize_repo_ref(entry["repo_url"])
        if repo_ref != target_repo_ref:
            continue
        old_tag = entry["target_revision"].strip()
        component = normalize_component_path(entry["path"])
        if not old_tag or not component or component in seen_components or old_tag == source_tag:
            continue

        compare_url = f"https://github.com/{source_owner}/{source_repo}/compare/{old_tag}...{source_tag}"
        compare_files = get_compare_files(source_owner, source_repo, source_tag, old_tag)
        if not any(f == component or f.startswith(component + "/") for f in compare_files):
            continue

        expected_title = render_title_template(pr_title_template, component, old_tag, source_tag)
        if expected_title in open_pr_titles:
            continue
        if max_prs_per_run > 0 and len(changed_components) >= max_prs_per_run:
            break

        path_diff_links = [
            {
                "filename": filename,
                "compare_sha256_url": f"{compare_url}#diff-{hashlib.sha256(filename.encode()).hexdigest()}",
            }
            for filename in compare_files
            if filename == component or filename.startswith(component + "/")
        ]
        changed_components.append(
            {
                "component_name": component,
                "old_tag": old_tag,
                "compare_url": compare_url,
                "path_diff_links": path_diff_links,
            }
        )
        seen_components.add(component)

    if not changed_components:
        fail(
            "No eligible components found in k8s-components compare flow for "
            f"prod-app-of-apps file '{values_file_path}'."
        )

    write_output("changed_components_count", str(len(changed_components)))
    write_output("changed_components_json", json.dumps(changed_components, separators=(",", ":")))

    if verbose:
        print(f"Detected source entries: {len(source_entries)}")
        print(f"Target repo matches: {sum(1 for e in source_entries if normalize_repo_ref(e['repo_url']) == target_repo_ref)}")
        print(f"Changed components: {len(changed_components)}")


if __name__ == "__main__":
    main()
