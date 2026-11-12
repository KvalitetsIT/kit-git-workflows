"""
Responsibility: decide which components should get update PRs in this workflow run.

This script takes pre-extracted Argo source entries (as JSON) and selects components that:
- match the configured source repository URL
- are not already on the latest target revision
- have file changes in source-repo compare(old_tag...new_tag)

Configurable output keys (for reuse in other workflows):
- OUTPUT_COUNT_KEY (default: changed_components_count)
- OUTPUT_JSON_KEY (default: changed_components_json)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any


def normalize_repo_ref(value: str) -> str:
    """Normalize GitHub repo references to `owner/repo` form."""
    s = (value or "").replace("\r", "").strip()
    for prefix in ("git@github.com:", "https://github.com/", "http://github.com/"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    if s.endswith(".git"):
        s = s[:-4]
    return s.strip("/").strip()


def clean(value: str) -> str:
    """Trim surrounding whitespace and carriage returns."""
    return (value or "").replace("\r", "").strip()


def gh_compare(owner: str, repo: str, compare_ref: str) -> tuple[dict[str, Any] | None, str]:
    """Call GitHub compare API and return JSON payload or error text."""
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/compare/{compare_ref}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None, result.stdout + result.stderr
    try:
        return json.loads(result.stdout), ""
    except json.JSONDecodeError:
        return None, result.stdout


def parse_entries() -> list[dict[str, Any]]:
    """Parse ALL_ENTRIES_JSON into a list of dictionaries."""
    try:
        data = json.loads(os.environ.get("ALL_ENTRIES_JSON", "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def write_outputs(selected: list[dict[str, Any]]) -> None:
    """Persist workflow outputs for downstream matrix job usage."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        raise RuntimeError("GITHUB_OUTPUT is not set")

    count_key = os.environ.get("OUTPUT_COUNT_KEY", "changed_components_count")
    json_key = os.environ.get("OUTPUT_JSON_KEY", "changed_components_json")

    with open(output_file, "a", encoding="utf-8") as fh:
        fh.write(f"{count_key}={len(selected)}\n")
        fh.write(f"{json_key}={json.dumps(selected, separators=(',', ':'))}\n")


def main() -> int:
    max_prs_raw = os.environ.get("MAX_PRS_PER_RUN", "0")
    max_prs_per_run = int(max_prs_raw) if max_prs_raw.isdigit() else 0
    target_repo_ref = normalize_repo_ref(os.environ.get("TARGET_REPO_URL", ""))
    new_target_revision = clean(os.environ.get("NEW_TARGET_REVISION", ""))
    source_owner = os.environ.get("SOURCE_OWNER", "")
    source_repo = os.environ.get("SOURCE_REPO", "")
    prod_file = os.environ.get("PROD_APP_OF_APPS_FILE_PATH", "")

    all_entries = parse_entries()
    all_entries_total = len(all_entries)
    print(f"DEBUG file={prod_file} entries_total={all_entries_total}")
    if all_entries_total > 0:
        print("DEBUG first entries:")
        for item in all_entries[:5]:
            print(json.dumps(item, separators=(",", ":")))

    selected_components: list[dict[str, Any]] = []
    seen_components: set[str] = set()

    skipped_duplicate = 0
    skipped_already_latest = 0
    skipped_repo_mismatch = 0
    compare_api_failures = 0
    skipped_no_path_changes = 0
    stopped_due_to_max = 0
    matched_entries_total = 0

    for entry in all_entries:
        if len(selected_components) >= max_prs_per_run:
            stopped_due_to_max = 1
            break

        repo_ref = normalize_repo_ref(str(entry.get("repo_url") or ""))
        if repo_ref != target_repo_ref:
            skipped_repo_mismatch += 1
            continue
        matched_entries_total += 1

        component_name = clean(str(entry.get("component_name") or ""))
        old_tag = clean(str(entry.get("old_tag") or ""))
        if not component_name or not old_tag:
            continue
        if component_name in seen_components:
            skipped_duplicate += 1
            continue
        if old_tag == new_target_revision:
            skipped_already_latest += 1
            continue

        compare_ref = f"{old_tag}...{new_target_revision}"
        compare_url = f"https://github.com/{source_owner}/{source_repo}/compare/{compare_ref}"
        compare_data, compare_error = gh_compare(source_owner, source_repo, compare_ref)
        if compare_data is None:
            compare_api_failures += 1
            print(
                f"DEBUG compare API failed for component={component_name} "
                f"compare_ref={compare_ref}: {compare_error.strip()}"
            )
            continue

        matching_files: list[str] = []
        for file_entry in compare_data.get("files", []) or []:
            filename = str(file_entry.get("filename", "")).lstrip("/")
            if not filename:
                continue
            if filename == component_name or filename.startswith(f"{component_name}/"):
                matching_files.append(filename)

        if not matching_files:
            skipped_no_path_changes += 1
            continue

        path_diff_links: list[dict[str, str]] = []
        for filename in matching_files:
            diff_sha = hashlib.sha256(filename.encode()).hexdigest()
            path_diff_links.append(
                {
                    "filename": filename,
                    "compare_sha256_url": f"{compare_url}#diff-{diff_sha}",
                }
            )

        selected_components.append(
            {
                "component_name": component_name,
                "old_tag": old_tag,
                "compare_url": compare_url,
                "path_diff_links": path_diff_links,
            }
        )
        seen_components.add(component_name)

    print(
        "DEBUG summary: "
        f"entries_total={all_entries_total} "
        f"entries_repo_match={matched_entries_total} "
        f"selected={len(selected_components)} "
        f"skipped_repo_mismatch={skipped_repo_mismatch} "
        f"skipped_duplicate={skipped_duplicate} "
        f"skipped_already_latest={skipped_already_latest} "
        f"compare_api_failures={compare_api_failures} "
        f"skipped_no_path_changes={skipped_no_path_changes} "
        f"stopped_due_to_max={stopped_due_to_max}"
    )

    print(f"Selected {len(selected_components)} components for this run (max_prs_per_run={max_prs_per_run}).")
    for candidate in selected_components:
        print(f"- {candidate['component_name']} ({candidate['old_tag']} -> {new_target_revision})")

    if not selected_components:
        print(
            "::error::No eligible components found in k8s-components compare flow for "
            f"prod-app-of-apps file '{prod_file}'. See DEBUG logs above."
        )
        return 1

    write_outputs(selected_components)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
