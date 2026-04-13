# Reusable workflow: PR Body Validation

This [reusable workflow][reusable workflow] validates pull request descriptions
against two quality gates:

- **Required text blocks** — regions marked with HTML comment tags must contain
  meaningful content.
- **Checklist validation** — all checklist items (`- [ ]`) in the PR body must
  be checked.

[reusable workflow]: https://docs.github.com/en/actions/using-workflows/reusing-workflows

## What the workflow does

### Required text check

1. Looks for `<!-- required-text-start -->...<!-- required-text-end -->` blocks
   in the PR body.
2. If no blocks are found, the check passes (no-op).
3. If blocks exist, each must contain at least `min_length` non-whitespace
   characters.
4. Fails on unbalanced tags (start without end, or end without start).

### Checklist check

1. Strips any regions between `<!-- ignore-task-list-start -->` and
   `<!-- ignore-task-list-end -->` tags.
2. Counts unchecked checklist items (`- [ ]`) in the remaining body.
3. Fails if any unchecked items are found.

## Behavior

- The two checks run as independent jobs.
- If no required-text tags are present, the required text check is a no-op.
- Ignored regions let you exclude checklists that are informational or optional.

## Examples

### Basic usage

```yaml
name: PR Validation

on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

jobs:
  validate:
    permissions:
      pull-requests: read
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/pr-description-validation.yml@<some sha>
```

### Custom minimum length

```yaml
name: PR Validation

on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

jobs:
  validate:
    permissions:
      pull-requests: read
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/pr-description-validation.yml@<some sha>
    with:
      min_length: 20
```

## Inputs

| Name         | Type   | Description                                                      | Default | Required |
| ------------ | ------ | ---------------------------------------------------------------- | ------- | -------- |
| `min_length` | number | Minimum non-whitespace character count inside a required-text block. | `10`  | false    |

## Required permissions

The calling job should grant:

- `pull-requests: read`

## PR template example

A PR template using both features:

```markdown
## What has changed — and why?
<!-- required-text-start -->
Replace this with a description of your changes.
<!-- required-text-end -->

## Checklist

- [ ] I have completed necessary tests
- [ ] I have updated documentation

<!-- ignore-task-list-start -->
### Optional
- [ ] Nice-to-have item (ignored by the check)
<!-- ignore-task-list-end -->
```
