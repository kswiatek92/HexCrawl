You are running the HexCrawl quiz system against the **current task** — the task the user is actively working on or has just finished. Source of truth for tasks is `BOARD.md`; source of truth for questions is `QUIZZES.md`. Never invent questions.

## Phase 1: Identify the current task

1. Read `BOARD.md` and scan the task tables for rows marked `🔄 in progress` or `✅ done` where the quiz column is still `⬜` or `🔁`.
2. Selection rules, in order:
   - If the user passed an explicit target (e.g. `/quiz 1.3`, `/quiz phase 1`, `/quiz summary 2`), use it verbatim. Task IDs look like `1.3`; phase quizzes are referred to as "Phase N quiz" or "summary quiz".
   - Else: exactly one row is `🔄 in progress` → that is the current task.
   - Else: the most recently transitioned `✅ done` row whose quiz is still `⬜` / `🔁` → that is the current task.
   - Else: there are multiple candidates → list them and ask the user to pick. Do not guess.
   - Else: there is no task in scope → tell the user and stop.
3. Confirm the selection in one sentence (e.g. "Quizzing you on Task 1.3 — `Enemy` dataclass + `BehaviourType` enum.") before asking any questions.

## Phase 2: Load the questions

1. Open `QUIZZES.md` and locate the matching section.
   - Task quiz: `### Task <id> — <title>` — 5 questions, pass = 5/5.
   - Phase summary quiz: `## Phase <n> — Summary quiz` — 10 questions, pass = 9/10.
2. If the heading text in `QUIZZES.md` does not match the task title in `BOARD.md`, stop and report the mismatch — do not paraphrase.
3. Copy the exact question text. Never rephrase or shorten a question before asking it.

## Phase 3: Run the quiz

Ask **one question at a time**. Do not batch. For each question:

1. Present it verbatim as `Q<n>/<total>: <question>`.
2. Wait for the user's answer. Do not answer for them, do not hint before they reply.
3. Grade the answer against what `CLAUDE.md` and `QUIZZES.md` imply is correct. Output one of:
   - `✅ Correct` — core idea is right; minor omissions are fine.
   - `🟡 Partial` — on the right track but missing a key point. Say explicitly what's missing. Counts as **incorrect** for the pass/fail tally (the thresholds in `BOARD.md` → "Quiz system" demand 90% correctness, not "mostly there").
   - `❌ Incorrect` — wrong or contradicts project conventions. Say what's wrong and cite the relevant `CLAUDE.md` section or quiz question.
4. After grading, give a one-to-three-sentence model answer so the user learns even when they fail. Keep it tight — this is feedback, not a lecture.
5. Move to the next question.

Grading rules:
- A correct answer must be consistent with `CLAUDE.md` (hexagonal rules, code conventions, stack choices). Any answer that violates a `CLAUDE.md` rule is at best 🟡 and usually ❌, even if technically workable in some other project.
- For questions about specific code in this repo, verify against the actual files when necessary — don't guess.
- Do not mark 🟡 / ❌ without pointing to *what* is missing or wrong. "Incomplete" alone is not feedback.

## Phase 4: Final profile assessment

After the final question, produce a report in this shape:

```
# Quiz result — <task id / phase> — <pass|fail>

Score: <correct>/<total>  (threshold: <5/5 or 9/10>)

## Strong areas
- <topic> — <one-line reason, referencing specific Q numbers>

## Weak spots
- <topic> — <one-line reason + Q numbers that revealed it>

## Things to revisit
- <concrete action: "re-read CLAUDE.md → Code conventions for match statements">
- <concrete action: "re-read QUIZZES.md Task <id> Q<n> model answer">

## Verdict
<one paragraph — pass or fail, and why; if fail, explicitly list which questions were missed>
```

The report must:
- Tally 🟡 and ❌ as incorrect. Pass requires ≥ 90% correct per the threshold in `BOARD.md` → "Quiz system".
- Name concrete sections of `CLAUDE.md` or `QUIZZES.md` to revisit — never say "study this topic more" without a pointer.
- Be honest. Do not inflate the score out of politeness.

## Phase 5: Update `BOARD.md`

Edit the quiz cell for the task row in `BOARD.md`:
- Pass → `🏆`
- Fail → `🔁`
- Leave the task status column (🔲 / 🔄 / ✅ / 🚫) alone — quiz state is separate.

Do not touch any other cell or any other file. Show the user the single-line diff of the table row you changed.

If the user explicitly says "don't update the board", skip Phase 5 and say so.

## Rules

- **Never skip a question** unless the user asks. If they skip, mark it ❌ and continue.
- **Never reveal answers ahead of time.** Only reveal the model answer after the user has submitted theirs.
- **Never invent questions** that are not in `QUIZZES.md`. If the user asks for more questions on a topic, point them at the adjacent tasks in `QUIZZES.md`.
- **Never grade based on memory of this repo** — if you're unsure whether an answer matches the code, open the file and check.
- **One question at a time.** Do not paste the whole quiz and ask the user to answer in bulk.
- **Do not modify `QUIZZES.md` or `CLAUDE.md`.** This skill is board-scoped only.
