"""
Shared helpers for k8s-components update scripts.

This file contains the common building blocks used by:
- detect_components_for_update.py
- update_component_target_revisions.py

Goal:
Keep one shared place for normalization and YAML matching rules so behavior
stays predictable and easy to maintain.
"""

from __future__ import annotations

import re
from pathlib import Path


# Why this exists:
# Some files may contain tabs in indentation. YAML tools and regex logic can
# behave differently when tabs are present. We normalize to spaces first so all
# downstream logic sees a stable input format.
def normalize_leading_tabs_to_spaces(content: str, spaces_per_tab: int = 2) -> str:
    lines: list[str] = []
    for line in content.splitlines(keepends=True):
        # Keep line endings intact while normalizing only the leading indent.
        leading_len = len(line) - len(line.lstrip(" \t"))
        leading = line[:leading_len].replace("\t", " " * spaces_per_tab)
        lines.append(f"{leading}{line[leading_len:]}")
    return "".join(lines)


# Why this exists:
# The workflow can receive repo URLs in different forms (git@..., https://...).
# We normalize to owner/repo so comparisons are simple and reliable.
def normalize_repo_ref(value: str) -> str:
    text = (value or "").replace("\r", "").strip()
    for prefix in ("git@github.com:", "https://github.com/", "http://github.com/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    if text.endswith(".git"):
        text = text[:-4]
    return text.strip("/").strip()


# Why this exists:
# YAML values can be quoted or unquoted. We normalize that detail away before
# comparing values.
def normalize_yaml_scalar(value: str) -> str:
    trimmed = (value or "").strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
        return trimmed[1:-1]
    return trimmed


# Why this exists:
# We only want to replace the value while preserving quote style if one exists.
def replacement_value(existing_raw_value: str, new_target_revision: str) -> str:
    existing_raw = existing_raw_value.strip()
    if len(existing_raw) >= 2 and existing_raw[0] == existing_raw[-1] and existing_raw[0] in {"'", '"'}:
        return f"{existing_raw[0]}{new_target_revision}{existing_raw[0]}"
    return new_target_revision


# Why this exists:
# We use this to reason about YAML block boundaries in the line-based updater.
def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


# Why this exists:
# We keep path comparison stable by removing common visual variations.
def normalize_component_path(path_value: str) -> str:
    component = normalize_yaml_scalar(path_value)
    component = component.replace("\\", "/").lstrip("./").lstrip("/")
    return component.rstrip("/")


# Why this exists:
# The updater edits only matching targetRevision lines and keeps other formatting.
def update_source_map_block(
    *,
    lines: list[str],
    block_start: int,
    block_end: int,
    source_indent: int,
    target_repo_ref: str,
    component_name: str,
    new_target_revision: str,
) -> bool:
    field_indent = None
    for line_idx in range(block_start, block_end):
        stripped = lines[line_idx].strip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = indent_of(lines[line_idx])
        if line_indent > source_indent and (field_indent is None or line_indent < field_indent):
            field_indent = line_indent
    if field_indent is None:
        return False

    repo_url_seen = False
    repo_url_matches = False
    target_line_idx = None
    target_line_match = None
    component_matches = False
    for line_idx in range(block_start, block_end):
        stripped = lines[line_idx].strip()
        if not stripped or stripped.startswith("#") or indent_of(lines[line_idx]) != field_indent:
            continue

        repo_match = re.match(r"^\s*repoURL:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[line_idx])
        if repo_match:
            repo_url_seen = True
            repo_url_matches = normalize_repo_ref(normalize_yaml_scalar(repo_match.group(1))) == target_repo_ref

        target_match = re.match(r"^(\s*targetRevision:\s*)([^#\r\n]+?)(\s*(?:#.*)?)(\r?\n?)$", lines[line_idx])
        if target_match:
            target_line_idx = line_idx
            target_line_match = target_match

        path_match = re.match(r"^\s*path:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[line_idx])
        if path_match:
            component_matches = normalize_component_path(path_match.group(1)) == component_name

    # If repoURL is not explicitly present in the block, it may come from a YAML
    # merge/anchor. In that case we allow update based on component/path match.
    if (repo_url_seen and not repo_url_matches) or not component_matches:
        return False

    # If targetRevision is inherited (no explicit line in this block), add one.
    if target_line_idx is None or target_line_match is None:
        new_line = f"{' ' * field_indent}targetRevision: {new_target_revision}\n"
        lines.insert(block_end, new_line)
        return True

    current_value = normalize_yaml_scalar(target_line_match.group(2))
    if current_value == new_target_revision:
        return False

    replacement = replacement_value(target_line_match.group(2), new_target_revision)
    lines[target_line_idx] = (
        f"{target_line_match.group(1)}{replacement}{target_line_match.group(3)}{target_line_match.group(4)}"
    )
    return True


# Why this exists:
# Same as above, but for one item inside `sources:`.
def update_one_sources_item(
    *,
    lines: list[str],
    item_start: int,
    item_end: int,
    item_indent: int,
    target_repo_ref: str,
    component_name: str,
    new_target_revision: str,
) -> bool:
    repo_url_seen = False
    repo_url_matches = False
    target_line_idx = None
    target_line_match = None
    component_matches = False

    item_start_repo_match = re.match(r"^\s*-\s*repoURL:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[item_start])
    if item_start_repo_match:
        repo_url_seen = True
        repo_url_matches = normalize_repo_ref(normalize_yaml_scalar(item_start_repo_match.group(1))) == target_repo_ref

    item_start_target_match = re.match(r"^(\s*-\s*targetRevision:\s*)([^#\r\n]+?)(\s*(?:#.*)?)(\r?\n?)$", lines[item_start])
    if item_start_target_match:
        target_line_idx = item_start
        target_line_match = item_start_target_match

    item_start_path_match = re.match(r"^\s*-\s*path:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[item_start])
    if item_start_path_match:
        component_matches = normalize_component_path(item_start_path_match.group(1)) == component_name

    field_indent = None
    for line_idx in range(item_start + 1, item_end):
        stripped = lines[line_idx].strip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = indent_of(lines[line_idx])
        if line_indent > item_indent and (field_indent is None or line_indent < field_indent):
            field_indent = line_indent

    if field_indent is not None:
        for line_idx in range(item_start + 1, item_end):
            stripped = lines[line_idx].strip()
            if not stripped or stripped.startswith("#") or indent_of(lines[line_idx]) != field_indent:
                continue

            repo_match = re.match(r"^\s*repoURL:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[line_idx])
            if repo_match:
                repo_url_seen = True
                repo_url_matches = repo_url_matches or (
                    normalize_repo_ref(normalize_yaml_scalar(repo_match.group(1))) == target_repo_ref
                )

            target_match = re.match(r"^(\s*targetRevision:\s*)([^#\r\n]+?)(\s*(?:#.*)?)(\r?\n?)$", lines[line_idx])
            if target_match:
                target_line_idx = line_idx
                target_line_match = target_match

            path_match = re.match(r"^\s*path:\s*([^#\r\n]+?)\s*(?:#.*)?\r?\n?$", lines[line_idx])
            if path_match:
                component_matches = component_matches or (normalize_component_path(path_match.group(1)) == component_name)

    # If repoURL is not explicitly present in this item, it may be inherited
    # from a YAML merge/anchor. Then we allow update based on component/path.
    if (repo_url_seen and not repo_url_matches) or not component_matches:
        return False

    # If targetRevision is inherited (no explicit line in this item), add one.
    if target_line_idx is None or target_line_match is None:
        insert_indent = field_indent if field_indent is not None else (item_indent + 2)
        new_line = f"{' ' * insert_indent}targetRevision: {new_target_revision}\n"
        lines.insert(item_end, new_line)
        return True

    current_value = normalize_yaml_scalar(target_line_match.group(2))
    if current_value == new_target_revision:
        return False

    replacement = replacement_value(target_line_match.group(2), new_target_revision)
    lines[target_line_idx] = (
        f"{target_line_match.group(1)}{replacement}{target_line_match.group(3)}{target_line_match.group(4)}"
    )
    return True


# Why this exists:
# Shared line-based update engine used by the update entry script.
def update_file_for_component(
    file_path: Path,
    target_repo_ref: str,
    component_name: str,
    new_target_revision: str,
) -> bool:
    normalized = normalize_leading_tabs_to_spaces(file_path.read_text(encoding="utf-8"))
    lines = normalized.splitlines(keepends=True)
    changed = False

    i = 0
    while i < len(lines):
        source_single_match = re.match(r"^(\s*)(?:-\s*)?source:\s*(?:#.*)?\r?\n?$", lines[i])
        sources_match = re.match(r"^(\s*)(?:-\s*)?sources:\s*(?:#.*)?\r?\n?$", lines[i])
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
                target_repo_ref=target_repo_ref,
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
            changed = update_one_sources_item(
                lines=lines,
                item_start=item_start,
                item_end=item_end,
                item_indent=indent_of(lines[item_start]),
                target_repo_ref=target_repo_ref,
                component_name=component_name,
                new_target_revision=new_target_revision,
            ) or changed

    if changed:
        file_path.write_text("".join(lines), encoding="utf-8")
    return changed
