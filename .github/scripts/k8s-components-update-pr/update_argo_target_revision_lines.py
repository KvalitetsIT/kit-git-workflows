"""
Responsibility: update only Argo component `targetRevision` values that match one repository+component pair.

This script intentionally preserves file formatting by editing only the matched value token on
matched `targetRevision` lines. It supports both:
- `source:` map structure
- `sources:` array structure

Exit codes:
- 0: file changed
- 1: no change
- 2: usage error
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def indent_of(line: str) -> int:
    """Return leading-space indentation width for one YAML line."""
    return len(line) - len(line.lstrip(" "))


def normalize_yaml_scalar(value: str) -> str:
    """Trim whitespace and unwrap matching single/double quotes."""
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
        return trimmed[1:-1]
    return trimmed


def replacement_value(existing_raw_value: str, new_target_revision: str) -> str:
    """Preserve existing quote style while replacing scalar value."""
    existing_raw = existing_raw_value.strip()
    if len(existing_raw) >= 2 and existing_raw[0] == existing_raw[-1] and existing_raw[0] in {"'", '"'}:
        return f"{existing_raw[0]}{new_target_revision}{existing_raw[0]}"
    return new_target_revision


def update_source_map_block(
    *,
    lines: list[str],
    block_start: int,
    block_end: int,
    source_indent: int,
    target_repo_url: str,
    component_name: str,
    new_target_revision: str,
) -> bool:
    """Update one `source:` map block when repo/path/targetRevision all match."""
    field_indent = None
    for line_idx in range(block_start, block_end):
        stripped = lines[line_idx].strip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = indent_of(lines[line_idx])
        if line_indent > source_indent:
            if field_indent is None or line_indent < field_indent:
                field_indent = line_indent
    if field_indent is None:
        return False

    repo_url_matches = False
    target_line_idx = None
    target_line_match = None
    component_matches = False

    for line_idx in range(block_start, block_end):
        stripped = lines[line_idx].strip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = indent_of(lines[line_idx])
        if line_indent != field_indent:
            continue

        repo_match = re.match(r"^\s*repoURL:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[line_idx])
        if repo_match:
            repo_url_matches = normalize_yaml_scalar(repo_match.group(1)) == target_repo_url

        target_match = re.match(r"^(\s*targetRevision:\s*)([^#\r\n]+?)(\s*(?:#.*)?)(\r?\n?)$", lines[line_idx])
        if target_match:
            target_line_idx = line_idx
            target_line_match = target_match

        path_match = re.match(r"^\s*path:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[line_idx])
        if path_match:
            component_matches = normalize_yaml_scalar(path_match.group(1)) == component_name

    if not repo_url_matches or target_line_idx is None or target_line_match is None or not component_matches:
        return False

    current_value = normalize_yaml_scalar(target_line_match.group(2))
    if current_value == new_target_revision:
        return False

    replacement = replacement_value(target_line_match.group(2), new_target_revision)
    lines[target_line_idx] = (
        f"{target_line_match.group(1)}{replacement}{target_line_match.group(3)}{target_line_match.group(4)}"
    )
    return True


def update_one_sources_item(
    *,
    lines: list[str],
    item_start: int,
    item_end: int,
    item_indent: int,
    target_repo_url: str,
    component_name: str,
    new_target_revision: str,
) -> bool:
    """Update one `sources[]` item when repo/path/targetRevision all match."""
    repo_url_matches = False
    target_line_idx = None
    target_line_match = None
    component_matches = False

    item_start_repo_match = re.match(r"^\s*-\s*repoURL:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[item_start])
    if item_start_repo_match:
        repo_url_matches = normalize_yaml_scalar(item_start_repo_match.group(1)) == target_repo_url

    item_start_target_match = re.match(r"^(\s*-\s*targetRevision:\s*)([^#\r\n]+?)(\s*(?:#.*)?)(\r?\n?)$", lines[item_start])
    if item_start_target_match:
        target_line_idx = item_start
        target_line_match = item_start_target_match

    item_start_path_match = re.match(r"^\s*-\s*path:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[item_start])
    if item_start_path_match:
        component_matches = normalize_yaml_scalar(item_start_path_match.group(1)) == component_name

    field_indent = None
    for line_idx in range(item_start + 1, item_end):
        stripped = lines[line_idx].strip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = indent_of(lines[line_idx])
        if line_indent > item_indent:
            if field_indent is None or line_indent < field_indent:
                field_indent = line_indent

    if field_indent is not None:
        for line_idx in range(item_start + 1, item_end):
            stripped = lines[line_idx].strip()
            if not stripped or stripped.startswith("#"):
                continue
            line_indent = indent_of(lines[line_idx])
            if line_indent != field_indent:
                continue

            repo_match = re.match(r"^\s*repoURL:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[line_idx])
            if repo_match:
                repo_url_matches = repo_url_matches or (normalize_yaml_scalar(repo_match.group(1)) == target_repo_url)

            target_match = re.match(r"^(\s*targetRevision:\s*)([^#\r\n]+?)(\s*(?:#.*)?)(\r?\n?)$", lines[line_idx])
            if target_match:
                target_line_idx = line_idx
                target_line_match = target_match

            path_match = re.match(r"^\s*path:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[line_idx])
            if path_match:
                component_matches = component_matches or (normalize_yaml_scalar(path_match.group(1)) == component_name)

    if not repo_url_matches or target_line_idx is None or target_line_match is None or not component_matches:
        return False

    current_value = normalize_yaml_scalar(target_line_match.group(2))
    if current_value == new_target_revision:
        return False

    replacement = replacement_value(target_line_match.group(2), new_target_revision)
    lines[target_line_idx] = (
        f"{target_line_match.group(1)}{replacement}{target_line_match.group(3)}{target_line_match.group(4)}"
    )
    return True


def update_file(file_path: Path, target_repo_url: str, component_name: str, new_target_revision: str) -> bool:
    """Update targetRevision lines for matching Argo source/sources entries in one file."""
    original = file_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changed = False

    i = 0
    while i < len(lines):
        source_single_match = re.match(r"^(\s*)source:\s*(?:#.*)?\r?\n?$", lines[i])
        sources_match = re.match(r"^(\s*)sources:\s*(?:#.*)?\r?\n?$", lines[i])
        if not source_single_match and not sources_match:
            i += 1
            continue

        if source_single_match:
            source_indent = len(source_single_match.group(1))
            block_start = i + 1
            i = block_start
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped and not stripped.startswith("#") and indent_of(lines[i]) <= source_indent:
                    break
                i += 1
            block_end = i
            changed = update_source_map_block(
                lines=lines,
                block_start=block_start,
                block_end=block_end,
                source_indent=source_indent,
                target_repo_url=target_repo_url,
                component_name=component_name,
                new_target_revision=new_target_revision,
            ) or changed
            continue

        sources_indent = len(sources_match.group(1))
        block_start = i + 1
        i = block_start
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped and not stripped.startswith("#"):
                line_indent = indent_of(lines[i])
                if line_indent < sources_indent:
                    break
                if line_indent == sources_indent and not re.match(r"^\s*-\s+", lines[i]):
                    break
            i += 1
        block_end = i

        first_outer_item_start = next(
            (
                idx
                for idx in range(block_start, block_end)
                if re.match(r"^\s*-\s+", lines[idx]) and indent_of(lines[idx]) >= sources_indent
            ),
            None,
        )
        if first_outer_item_start is None:
            continue

        outer_item_indent = indent_of(lines[first_outer_item_start])
        item_starts = [
            idx
            for idx in range(first_outer_item_start, block_end)
            if re.match(r"^\s*-\s+", lines[idx]) and indent_of(lines[idx]) == outer_item_indent
        ]
        for idx, item_start in enumerate(item_starts):
            item_end = item_starts[idx + 1] if idx + 1 < len(item_starts) else block_end
            item_indent = indent_of(lines[item_start])
            changed = update_one_sources_item(
                lines=lines,
                item_start=item_start,
                item_end=item_end,
                item_indent=item_indent,
                target_repo_url=target_repo_url,
                component_name=component_name,
                new_target_revision=new_target_revision,
            ) or changed

    if changed:
        file_path.write_text("".join(lines), encoding="utf-8")
    return changed


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: update_argo_target_revision_lines.py <file_path>", file=sys.stderr)
        return 2

    file_path = Path(sys.argv[1])
    changed = update_file(
        file_path=file_path,
        target_repo_url=os.environ["TARGET_REPO_URL"],
        component_name=os.environ["COMPONENT_NAME"],
        new_target_revision=os.environ["NEW_TARGET_REVISION"],
    )
    return 0 if changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
