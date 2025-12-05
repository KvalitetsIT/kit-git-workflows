# Slack reminder: merged PRs missing production-release labels

## Get started (per repo)

1. **Add Actions variables**  
   GitHub → **Repo** → **Settings** → **Secrets and variables** → **Actions** → **Variables** → **New repository variable**

   - `TARGET_BRANCH` = `main` (or whatever your repo uses)
   - _(optional)_ `CREATED_AFTER` = `2025-12-03` (YYYY-MM-DD)
   - _(optional)_ `MERGED_DAYS_AGO` = `7` (integer)

2. **Add Slack webhook secret**  
   GitHub → **Repo** → **Settings** → **Secrets and variables** → **Actions** → **Secrets** → **New repository secret**
   - `SLACK_WEBHOOK_URL_KIT_HOSTING_GITHUB` = `<your Slack Incoming Webhook URL>`

## What it does (conditions)

On schedule (and manual run), it:

- Searches for PRs that are:
  - **Merged**
  - **Targeting** `TARGET_BRANCH` (base branch)
  - **Created after** `CREATED_AFTER`
  - **Merged more than** `MERGED_DAYS_AGO` days ago
  - **Missing** label `production release tested`
  - **And also missing** label `production release no impact`
- Posts matching PRs as **clickable links** to Slack via the webhook
