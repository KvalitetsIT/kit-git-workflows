#!/usr/bin/env python3
"""
Apply targetRevision updates for one component across values files.

This script focuses only on "apply changes safely".
It keeps existing YAML formatting and only rewrites targetRevision values that
match the selected component and repo.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# Why this exists:
# The workflow runs scripts with `python -I` (isolated mode). In isolated mode,
# Python does not include the script directory on `sys.path`.
# We add it explicitly so this script can import shared local helpers.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from component_update_shared import normalize_repo_ref, update_file_for_component


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


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


def main() -> None:
    target_repo_url = os.getenv("TARGET_REPO_URL", "").strip()
    component_name = os.getenv("COMPONENT_NAME", "").strip()
    new_target_revision = os.getenv("NEW_TARGET_REVISION", "").strip()
    values_prod_path = os.getenv("VALUES_PROD_FILE", "").strip()

    required_env = {
        "TARGET_REPO_URL": target_repo_url,
        "COMPONENT_NAME": component_name,
        "NEW_TARGET_REVISION": new_target_revision,
        "VALUES_PROD_FILE": values_prod_path,
        "GITHUB_OUTPUT": os.getenv("GITHUB_OUTPUT", "").strip(),
    }
    missing = [name for name, value in required_env.items() if not value]
    if missing:
        fail(f"Missing required environment variable(s): {', '.join(missing)}")

    values_prod = Path(values_prod_path)
    if not values_prod.exists():
        fail(f"Values file not found: {values_prod_path}")

    sibling_values_files = sorted(
        p
        for p in values_prod.parent.iterdir()
        if p.is_file() and p.name.startswith("values-") and p.suffix.lower() in {".yml", ".yaml"}
    )
    if not sibling_values_files:
        fail(f"No sibling values-*.yml/yaml files found near {values_prod_path}")

    target_repo_ref = normalize_repo_ref(target_repo_url)
    any_changed = False
    changed_files: list[str] = []
    for candidate in sibling_values_files:
        changed = update_file_for_component(
            file_path=candidate,
            target_repo_ref=target_repo_ref,
            component_name=component_name,
            new_target_revision=new_target_revision,
        )
        any_changed = any_changed or changed
        if changed:
            changed_files.append(candidate.as_posix())
            print(f"Updated targetRevision in: {candidate.as_posix()}")

    if not any_changed:
        fail(
            "No targetRevision lines were updated for the selected component. "
            "This usually means the selected component was detected, but update matching did not find editable entries."
        )

    write_output("has_changes", "true")
    write_output("changed_files", "\n".join(changed_files))


if __name__ == "__main__":
    main()
