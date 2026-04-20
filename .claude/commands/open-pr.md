You open a pull request from the current branch and request a review from GitHub Copilot. If a PR already exists, you add Copilot as a reviewer (if not already requested) instead of creating a new one. This skill does git + `gh` operations only — no file edits.

**Argument:** $ARGUMENTS (optional one-line PR title override; if empty, generate from commits)

## Deliverables

- A pull request on GitHub targeting the repo's main branch, with Copilot requested as a reviewer.
- The PR URL printed at the end so the user can open it.

## Scope Boundaries

**You MUST NOT:**
- Modify any files in the working tree. This skill is pure git/gh orchestration.
- Force-push or amend commits (`git push --force`, `git commit --amend`).
- Open a PR if one already exists for the branch — update the reviewer list on the existing PR instead.
- Push to `main` or another protected base branch.
- Run the `/copilot-review` fix loop — that's a separate skill.

**You MUST:**
- Work on the branch that is currently checked out. Do not switch branches.
- Use the repo's actual default branch (read it from `gh repo view --json defaultBranchRef`) — don't hardcode `main`.
- Follow Conventional Commits per `CLAUDE.md` → "Code conventions" when generating the PR title.
- Ensure Copilot is on the reviewer list at the end.

## Workflow

### Step 1: Verify branch state

```
git branch --show-current
```

If the current branch is the default branch (e.g. `main`), stop and tell the user: "Refusing to open a PR from the default branch — check out a feature branch first (or run `/pickup`)."

If the working tree is dirty (`git status --porcelain` non-empty), stop and tell the user to commit or stash first — don't silently stash.

### Step 2: Push unpushed commits

Run:

```
git rev-list --count @{u}..HEAD 2>/dev/null || echo "no-upstream"
```

- If the branch has no upstream yet, push with `git push -u origin <branch>`.
- If there are unpushed commits, push with `git push`.
- If fully in sync, skip.

### Step 3: Check for an existing PR

```
gh pr view --json number,url,state,isDraft,reviewRequests
```

- If this command succeeds and `state` is `OPEN`:
  - Note the PR number and URL.
  - Parse `reviewRequests` — look for an entry whose login is `Copilot` or whose bot slug matches `copilot-pull-request-reviewer`.
  - If Copilot is already on the list, print the URL and stop. The PR is ready.
  - Otherwise, go to Step 5 (add-reviewer path).
- If the command fails with "no pull requests found", go to Step 4 (create path).
- If `state` is `MERGED` or `CLOSED`, stop and tell the user: "The existing PR for this branch is `<state>`. Open a new branch before creating another PR."

### Step 4: Create the PR

1. Determine the base branch:
   ```
   gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name'
   ```
2. Generate the title:
   - If `$ARGUMENTS` is non-empty, use it verbatim.
   - Otherwise, use the **subject line of the first commit** on this branch that is not on the base branch (`git log <base>..HEAD --reverse --format=%s | head -1`). This keeps the title in Conventional-Commits style since `CLAUDE.md` mandates that commit format.
3. Generate the body:
   - Summarize the commits: `git log <base>..HEAD --reverse --format='- %s'`.
   - Include a `## Summary` section with those bullets.
   - Include a `## Test plan` section listing the local checks that were run (pytest, mypy, ruff, black, pnpm tsc, etc., whichever apply based on which files changed).
4. Create the PR, requesting Copilot as reviewer in the same call:
   ```
   gh pr create \
     --base <base> \
     --head <current-branch> \
     --title "<title>" \
     --body "$(cat <<'EOF'
   ## Summary
   <bullets>

   ## Test plan
   <checklist>
   EOF
   )" \
     --reviewer Copilot
   ```
5. If `--reviewer Copilot` fails (older `gh` or Copilot code review not enabled), fall through: create the PR without the reviewer flag, capture the PR number, then run Step 5 to add Copilot explicitly. Do not silently skip — tell the user if Copilot cannot be added and why.

### Step 5: Add Copilot to an existing PR (or a just-created one that couldn't receive `--reviewer` inline)

Try the `gh` native path first:

```
gh pr edit <pr-number> --add-reviewer Copilot
```

If that fails (some `gh` versions reject bot reviewers on this endpoint), fall back to the REST API:

```
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  /repos/{owner}/{repo}/pulls/<pr-number>/requested_reviewers \
  -f 'reviewers[]=Copilot'
```

If both fail, print the error verbatim and tell the user:
- Verify "Copilot code review" is enabled for the repo (Settings → Code & automation → Code review).
- Confirm the org has the Copilot Enterprise / Copilot Pro entitlement that includes PR reviews.

Do **not** invent fake success — if Copilot can't be requested, say so.

### Step 6: Report

Print a short summary:

1. PR number and URL.
2. Whether the PR was created new or already existed.
3. Whether Copilot was newly requested, already requested, or failed to be requested (with reason).
4. Next step: `/copilot-review` once Copilot has posted its review (usually within a minute or two), or `/ship` to run the full open-PR → wait → review loop.

## Rules

- **Never force-push.**
- **Never modify files.** This skill is orchestration only.
- **Never hardcode the base branch.** Always read it from `gh repo view`.
- **Never pretend Copilot was added** if the reviewer request failed.
- **Never open a duplicate PR.** If one exists and is open, update it; if merged/closed, stop.
