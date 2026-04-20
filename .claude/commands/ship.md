You run the full "ready for review" loop for the current branch: open a PR with Copilot as a reviewer (if there isn't one already), wait for Copilot to post its review, then run the `/copilot-review` fix-and-push-and-CI loop until CI is green or the cycle budget is exhausted. This skill chains `/open-pr` and `/copilot-review`.

**Argument:** $ARGUMENTS (optional one-line PR title override; forwarded to `/open-pr`)

## Deliverables

- A pull request on GitHub with Copilot as a reviewer.
- Copilot's review comments triaged, valid suggestions applied, a new commit pushed (if any fixes were made).
- Green CI on the PR, or — if CI still fails after the `/copilot-review` cycle budget — a clear hand-off message to the user.

## Scope Boundaries

**You MUST NOT:**
- Duplicate the logic from `/open-pr` or `/copilot-review` — this skill orchestrates; each phase defers to its underlying skill file.
- Apply fixes without user confirmation (the approval gate belongs to `/copilot-review` Phase 2 step 4 — respect it).
- Close or merge the PR. Merging is a human decision.
- Force-push.

**You MUST:**
- Run the phases strictly in order; do not start Phase 3 until Phase 2 produces at least one Copilot comment (or the timeout fires).
- Pass through `$ARGUMENTS` to `/open-pr` unchanged.
- Stop immediately if a phase returns an error state that can't be remediated automatically (e.g. dirty working tree, no PR could be created, Copilot code review not enabled on the repo).

## Workflow

### Phase 1: Open (or find) the PR — delegate to `/open-pr`

Execute the steps in `.claude/commands/open-pr.md` verbatim, with `$ARGUMENTS` forwarded. When that flow finishes you will have:

- A PR number and URL for the current branch.
- Copilot on the reviewer list (or an explicit error from `/open-pr` — in which case stop here and surface it).

If `/open-pr` stopped early (dirty tree, closed PR, refusing to push from `main`), this skill stops with the same message. Do not try to work around it.

### Phase 2: Wait for Copilot's review

Copilot's code review usually lands within 30–120 seconds, but there's no SLA. Poll:

```
gh api repos/{owner}/{repo}/pulls/<pr-number>/reviews --paginate \
  --jq '[.[] | select(.user.login | test("copilot"; "i"))] | length'

gh api repos/{owner}/{repo}/pulls/<pr-number>/comments --paginate \
  --jq '[.[] | select(.user.login | test("copilot"; "i"))] | length'
```

Sum the two counts. The poll strategy:

- Poll every **30 seconds** for up to **5 minutes** (10 iterations).
- Stop polling as soon as the sum is `> 0` — Copilot has posted something.
- If the 5-minute budget expires with zero Copilot activity:
  - Report the PR URL and tell the user: "Copilot hasn't posted a review within 5 minutes. Possible causes: (1) Copilot code review is not enabled for this repo, (2) the org's Copilot entitlement doesn't include PR reviews, (3) the service is temporarily backed up. Re-run `/copilot-review` manually once the review lands, or `/ship` again."
  - Do **not** proceed to Phase 3.

Run the poll with Bash's `run_in_background` if available so the main conversation isn't blocked — otherwise poll in-foreground but keep updates concise (a single sentence per iteration, not a log dump).

### Phase 3: Run `/copilot-review`

Once Copilot has posted at least one review item, execute the flow in `.claude/commands/copilot-review.md` verbatim. That skill handles:

- Fetching inline comments + top-level review bodies.
- Evaluating each against `CLAUDE.md` (including the hexagonal guards).
- Asking the user for confirmation before applying changes.
- Committing + pushing approved fixes.
- Polling CI and diagnosing failures (up to 3 fix cycles).

This skill **does not** override any of those steps — it just hands control to `/copilot-review`.

### Phase 4: Final report

After `/copilot-review` returns, summarise in one short paragraph:

1. PR URL and number.
2. Whether new commits were pushed during the review cycle (and how many).
3. Final CI status (green / still failing / waiting).
4. What the user should do next — typically: review the diff on GitHub and merge, or address whatever `/copilot-review` flagged as unresolved.

## Rules

- **Never duplicate `/open-pr` or `/copilot-review` logic.** Defer to the skill files.
- **Never skip Phase 2** even if Copilot has reviewed past PRs quickly — there's no guarantee on timing.
- **Never merge the PR.** That's the user's call.
- **Never force-push.** Inherited from both upstream skills.
- **Respect `/copilot-review`'s approval gate.** The user must confirm each fix; do not pre-approve on their behalf.
- **Stop on unrecoverable errors.** Dirty tree, missing PR capability, disabled Copilot — report and halt.
