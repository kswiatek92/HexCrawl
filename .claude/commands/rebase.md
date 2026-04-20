You rebase the current branch onto the latest `main`, resolve conflicts, and push. This handles the common case where the current branch was created from another feature branch that has since been squash-merged into `main`.

**Argument:** $ARGUMENTS (optional: the name of the parent branch that was squash-merged, to help identify which conflicts come from duplicate commits)

## Deliverables

- The current branch rebased onto the latest `origin/main`.
- All conflicts resolved.
- The updated branch force-pushed to remote with `--force-with-lease`.

## Scope Boundaries

**You MUST NOT:**
- Modify any source code beyond what is required to resolve merge conflicts.
- Create new branches, commits unrelated to the rebase, or board changes.
- Drop, reorder, or squash commits during the rebase (empty-after-replay commits may be skipped — that's different).
- Push with plain `--force`. Always `--force-with-lease`.

**You MUST:**
- Preserve all of the current branch's unique work (commits not from the squash-merged parent).
- Verify the branch still builds / typechecks after rebase when cheap to do so.

## Workflow

### Step 1: Assess current state

```
git status
git branch --show-current
git log --oneline -20
```

Confirm:
- Working tree is clean (no uncommitted changes). If dirty, **stop and ask the user to commit or stash**.
- You are NOT on `main`. If on `main`, **stop and tell the user to check out their feature branch**.

Record the current branch name and its commit history.

### Step 2: Fetch latest main

```
git fetch origin main
```

### Step 3: Identify the rebase boundary

This is the critical step for the squash-merge scenario.

1. Find the merge-base between the current branch and `origin/main`:
   ```
   git merge-base HEAD origin/main
   ```
2. Count how many commits are on the current branch above the merge-base:
   ```
   git log --oneline <merge-base>..HEAD
   ```
3. If `$ARGUMENTS` was provided (parent branch name), check whether that branch's squash commit exists on `main`:
   ```
   git log --oneline origin/main | head -20
   ```
   This helps confirm the parent was indeed squash-merged and identify which of the current branch's commits are duplicates.

### Step 4: Rebase onto main

```
git rebase origin/main
```

### Step 5: Resolve conflicts

If the rebase stops due to conflicts:

1. **Identify conflict type.** For each conflicting file, determine whether the conflict comes from:
   - **Duplicate changes** (changes from the squash-merged parent branch that now exist on `main` as a single squash commit). Most common in this workflow.
   - **Genuine conflicts** (the current branch's own changes conflict with unrelated `main` changes).

2. **For duplicate-change conflicts:** the content on `main` (the squash-merged version) is authoritative for the parent branch's work. Accept the `main` version for those hunks, then ensure the current branch's own modifications on top are preserved. In practice:
   - Read the conflicting file to understand both sides.
   - If the current commit being replayed is entirely from the parent branch (a duplicate), the resolution is usually to accept `main`'s version entirely: `git checkout --theirs <file> && git add <file>`.
   - If the current commit mixes parent-branch and own changes, manually edit to keep `main`'s base + the branch's unique additions.

3. **For genuine conflicts:** resolve by understanding both sides — read surrounding code, check the intent of each change, and merge them correctly.

4. **HexCrawl-specific conflict gotchas** — check these before marking a resolution complete:
   - **Alembic migration heads**: if `alembic/versions/` has conflicting heads, do NOT just keep both files. Re-parent the branch's migration to point its `down_revision` at the current head on `main`. If unsure, run `alembic heads` and stop for the user.
   - **`requirements/*.txt`**: never keep both versions of a dependency line. Take the higher pinned version from `main` and merge the branch's additions — then note the change so the user can reinstall.
   - **`BOARD.md`**: never auto-resolve conflicts here. The status/quiz cells encode state — always show both sides to the user and ask which to keep.
   - **`CLAUDE.md`**: same as above — conventions live here; resolve by hand or ask.
   - **Frontend `package.json` / lockfile**: keep `main`'s lockfile, reapply the branch's `package.json` additions, then the user must re-run the package manager locally.

5. After resolving all conflicts in a step:
   ```
   git add <resolved-files>
   git rebase --continue
   ```

6. If a commit becomes empty after resolution (all its changes were already on `main` via squash):
   ```
   git rebase --skip
   ```

7. Repeat until the rebase completes.

### Step 6: Verify

After the rebase completes:

1. Check the commit log looks correct:
   ```
   git log --oneline origin/main..HEAD
   ```
   The remaining commits should be only the current branch's unique work.

2. Quick sanity checks — only run what's cheap:
   - If any `src/` Python was touched: `pytest tests/unit -x -q` (fast tier, < a few seconds per `CLAUDE.md`).
   - If typed Python changed: `mypy src` on the affected packages (or the whole tree if configured).
   - If `alembic/` was touched: `alembic heads` should report a single head.
   - If the frontend was touched and the repo has `pnpm`: `pnpm tsc --noEmit` on the frontend workspace.
   - Otherwise: review `git diff origin/main --stat` to confirm the changes look right.

   Do not run slow integration / e2e suites here — that's the CI's job.

### Step 7: Push

```
git push --force-with-lease
```

If this fails because the remote has diverged, **stop and tell the user** — do not escalate to `--force`.

### Step 8: Summary

Report:
1. Branch name.
2. Number of commits before and after the rebase.
3. Number of conflicts resolved (and how — which were duplicates vs genuine).
4. Whether any commits were skipped (empty after resolution).
5. Which quick checks you ran and their results.
6. Push result.

## Important Rules

- **Never use `git push --force`** — always `--force-with-lease`.
- **If the rebase gets too tangled** (e.g. 10+ conflicting commits with complex manual merges), abort with `git rebase --abort` and tell the user. Suggest an alternative: interactive rebase to drop the parent's commits first, or a fresh branch with cherry-picks.
- **If you are unsure about a conflict resolution**, stop the rebase and show the conflict to the user for guidance. Do not guess.
- **Working tree must be clean before starting.** No stashing on the user's behalf.
- **Do not touch `BOARD.md`, `CLAUDE.md`, `QUIZZES.md`, or `QUESTIONS.md` state as part of conflict resolution** without explicit user input — those files encode project state, not just code.
