from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def indent_of(line: str) -> int:
    """Return leading-space indentation width for a YAML line."""
    return len(line) - len(line.lstrip(" "))


def normalize_yaml_scalar(value: str) -> str:
    """Normalize a scalar by trimming whitespace and optional matching quotes."""
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
        return trimmed[1:-1]
    return trimmed


def update_file(file_path: Path, target_repo_url: str, component_name: str, new_target_revision: str) -> bool:
    """
    Update only matching targetRevision value lines while preserving file formatting.

    A line is updated when:
    - repoURL matches target_repo_url
    - path matches component_name
    - targetRevision exists and differs from new_target_revision
    Supports both `source:` and `sources:` Argo structures.
    """
    # Read raw file text and keep line endings so rewritten lines preserve formatting.
    original = file_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changed = False

    # Walk line-by-line and detect `source:` or `sources:` blocks.
    i = 0
    while i < len(lines):
        source_single_match = re.match(r"^(\s*)source:\s*(?:#.*)?\r?\n?$", lines[i])
        sources_match = re.match(r"^(\s*)sources:\s*(?:#.*)?\r?\n?$", lines[i])
        if not source_single_match and not sources_match:
            i += 1
            continue

        if source_single_match:
            # Handle single-object `source:` block.
            source_indent = len(source_single_match.group(1))
            block_start = i + 1
            i = block_start
            # Find where the `source:` block ends.
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped and not stripped.startswith("#") and indent_of(lines[i]) <= source_indent:
                    break
                i += 1
            block_end = i

            # Detect primary field indentation inside this block.
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
                continue

            # Track whether this block matches our component and repo.
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

            # Skip if required fields are not matched/found.
            if not repo_url_matches or target_line_idx is None or target_line_match is None or not component_matches:
                continue

            # Skip if already on desired revision.
            current_value = normalize_yaml_scalar(target_line_match.group(2))
            if current_value == new_target_revision:
                continue

            # Preserve original quoting style around targetRevision value.
            existing_raw = target_line_match.group(2).strip()
            if len(existing_raw) >= 2 and existing_raw[0] == existing_raw[-1] and existing_raw[0] in {"'", '"'}:
                replacement = f"{existing_raw[0]}{new_target_revision}{existing_raw[0]}"
            else:
                replacement = new_target_revision

            # Rewrite only the value part; keep whitespace/comments/newline suffix.
            lines[target_line_idx] = (
                f"{target_line_match.group(1)}{replacement}{target_line_match.group(3)}{target_line_match.group(4)}"
            )
            changed = True
            continue

        # Handle array-style `sources:` block with one or more `-` items.
        sources_indent = len(sources_match.group(1))
        block_start = i + 1
        i = block_start
        # Find where this `sources:` block ends.
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped and not stripped.startswith("#") and indent_of(lines[i]) <= sources_indent:
                break
            i += 1
        block_end = i

        # Collect item starts for each list entry under `sources:`.
        item_starts = []
        for idx in range(block_start, block_end):
            if re.match(r"^\s*-\s+", lines[idx]) and indent_of(lines[idx]) > sources_indent:
                item_starts.append(idx)

        # Evaluate each sources item independently.
        for idx, item_start in enumerate(item_starts):
            item_end = item_starts[idx + 1] if idx + 1 < len(item_starts) else block_end
            item_indent = indent_of(lines[item_start])

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

            # Determine nested field indentation for multiline list item style.
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

            # Skip items that do not fully match repo/path/targetRevision requirements.
            if not repo_url_matches or target_line_idx is None or target_line_match is None or not component_matches:
                continue

            # Skip if targetRevision is already correct.
            current_value = normalize_yaml_scalar(target_line_match.group(2))
            if current_value == new_target_revision:
                continue

            # Preserve existing quote style when replacing value.
            existing_raw = target_line_match.group(2).strip()
            if len(existing_raw) >= 2 and existing_raw[0] == existing_raw[-1] and existing_raw[0] in {"'", '"'}:
                replacement = f"{existing_raw[0]}{new_target_revision}{existing_raw[0]}"
            else:
                replacement = new_target_revision

            # Rewrite only matched targetRevision line for this sources item.
            lines[target_line_idx] = (
                f"{target_line_match.group(1)}{replacement}{target_line_match.group(3)}{target_line_match.group(4)}"
            )
            changed = True

    # Persist file only when at least one update happened.
    if changed:
        file_path.write_text("".join(lines), encoding="utf-8")
    return changed


def main() -> int:
    """CLI entrypoint used by the workflow; returns 0 when file changed, 1 when unchanged."""
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
    # Propagate exit code to the workflow step.
    raise SystemExit(main())
