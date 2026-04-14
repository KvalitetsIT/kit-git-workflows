# Reusable workflow: Helm PR

This [reusable workflow][reusable workflow] lints and tests Helm charts that have
changed in a pull request. It uses [chart-testing (`ct`)][chart-testing] to
detect changed charts, lint them, and optionally install them in a
[KinD][kind] cluster.

[reusable workflow]: https://docs.github.com/en/actions/using-workflows/reusing-workflows
[chart-testing]: https://github.com/helm/chart-testing
[kind]: https://kind.sigs.k8s.io/

## What the workflow does

1. Checks out the repository with full history (needed by `ct` to detect changes).
2. Sets up Helm, Python, and chart-testing.
3. Lists changed charts using `ct list-changed`.
4. Lints changed charts with `ct lint`.
5. If charts have changed, creates a KinD cluster.
6. Optionally installs CRDs and creates namespaces.
7. Runs `ct install` to install and test the changed charts.

## Behavior

- The workflow lints charts detected as changed by `ct`; if none have changed, `ct lint` may no-op.
- Chart installation only runs when `ct list-changed` detects changes.
- CRD installation waits for each CRD to be established before continuing.
- Namespace creation is idempotent — existing namespaces are not recreated.

## Examples

### Basic usage

```yaml
name: Helm PR

on:
  pull_request:
    paths:
      - "charts/**"

jobs:
  helm:
    name: Helm Lint & Test
    permissions:
      contents: read
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/helm-pr.yaml@<some sha>
```

### With CRDs and custom namespaces

```yaml
name: Helm PR

on:
  pull_request:
    paths:
      - "charts/**"

jobs:
  helm:
    name: Helm Lint & Test
    permissions:
      contents: read
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/helm-pr.yaml@<some sha>
    with:
      crd_urls: |
        https://raw.githubusercontent.com/cert-manager/cert-manager/v1.14.5/deploy/crds/cert-manager.crds.yaml
      namespaces: |
        monitoring
        cert-manager
```

### With custom chart-testing config

```yaml
name: Helm PR

on:
  pull_request:
    paths:
      - "charts/**"

jobs:
  helm:
    name: Helm Lint & Test
    permissions:
      contents: read
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/helm-pr.yaml@<some sha>
    with:
      ct_config: ".github/ct.yaml"
```

## Inputs

| Name             | Type   | Description                                                          | Default    | Required |
| ---------------- | ------ | -------------------------------------------------------------------- | ---------- | -------- |
| `helm_version`   | string | Helm version to install.                                             | `v3.17.0`  | false    |
| `python_version` | string | Python version to install (required by chart-testing).               | `3.x`      | false    |
| `ct_config`      | string | Path to the chart-testing configuration file.                        | `ct.yaml`  | false    |
| `crd_urls`       | string | Newline-separated list of CRD manifest URLs to install before testing. | `""`     | false    |
| `namespaces`     | string | Newline-separated list of namespaces to create before testing.       | `""`       | false    |

## Required permissions

The calling job should grant:

- `contents: read`
