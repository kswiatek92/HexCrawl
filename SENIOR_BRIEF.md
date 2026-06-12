# Senior Brief

Personal study aid. Concepts surfaced as gaps by quiz fails or learnings worth keeping from review/coaching sessions. Updated incrementally; not project documentation.

> **Maintenance rules:**
>
> - **Source of additions**: a quiz fail/partial, a coaching session, or manual ("save this to the brief").
> - **Entry shape**: section heading → 1–2 sentence definition → "Why it matters" line → "Code-review tell" line → reference (optional). Cap each concept at ~5–7 lines so the file stays scannable.
> - **Cheat-sheet line**: every concept added above should also land as a one-line entry in the vocabulary cheat-sheet near the bottom.
> - **Insertion order**: append concepts under the closest existing section family; create a new numbered section if no family fits.
> - **Soft cap**: if the file exceeds ~250 lines, prune low-traffic entries (concepts that haven't come up again in subsequent quizzes/reviews) rather than letting it bloat into a textbook.

---

## 1 — Persistence & ORM

### N+1 query problem
One query loads a **parent** collection (N rows); then accessing a lazily-loaded relationship on each parent fires **one more query per parent** → N+1 total, growing linearly with parent count. It's "per parent loaded," not "per row in the DB."
**Why it matters:** a silent performance cliff — invisible with 10 rows in dev, melts the DB at 10k in prod.
**Code-review tell:** a loop over ORM objects that touches a relationship attribute (`for f in dungeon.floors: f.enemies`) with default lazy loading and no eager-load hint.
**Reference:** *SQL Performance Explained* (Winand); SQLAlchemy relationship-loading docs.

### Eager-loading strategies: selectin vs joined vs subquery
How to pre-load a relationship in one shot. **joined** = single `LEFT JOIN` — duplicates the parent row once per child (row multiplication) and breaks `LIMIT`. **subquery** = a 2nd query re-running the original as a subquery. **selectin** = a 2nd query `... WHERE parent_id IN (:ids)` using the already-loaded PKs — no JOIN, no blow-up.
**Why it matters:** the fix for N+1 — but the *wrong* strategy (`joined` on a one-to-many) trades N+1 for row multiplication.
**Code-review tell:** a collection (`list[...]`) relationship using `lazy="joined"`, or a hot path with no loader strategy at all. Collections should default to `selectin`.
**Reference:** SQLAlchemy *Relationship Loading Techniques* docs.

### Identity Map & Unit of Work
**Identity Map** = a per-`Session` cache keyed by `(class, primary key)`, so one DB row maps to exactly one in-memory object (`a is b` for the same PK). **Unit of Work** = the session tracks every change to those objects and, on `flush`/`commit`, emits the needed INSERT/UPDATE/DELETE as one correctly-ordered batch.
**Why it matters:** you mutate objects and let the session generate the SQL — no divergent copies of a row, writes ordered/batched for you.
**Code-review tell:** code hand-writing an UPDATE (or re-fetching) for an object already loaded in the session, or assuming two loads of the same PK give distinct objects.
**Reference:** *Patterns of Enterprise Application Architecture* (Fowler); *Architecture Patterns with Python* (UoW chapter).

### Normalisation vs JSONB-blob modelling trade-off
**Normalised** (separate tables/columns + FKs) buys queryability, indexing, and referential integrity at the cost of joins. A **blob** (JSONB/document) buys read-as-a-whole simplicity but is opaque to SQL — you can't filter/index inner fields without JSON operators, and there's no FK or schema enforcement.
**Why it matters:** the core schema decision for nested/aggregate data; picking wrong means a join-heavy schema for blob-like data, or an unqueryable blob for data you need to query.
**Code-review tell:** a JSONB column you keep reaching into (`WHERE data->>'x' = ...` everywhere → should be a column), or a many-row child table for data only ever read as one unit (→ should be a blob).
**Reference:** checklist §4 Databases → "Modeling"; *The Art of PostgreSQL* (JSONB).

---

## Vocabulary cheat-sheet (one line each)

- **N+1 query problem** — 1 query for N parents + 1 per parent on lazy relationship access = N+1; fix with eager loading.
- **Eager-loading strategies** — selectin (`IN` query; default for collections) vs joined (one JOIN, duplicates parents, breaks LIMIT) vs subquery.
- **Identity Map / Unit of Work** — session caches one object per PK; tracks mutations and flushes them as one ordered batch on commit.
- **Normalisation vs JSONB blob** — tables/FKs = queryable + integrity; JSONB = read-as-blob simplicity but SQL-opaque, no FK/schema.

---

## Reading list (durable, picked up from quizzes)

- ***SQL Performance Explained*** — Markus Winand. Indexing, query plans, the N+1/execution-plan gap. Free companion: use-the-index-luke.com. _(Task 2.3 Q2)_
- ***Architecture Patterns with Python*** — Percival & Gregory. Hexagonal, Repository, Unit of Work in Python/Flask/SQLAlchemy. Free: cosmicpython.com. _(Task 2.3 Q1/Q3/Q4)_
- ***Patterns of Enterprise Application Architecture*** — Martin Fowler. Defines Identity Map, Unit of Work, Data Mapper, Repository. Reference, not cover-to-cover. _(Task 2.3 Q4)_
- ***The Art of PostgreSQL*** — Dimitri Fontaine. Postgres-specific: JSONB, window functions, lateral joins. _(Task 2.3 Q5)_
- [SQLAlchemy — Relationship Loading Techniques](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html) — selectin/joined/subquery query shapes. _(Task 2.3 Q3 — no book covers loader internals)_
