# Shared GitHub Actions Workflows (kit-git-workflows)

This repository contains **reusable GitHub Actions workflows** that are meant to be referenced from other repositories in the **KvalitetsIT** GitHub org. The goal is to keep workflow logic in one place, while each repo can configure it with its own secrets/variables.

---

## How to use a shared workflow from your repo

1. In **your repo**, create a workflow file, for example:

- `.github/workflows/use-kit-git-workflows.yml`

2. Add a job that references a workflow in this repository using `uses:`:

```yaml
name: Use a shared workflow from kit-git-workflows

on:
  workflow_dispatch:
  schedule:
    - cron: "0 8 * * *"

jobs:
  run_shared_workflow:
    uses: KvalitetsIT/kit-git-workflows/.github/workflows/<WORKFLOW_FILE>.yml@<REF>
    secrets: inherit
```

Each workflow has its own README.md file with more details regarding variables and so on.
