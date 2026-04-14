# Reusable workflow: Notify Slack about merged PRs missing production release labels

This [reusable workflow][reusable workflow] searches for pull requests that have
been merged but are missing production release labels, and posts a reminder to
Slack via an incoming webhook.

[reusable workflow]: https://docs.github.com/en/actions/using-workflows/reusing-workflows

## What the workflow does

1. Searches for PRs that are merged into the target branch, created after a
   cutoff date, and merged more than a configurable number of days ago.
2. Filters out PRs that already have the "tested" or "no impact" labels.
3. Builds a Slack message with links to the matching PRs and mentions the
   PR author (via a GitHub-to-Slack user ID map).
4. Sends the message to Slack using an incoming webhook.

## Behavior

- If no matching PRs are found, the Slack step is skipped entirely.
- Results are capped at 50 PRs per message.
- The GitHub-to-Slack user ID map is maintained inside the workflow. Users
  not in the map are mentioned by their GitHub username instead.
- The workflow paginates through up to 1,000 search results (10 pages of 100).

## Examples

### Basic usage (scheduled)

```yaml
name: Slack reminder — missing release labels

on:
  schedule:
    - cron: "0 8 * * 1-5" # weekdays at 08:00 UTC
  workflow_dispatch:

jobs:
  notify:
    permissions:
      contents: read
      pull-requests: read
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/notify-slack-prs-merged-to-main-missing-production-release-labels.yaml@<some sha>
    secrets:
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL_KIT_HOSTING_GITHUB }}
```

### Custom branch and labels

```yaml
name: Slack reminder — missing release labels

on:
  schedule:
    - cron: "0 8 * * 1-5"

jobs:
  notify:
    permissions:
      contents: read
      pull-requests: read
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/notify-slack-prs-merged-to-main-missing-production-release-labels.yaml@<some sha>
    with:
      target_branch: release
      merged_days_ago: 14
      label_tested: "released"
      label_no_impact: "no-release-needed"
    secrets:
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

## Inputs

| Name             | Type   | Description                                                     | Default                          | Required |
| ---------------- | ------ | --------------------------------------------------------------- | -------------------------------- | -------- |
| `target_branch`  | string | Base/target branch to check (e.g. `main`, `master`, `release`). | `main`                           | false    |
| `created_after`  | string | Only include PRs created after this date (`YYYY-MM-DD`).        | `2025-12-03`                     | false    |
| `merged_days_ago`| number | Only include PRs merged more than this many days ago.           | `7`                              | false    |
| `label_tested`   | string | Label indicating production release has been tested.            | `production release tested`      | false    |
| `label_no_impact`| string | Label indicating the PR has no production impact.               | `production release no impact`   | false    |

## Secrets

| Name               | Description                    | Required |
| ------------------ | ------------------------------ | -------- |
| `SLACK_WEBHOOK_URL`| Slack incoming webhook URL.    | true     |

## Required permissions

The calling job should grant:

- `contents: read`
- `pull-requests: read`

## Setup

1. **Create a Slack incoming webhook** for your channel.
2. **Add the webhook URL as a repository secret:**
   GitHub → Repo → Settings → Secrets and variables → Actions → Secrets → New repository secret
   - Name: `SLACK_WEBHOOK_URL_KIT_HOSTING_GITHUB` (or any name you prefer)
   - Value: your Slack incoming webhook URL
3. **Call the reusable workflow** on a schedule from your repo (see examples above).
   All inputs have sensible defaults — you only need to pass the ones you want to override.
