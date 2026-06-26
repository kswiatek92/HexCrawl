# HexCrawl frontend

React + Vite (TypeScript) client for HexCrawl. The backend is the portfolio
centrepiece — this app stays deliberately focused.

## Stack

| Concern     | Choice                           |
| ----------- | -------------------------------- |
| Build / dev | Vite + `@vitejs/plugin-react`    |
| Language    | TypeScript                       |
| State       | Zustand                          |
| Styling     | Tailwind CSS v4 (Vite plugin)    |
| Routing     | React Router                     |
| Tests       | Vitest + Testing Library (jsdom) |

State / styling / routing choices are recorded in the repo-root `QUESTIONS.md`
(Phase 5, task 5.1).

## Prerequisites

- Node 20+ (CI uses Node 20)
- pnpm 9 (`corepack use pnpm@9` or `corepack pnpm@9 …`)

## Commands

```bash
pnpm install            # install deps (CI uses --frozen-lockfile)
pnpm dev                # start Vite dev server (http://localhost:5173)
pnpm build              # production build
pnpm preview            # preview the production build
pnpm lint               # ESLint
pnpm exec prettier --check .   # formatting check
pnpm tsc --noEmit       # type check
pnpm test -- --run      # run tests once
pnpm test -- --coverage --run  # tests with coverage (CI)
```

## Dev proxy

`vite.config.ts` proxies `/api` and `/ws` to the backend (default
`http://localhost:8000`, overridable via `VITE_API_PROXY_TARGET` — see
`.env.example`). This keeps the browser on a single origin in development, which
sidesteps CORS preflights and cross-site cookie restrictions. Start the backend
with `uv run uvicorn src.entrypoints.http.main:app --reload` from the repo root.
