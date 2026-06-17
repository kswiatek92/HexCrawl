# Supabase Storage setup (task 2.11)

How to provision the Supabase Storage buckets HexCrawl uses, and the contract the backend
follows when it reads and writes them. Like `docs/auth-setup.md`, this is a **runbook** —
the bucket-creation steps are performed once, by hand, in the Supabase dashboard; the repo
only carries the configuration (the bucket names, in `src/config.py`) the backend needs.

## Where storage lives in the architecture

Supabase Storage is S3-compatible **object storage**. HexCrawl uses it for blobs that don't
belong in Postgres:

| Bucket    | Privacy         | Holds                      | Object path *within the bucket* |
|-----------|-----------------|----------------------------|---------------------------------|
| `saves`   | **private**     | Save-file snapshots (JSON) | `{user_id}/{game_id}.json`      |
| `avatars` | **public-read** | Player profile images      | `{user_id}.png`                 |

Note the bucket name and the object path are **separate arguments** to the Storage API
(`from_("saves").create_signed_url("{user_id}/{game_id}.json", …)`) — the path does **not**
repeat the bucket. Writing `saves/{user_id}/…` as the path would create a doubly-nested
`saves/saves/…` object.

The backend is the only writer. For private `saves`, clients never touch the bucket
directly with a long-lived credential — the backend either streams through a privileged
call **or** (preferred) hands the client a short-lived **pre-signed URL** (see below).

### Why object storage, not a Postgres `BYTEA` column

A save snapshot is a large opaque blob read/written wholesale. Putting it in a `BYTEA`
column would:

- **Bloat the table** and every backup/restore — the blob rides along with relational data
  it has nothing to do with, inflating `pg_dump` size and slowing restores.
- **Pollute the buffer cache** — large rows evict hot index/relational pages, hurting the
  queries that actually need Postgres.
- Push large payloads through TOAST and the connection pool, competing with real queries.

Object storage offloads all of that to infrastructure built for blobs. **What you give up:**
**transactional consistency** — the object write and the owning DB row commit are two
separate operations. There's no single transaction spanning both, so the app must tolerate
(and reconcile) a row that points at a not-yet/never-written object, or an orphaned object
whose row write rolled back. We accept that trade for save files: a missing/stale snapshot is
recoverable (re-save), and the blob is not relational data.

## One-time console steps

1. In the same Supabase project from `docs/auth-setup.md` (Auth + Storage only; game
   Postgres + Redis stay local in `docker-compose`), open **Storage**.
2. **Create bucket `saves`** — leave **"Public bucket" OFF** (private). This is the default
   and the important one: a save file is per-user data and must never be world-readable.
3. **Create bucket `avatars`** — turn **"Public bucket" ON** (public-read). Profile images are
   displayed in the browser on every leaderboard row; a public bucket lets the `<img>` tag
   load them directly from a stable CDN-cacheable URL with no per-request signing. Avatars are
   non-sensitive and chosen by the user, so public read is acceptable. (Writes are still
   backend-only.)
4. (Optional, later) Add **lifecycle / retention** rules on `saves` once weekly-reset
   archival lands (QUESTIONS.md task 4.4) — e.g. expire abandoned-run snapshots.

The bucket names map to `SUPABASE_STORAGE_SAVES_BUCKET` / `SUPABASE_STORAGE_AVATARS_BUCKET`
in `.env` (defaults `saves` / `avatars`; see `src/config.py`). Override only if your project
names them differently.

## Private saves: pre-signed URLs

The `saves` bucket is private, but a client still needs to read/write its own snapshot. Two
options:

1. **Stream the bytes through FastAPI** — the request hits the API, the API fetches from
   Storage and pipes the body back (or buffers an upload and forwards it).
2. **Hand out a pre-signed URL** *(preferred)* — the API makes one privileged call to mint a
   URL that grants **time-bounded** access (read or write) to **one object key**, then returns
   that URL. The client transfers bytes **directly to/from Supabase Storage**.

A **pre-signed URL** is a normal URL with a signed, expiring token in its query string. The
signature proves "the backend authorised access to *this key* until *this time*" — so the
bucket stays private (no public access) while a specific client gets a narrow, expiring grant.
After expiry the URL is dead.

Prefer pre-signed URLs because they:

- **Offload bandwidth** — large blob transfers go client ↔ Storage, not through the API's
  network path, so the API isn't a throughput bottleneck.
- **Keep the event loop free** — a multi-megabyte transfer streaming through an async worker
  ties up that task; the API instead does one tiny "mint URL" call and returns. No long
  transfer blocking the loop.

## The authorisation rule (do not skip)

Within the `saves` bucket, the object-path layout `{user_id}/{game_id}.json` gives us, for free:

- **Listing / per-user scoping** — `from_("saves").list("{user_id}/")` returns just that user's saves.
- **Lifecycle rules** — retention/cleanup can target a path prefix.
- **Debuggability** — a path tells you whose save it is at a glance.

But the path prefix is **not an authorisation boundary**. Nothing stops a caller from *asking*
for another user's object path (`{someone-elses-id}/{game_id}.json`) in the same bucket. So
**before** minting any pre-signed URL or streaming any object, the backend **must verify
ownership server-side**: the `sub` from the verified JWT (`get_current_user`, task 2.10) must
match the `{user_id}` segment of the requested path (and, for game-scoped reads, that
`{game_id}` belongs to that user). AuthN happens at the edge;
**authZ happens next to the resource** — same split as the auth runbook. Trusting the key
prefix alone would be an IDOR (insecure direct object reference).

## Security notes

- The `service_role` key bypasses RLS and Storage policies entirely — it is what makes
  privileged "mint a pre-signed URL for any key" calls possible. Keep it backend-only; never
  ship it to the browser or commit it (see `docs/auth-setup.md`).
- A **public bucket is world-readable** — anyone with the URL can fetch the object, and the URL
  is guessable from the key. Only put non-sensitive, user-chosen content (avatars) there. Save
  files never go in a public bucket.
- Pre-signed URLs leak access if shared before they expire — keep their TTL short (minutes, not
  days) and mint them per-request.
