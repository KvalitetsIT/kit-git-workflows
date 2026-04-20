# Reusable workflow: Argo CD Diff Preview

This [reusable workflow][reusable workflow] generates a diff of Argo CD
Application manifests between a pull request branch and its base branch, and
posts the result as a PR comment.

It is intended for repositories using a Helm [App-of-Apps][app-of-apps] pattern
where Application CRs are not raw YAML files but rendered from a Helm chart.

[reusable workflow]: https://docs.github.com/en/actions/using-workflows/reusing-workflows
[app-of-apps]: https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/
[argocd-diff-preview]: https://github.com/dag-andersen/argocd-diff-preview

## What the workflow does

1. Checks out the base branch and the PR merge ref into separate directories.
2. Pre-renders the App-of-Apps Helm chart for both branches using `helm template`.
3. Creates an Argo CD repository credentials secret using the provided SSH deploy key.
4. Runs [dagandersen/argocd-diff-preview][argocd-diff-preview] in a local [KinD][kind] cluster to render all Applications and produce a diff.
5. Posts (or updates) the diff as a comment on the pull request.

[kind]: https://kind.sigs.k8s.io/

## Prerequisites

A read-only SSH deploy key must be added to the repository:

1. Generate a key: `ssh-keygen -t ed25519 -f argocd-diff-key -C "development@kvalitetsit.dk" -N ""`
2. Add `argocd-diff-key.pub` as a deploy key under **Settings → Deploy keys** (read-only).
3. Add `argocd-diff-key` (private key) as a repository secret under **Settings → Secrets and variables → Actions** — this would be named `ARGOCD_DIFF_DEPLOY_KEY` as used in the example below.

## Example

```yaml
name: Argo CD Diff Preview

on:
  pull_request:
    branches:
      - prod
    types: [opened, synchronize, reopened]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  diff:
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/argocd-diff-preview.yaml@main
    with:
      app_of_apps_path: deployment/apps/infrastructure
      values_files: "values.yaml values-prod.yaml"
    secrets:
      argocd_diff_deploy_key: ${{ secrets.ARGOCD_DIFF_DEPLOY_KEY }}
```

## Inputs

| Name               | Type   | Description                                                                  | Default  | Required |
| ------------------ | ------ | ---------------------------------------------------------------------------- | -------- | -------- |
| `app_of_apps_path` | string | Path to the Helm App-of-Apps chart relative to the repository root.          | —        | true     |
| `values_files`     | string | Space-separated list of values files relative to `app_of_apps_path`.         | —        | true     |
| `tool_version`     | string | Version of the `dagandersen/argocd-diff-preview` Docker image to use.        | `v0.2.3` | false    |

## Secrets

| Name                    | Description                                          | Required |
| ----------------------- | ---------------------------------------------------- | -------- |
| `argocd_diff_deploy_key` | SSH private key with read access to the repository. | true     |
