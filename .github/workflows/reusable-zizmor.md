# Reusable workflow: zizmor

This [reusable workflow][reusable workflow] runs [`zizmor`][zizmor] against the
caller repository's GitHub Actions files and uploads the results as SARIF to
GitHub code scanning.

It is designed to give repositories a shared baseline while still allowing local
configuration when needed.

[reusable workflow]: https://docs.github.com/en/actions/using-workflows/reusing-workflows
[zizmor]: https://woodruffw.github.io/zizmor/
[zizmor-checks]: https://woodruffw.github.io/zizmor/audits/

## What the workflow does

At a high level, the workflow:

1. Determines which revision of the reusable workflow was called.
2. Tries to fetch the matching shared [default configuration].
3. Resolves which configuration file to use.
4. Installs the requested `zizmor` version.
5. Runs `zizmor` with the configured severity and confidence filters.
6. Uploads the SARIF output to GitHub code scanning.

See the [`zizmor` audit documentation][zizmor-checks] for the checks that can be reported.

## Behavior

- Findings are filtered with `--min-severity` and `--min-confidence`.
- Findings are uploaded to code scanning as SARIF.
- The workflow does **not** fail just because `zizmor` found issues.
- The workflow only fails if `zizmor` itself crashes.
- SARIF upload is configured with `continue-on-error: true`, so upload problems
  do not fail the whole workflow.

## Examples

### Basic usage

```yaml
name: GitHub Actions security analysis

on:
  pull_request:
    paths:
      - ".github/**"
  push:
    branches:
      - main
    paths:
      - ".github/**"

jobs:
  zizmor:
    name: Run zizmor
    permissions:
      actions: read
      contents: read
      id-token: write
      security-events: write
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/reusable-zizmor.yaml@<some sha>
```

### Show only medium-and-up findings

```yaml
name: GitHub Actions security analysis

on:
  pull_request:
    paths:
      - ".github/**"

jobs:
  zizmor:
    name: Run zizmor
    permissions:
      actions: read
      contents: read
      id-token: write
      security-events: write
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/reusable-zizmor.yaml@<some sha>
    with:
      min-severity: medium
      min-confidence: medium
```

### Run offline and always use the shared config

```yaml
name: GitHub Actions security analysis

on:
  pull_request:
    paths:
      - ".github/**"

jobs:
  zizmor:
    name: Run zizmor
    permissions:
      actions: read
      contents: read
      id-token: write
      security-events: write
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/reusable-zizmor.yaml@<some sha>
    with:
      always-use-default-config: true
      zizmor-args: --offline
```

## Inputs

| Name                        | Type    | Description                                                                                     | Default Value | Required |
| --------------------------- | ------- | ----------------------------------------------------------------------------------------------- | ------------- | -------- |
| `min-severity`              | string  | Only show results at or above this severity. Possible values: `unknown`, `informational`, `low`, `medium`, `high`. | `low`         | false    |
| `min-confidence`            | string  | Only show results at or above this confidence level. Possible values: `unknown`, `low`, `medium`, `high`.           | `low`         | false    |
| `zizmor-version`            | string  | Version of `zizmor` to install.                                                                 | `latest`      | false    |
| `zizmor-args`               | string  | Additional arguments passed to `zizmor`.                                                        | `""`          | false    |
| `always-use-default-config` | boolean | Always use the shared [default configuration], even if the caller repository defines its own.   | `false`       | false    |

## Secrets

| Name    | Description                                                                      | Required |
| ------- | -------------------------------------------------------------------------------- | -------- |
| `token` | GitHub token for `zizmor` API calls. If omitted, the workflow uses `GITHUB_TOKEN`. | false    |

[default configuration]: ../zizmor.yml

## Configuration resolution

Unless `always-use-default-config` is `true`, the workflow resolves configuration
in this order:

1. `.github/zizmor.yml` in the caller repository
2. `zizmor.yml` in the caller repository
3. The shared [default configuration] for the called reusable workflow revision
4. `zizmor`'s built-in defaults

When `always-use-default-config: true` is set, the workflow skips the caller
repository config files and uses the shared default configuration when it is available.

## Required permissions

The calling job should grant:

- `actions: read`
- `contents: read`
- `id-token: write`
- `security-events: write`

`id-token: write` is used by the workflow to resolve which reusable workflow
revision was invoked, so it can fetch the matching shared config.

## Getting started

For most repositories, a good starting point is:

1. Trigger the workflow on changes under `.github/**`.
2. Start with the defaults, which report `low` severity and above with `low`
   confidence and above.
3. Tighten the filters later by raising `min-severity` or `min-confidence`.
4. Add a repository-specific `.github/zizmor.yml` or `zizmor.yml` only when you
   need repository-specific rules or ignores.

## Ignore findings

Specific findings can be ignored by [adding a comment to the affected line][zizmor-ignore-comment].

```yaml
uses: actions/checkout@v3 # zizmor: ignore[artipacked]
```

[zizmor-ignore-comment]: https://woodruffw.github.io/zizmor/usage/#with-comments

## Configuration

`zizmor` [can be configured][zizmor-config] with either `zizmor.yml` or
`.github/zizmor.yml` in the caller repository. This can be used to adjust rules
or [ignore findings and files][zizmor-ignore-config].

[zizmor-config]: https://woodruffw.github.io/zizmor/configuration/
[zizmor-ignore-config]: https://woodruffw.github.io/zizmor/usage/#with-zizmoryml
