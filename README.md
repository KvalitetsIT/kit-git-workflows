# Shared GitHub Actions Workflows (kit-git-workflows)

This repository contains **reusable GitHub Actions workflows** that are meant to be referenced from other repositories in the **KvalitetsIT** GitHub org. The goal is to keep workflow logic in one place, while each repo can configure it with its own secrets/variables.

## Available Workflows

| Workflow | Description | Docs |
| :------- | :---------- | :--- |
| [helm-pr.yaml](.github/workflows/helm-pr.yaml) | Lints and tests Helm charts using chart-testing and a KinD cluster. | [Docs](.github/workflows/helm-pr.md) |
| [pr-description-validation.yml](.github/workflows/pr-description-validation.yml) | Validates PR descriptions: required text blocks and checklist completion. | [Docs](.github/workflows/pr-description-validation.md) |
| [notify-slack-prs-merged-to-main-missing-production-release-labels.yaml](.github/workflows/notify-slack-prs-merged-to-main-missing-production-release-labels.yaml) | Sends a Slack reminder for merged PRs missing production release labels. | [Docs](.github/workflows/notify-slack-prs-merged-to-main-missing-production-release-labels.md) |
| [reusable-zizmor.yaml](.github/workflows/reusable-zizmor.yaml) | Runs zizmor security analysis on GitHub Actions files and uploads SARIF results. | [Docs](.github/workflows/reusable-zizmor.md) |

Each workflow has its own documentation with detailed inputs, examples, and setup instructions.

---

## How to use a shared workflow from your repo

1. In **your repo**, create a workflow file, for example:

- `.github/workflows/use-kit-git-workflows.yml`

2. Add a job that references a workflow in this repository using `uses:`:

```yaml
name: Notify Slack about merged PRs missing production release labels

on:
  schedule:
    - cron: "0 8 * * *"
  workflow_dispatch:

jobs:
  remind:
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/notify-slack-prs-merged-to-main-missing-production-release-labels.yaml@main
    secrets:
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL_KIT_HOSTING_GITHUB }}
    with:
      target_branch: "main"
      created_after: "2025-12-03"
      merged_days_ago: 7
      label_tested: "production release tested"
      label_no_impact: "production release no impact"
```
