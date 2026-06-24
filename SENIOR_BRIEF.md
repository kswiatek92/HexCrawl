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

### Read-after-write cache coherence (durable-first write ordering)
When a write touches both a durable store and a cache fronting it, the **durable store goes first, then the cache is refreshed (or invalidated)** — and the refresh isn't optional housekeeping, it's what stops a cache-first read from serving the pre-write copy. Skipping it leaves the two stores divergent until the cache's TTL expires.
**Why it matters:** if reads are cache-first and the cache isn't updated after a write, a follow-up read returns stale data for the whole TTL window — a silent correctness bug, not a perf one. Durable-first ordering also means a crash between the two writes loses only a rebuildable cache refresh, never the authoritative write.
**Code-review tell:** a handler that persists to the DB and returns, but never updates/invalidates the cache it later reads from — especially when there's no `delete` on the cache and eviction is "left to TTL". Also the inverse: cache written before the durable store, so a crash leaves the cache asserting a write that didn't survive.
**Reference:** HexCrawl `AbandonGame` (task 3.8) — Postgres checkpoint *then* `cache.set`, mirroring `ProcessTurn`'s game-over branch; DECISIONS.md ADR-0008.

---

## 2 — Boundaries & Interfaces

### Robustness principle (adapter input tolerance)
"Be conservative in what you send, liberal in what you accept" (Postel's law). At an adapter that wraps a third-party client, accept every shape the client can legitimately return rather than assuming one — but fail loudly on genuinely unexpected input rather than silently mangling it.
**Why it matters:** an adapter that assumes one config of its dependency (e.g. Redis `get()` returning `bytes`) becomes a latent crash the moment someone constructs the client differently (`decode_responses=True` → `str`) — and the assumption silently contradicts any "works regardless of config" contract the adapter advertises.
**Code-review tell:** an unconditional transform on a dependency's return value (`raw.decode(...)`, `resp.json()[0]`) with no type/shape guard, especially when hidden behind a `cast(...)` that suppresses the type checker instead of handling the variance. The "liberal accept" must still end in an explicit `else: raise` — liberal ≠ silent.
**Reference:** RFC 1122 §1.2.2 (Postel's law); the bytes/str fix in `src/adapters/cache/redis_cache.py` (`get`).

### Ports speak domain types; adapters own serialisation
A port (the abstract interface the domain/application depends on) should be typed in **domain terms** — `UUID`, `Score`, a dataclass — never in a transport's wire shape (`str`, `dict`, JSON). Converting to/from the wire format (stringifying a `UUID`, `json.dumps`, pickling) is the **adapter's** job, on the far side of the boundary.
**Why it matters:** keeping the port domain-typed preserves type safety for every caller and stops a transport choice (Celery's JSON serializer, Redis's bytes) from leaking inward — the whole point of hexagonal. Downgrading the port to `str` "because the wire needs a string" pushes serialisation up into the use case and couples the domain to a format it shouldn't know.
**Code-review tell:** a port method typed `str`/`dict`/`bytes` where a domain type would do, justified by "the broker/cache needs it that way." The fix is a domain-typed signature with the conversion living in the adapter — not a relaxed port. A raw `UUID` not being JSON-serialisable is the adapter's problem to solve (`str(score_id)`), not the port's to absorb.
**Reference:** `IScoreRecalcQueue` (`src/domain/ports/score_recalc_queue.py`) keeping `enqueue(score_id: UUID)` while the Celery adapter stringifies; mirrors `IScoreRepository` speaking `Score` not `dict`. Copilot review on PR #60.

### Stateless resource server (verify-only auth boundary)
An API that holds **no session** and never authenticates credentials itself: an external IdP (Supabase/Auth0/Cognito) issues a signed token, and the API only **verifies** it per request (signature + `exp`/`aud`/`iss`) and reads the principal from a claim. authN lives at the *edge* (who are you? → 401 on a bad token); authZ lives next to the *resource* (is this yours? → 403). The two are separate decisions in separate places.
**Why it matters:** no credential ever touches your server, so a compromise can't leak passwords or refresh tokens; and with identity in a verifiable token (not server memory) any instance can serve any request — horizontal scaling is free (twelve-factor "stateless processes"). Adding a "convenience" login/proxy route quietly throws both away — the server becomes a credential-interception point.
**Code-review tell:** a backend `/login` or `/register` that forwards a password to the IdP, stores a refresh token, or holds a server-side session — when the frontend SDK could talk to the IdP directly. Also: an ownership check returning 401 (should be 403) or a bad-token check returning 403 (should be 401) — a sign authN and authZ have been conflated.
**Reference:** DECISIONS.md ADR-0007 (no backend auth route); `src/entrypoints/http/auth.py` `get_current_user` (verify-only, task 2.10); `docs/auth-setup.md`.

### 403 vs 404 as an information-leak trade-off
Returning **403 Forbidden** for a resource that exists but isn't yours *confirms it exists* to a non-owner; returning **404 Not Found** for both "doesn't exist" and "not yours" leaks nothing about which ids are valid. The choice is a deliberate honesty-vs-confidentiality trade-off, not a default — distinct from 401-vs-403 (which is authN-vs-authZ).
**Why it matters:** 403 on enumerable/guessable ids (sequential ints, emails, usernames) hands an attacker an *existence oracle* — they map which records exist without ever having access. 404-for-both closes that oracle at the cost of muddier semantics (a genuine permission error is indistinguishable from a typo). Rule of thumb: 403 is safe when ids are unguessable (UUIDv4) and existence is low-value; prefer 404-for-both when ids are enumerable or the existence fact is itself sensitive.
**Code-review tell:** an ownership check returning 403 on a resource keyed by a sequential/guessable id, or any endpoint where "exists but forbidden" and "doesn't exist" are externally distinguishable on enumerable ids. The choice deserves a one-line comment recording *why*, since it's non-obvious and security-relevant.
**Reference:** HexCrawl `GET /game/{id}` (task 3.7) → 403 for a foreign run, justified because dungeon ids are UUIDv4 (unguessable); `src/application/get_game.py` `NotGameOwnerError`. OWASP API3:2023 (Broken Object Level Authorization).

---

## 3 — Testing

### Bounded timeouts on connection-failure tests
A test that asserts "the dependency is down → we raise" must build its client with an explicit, short `connect`/read timeout. Otherwise the failure path is at the mercy of the OS-level connect timeout, which can be seconds-to-minutes — and varies by how the endpoint refuses (RST = instant; firewall DROP = full timeout).
**Why it matters:** a "negative" test with no timeout is silently non-deterministic — fast when the port refuses, a multi-second hang (or CI flake/timeout) when it doesn't. The assertion is correct but the *latency* is unbounded.
**Code-review tell:** a test connecting to an unreachable host/port (`127.0.0.1:1`, `10.255.255.1`, a stopped container) with default client construction and no `socket_connect_timeout`/`socket_timeout` (or equivalent). Pick a timeout generous enough not to false-fail, short enough to bound the run.
**Reference:** the dead-Redis fix in `tests/integration/adapters/cache/test_redis_cache.py` (`test_failure_propagates_not_swallowed`); Copilot review on PR #51.

---

## Vocabulary cheat-sheet (one line each)

- **N+1 query problem** — 1 query for N parents + 1 per parent on lazy relationship access = N+1; fix with eager loading.
- **Eager-loading strategies** — selectin (`IN` query; default for collections) vs joined (one JOIN, duplicates parents, breaks LIMIT) vs subquery.
- **Identity Map / Unit of Work** — session caches one object per PK; tracks mutations and flushes them as one ordered batch on commit.
- **Normalisation vs JSONB blob** — tables/FKs = queryable + integrity; JSONB = read-as-blob simplicity but SQL-opaque, no FK/schema.
- **Read-after-write cache coherence** — write durable store first, then refresh/invalidate the cache; skipping the refresh serves stale data on cache-first reads until TTL. Durable-first ordering means a mid-write crash loses only a rebuildable cache refresh.
- **Robustness principle (adapter input tolerance)** — accept every shape a wrapped client can return (bytes *and* str), but end the liberal-accept in an explicit `else: raise`, never a silent `cast`.
- **Ports speak domain types; adapters own serialisation** — type a port in domain terms (`UUID`, `Score`), never the wire shape (`str`/`dict`); stringifying/`json.dumps` belongs in the adapter, not a relaxed port signature.
- **Stateless resource server (verify-only auth)** — API holds no session and never sees credentials; IdP issues a signed token, API only verifies it (401 at the edge) and checks ownership by resource (403). No password leak surface, free horizontal scaling.
- **403 vs 404 info-leak trade-off** — 403 "exists but not yours" confirms existence; 404-for-both hides it. Safe to use 403 with unguessable (UUIDv4) ids; prefer 404-for-both when ids are enumerable or existence is sensitive.
- **Bounded timeouts on connection-failure tests** — a "dependency is down → we raise" test must set a short connect/read timeout, or its latency is at the mercy of the OS connect timeout (RST = instant, DROP = hang/flake).

---

## Reading list (durable, picked up from quizzes)

- ***SQL Performance Explained*** — Markus Winand. Indexing, query plans, the N+1/execution-plan gap. Free companion: use-the-index-luke.com. _(Task 2.3 Q2)_
- ***Architecture Patterns with Python*** — Percival & Gregory. Hexagonal, Repository, Unit of Work in Python/Flask/SQLAlchemy. Free: cosmicpython.com. _(Task 2.3 Q1/Q3/Q4)_
- ***Patterns of Enterprise Application Architecture*** — Martin Fowler. Defines Identity Map, Unit of Work, Data Mapper, Repository. Reference, not cover-to-cover. _(Task 2.3 Q4)_
- ***The Art of PostgreSQL*** — Dimitri Fontaine. Postgres-specific: JSONB, window functions, lateral joins. _(Task 2.3 Q5)_
- [SQLAlchemy — Relationship Loading Techniques](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html) — selectin/joined/subquery query shapes. _(Task 2.3 Q3 — no book covers loader internals)_
