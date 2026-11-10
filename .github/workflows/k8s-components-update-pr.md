# Workflow: Create PR for k8s-components updates

This workflow creates PRs that keep
k8s-components references updated in Argo app-of-apps YAML files by changing
only `sources[].targetRevision` when the matching
`sources[].repoURL` equals a configured value.

Default `repoURL` match value:

- `git@github.com:KvalitetsIT/k8s-components.git`

## What the workflow does

1. Resolves the source repository from `source_repo_url`.
2. Fetches the newest release tag (fallback: newest tag).
3. Uses the configured app-of-apps prod file path as the source of component candidates.
4. For each candidate component, compares old tag in the configured prod app-of-apps file against newest tag and checks whether files under the component `path` changed.
5. Creates one pull request per qualifying component (up to `max_prs_per_run`, default `5`) with compare links.
6. Fails the run when no qualifying component changes are found.

## Behavior and scope

- Supports both `source` and `sources[]` Argo formats.
- Candidate components are read from `prod-app-of-apps-file-path` on `target_branch` (default `main`).
- A component is selected only when compare `<old_tag>...<new_tag>` contains changed files under that component `path`.
- PR body includes the full compare link and per-file SHA-256 compare anchor links.
- PR body includes one organization-wide search link for merged PRs that share the same labels as the created PR.
- PR title includes component and version transition, for example `Update cert-manager (26.05.3 => 26.11.7)`.
- Uses the template at `pr_template_path` from `KvalitetsIT/.github@main` and replaces `Type here` with the generated update description before PR creation. If that path does not exist, the job fails.
- Ensures `AutoUpdate` label and adds a version label (for example `26.11.7`) plus component label (for example `cert-manager`) when label creation is permitted; otherwise missing labels are skipped.
- `Chart.yaml` files are excluded.
- Creates one PR per selected component path (for example `reflector`), and updates matching component entries in all `values-*.yml`/`values-*.yaml` files in the same directory as `prod-app-of-apps-file-path`.
- Closes existing open PRs for the same component before creating the new PR, except when an open PR already exists with the exact same title (that PR is kept).
- Newly created component update PRs are created as **Draft**.
- When old component PRs are closed, the new PR inherits milestone from the first matching old PR that had a milestone.
- No PR is created when there are no changes.
- File updates only change `targetRevision` value lines for matching component entries, preserving existing indentation/formatting.
- The run fails if `prod-app-of-apps-file-path` does not exist or if zero eligible components are detected after compare checks.
- After PR creation, a separate job can add a PR comment with release-note matches containing the component name between old and new version (max entries is configurable by `max_release_notes`, default `5`).

## Example usage from another repository

```yaml
name: Create PR for k8s-components updates

on:
  workflow_dispatch:
  schedule:
    - cron: "0 6 * * 1"

jobs:
  update-k8s-components:
    permissions:
      contents: write
      pull-requests: write
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/k8s-components-update-pr.yaml@main
    with:
      source_repo_url: git@github.com:KvalitetsIT/k8s-components.git
      prod-app-of-apps-file-path: deployment/apps/infrastructure/values-prod.yaml
      target_branch: main
    secrets:
      k8s_repo_token: ${{ secrets.KIT_GITHUB_ACCESS }}
```

## Inputs

| Name              | Type   | Description                                          | Default Value                                     | Required |
| ----------------- | ------ | ---------------------------------------------------- | ------------------------------------------------- | -------- |
| `source_repo_url` | string | Exact repoURL to match in `sources[].repoURL`.      | `git@github.com:KvalitetsIT/k8s-components.git`  | false    |
| `prod-app-of-apps-file-path` | string | Full path to the app-of-apps `values-prod` file that uses `argocd-apps-chart`. | - | true |
| `target_branch`   | string | Branch to read app-of-apps values files from and use as PR base.| `main`                                            | false    |
| `max_prs_per_run` | number | Maximum number of component PRs to create per run.  | `5`                                               | false    |
| `max_release_notes` | number | Maximum number of matched release-note entries shown in the PR comment. | `5`                                     | false    |
| `pr_labels`       | string | Comma-separated additional labels to apply to created PRs. | `""`                                         | false    |
| `pr_template_path`| string | Path in `KvalitetsIT/.github@main` to the PR template file used for replacement. | `PULL_REQUEST_TEMPLATE.md` | false |

## Secrets

| Name                | Description                                                                                      | Required |
| ------------------- | ------------------------------------------------------------------------------------------------ | -------- |
| `k8s_repo_token` | Token used when calling source-repo APIs (release/tag/compare) and `KvalitetsIT/.github` template API. | true    |

No secret fallback chain is used. If you need to use another secret value, map that secret explicitly to `k8s_repo_token` in the caller workflow.

## Required permissions

The calling job should grant:

- `contents: write`
- `pull-requests: write`
- `issues: write`

The `k8s_repo_token` must have these repository permissions:

- **Source repository (`source_repo_url`):** `Contents: read` (for releases/tags/compare lookup)
- **`KvalitetsIT/.github` repository:** `Contents: read` (for `pr_template_path` fetch)

All target-repository operations (close/create PR, labels, push) use `github.token`.
