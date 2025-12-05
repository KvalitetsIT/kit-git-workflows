# Shared GitHub Actions Workflows (kit-git-workflows)

This repository contains **reusable GitHub Actions workflows** that are meant to be referenced from other repositories in the **KvalitetsIT** GitHub org. The goal is to keep workflow logic in one place, while each repo can configure it with its own secrets/variables.

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
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/notify-slack-prs-merged-to-main-missing-production-release-labels/notify-slack-prs-merged-to-main-missing-production-release-labels.yaml@main
    secrets:
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL_KIT_HOSTING_GITHUB }}
    with:
      target_branch: "main"
      created_after: "2025-12-03"
      merged_days_ago: 7
      label_tested: "production release tested"
      label_no_impact: "production release no impact"
```

Each workflow has its own README.md file with more details regarding variables and so on.
