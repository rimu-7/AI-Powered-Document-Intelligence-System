# DocIntel AI — frontend

Next.js 16 web app for DocIntel AI: the UI and a Backend-for-Frontend (`/bff`)
that keeps the session in httpOnly cookies and forwards requests to the API.
Architecture and conventions: [docs/frontend.md](../docs/frontend.md). System
setup: [root README](../README.md).

## Working on the frontend

Requirements: Node.js 24+ and pnpm (the version is pinned in `package.json`;
`corepack enable` picks it up).

```bash
pnpm install --frozen-lockfile
cp .env.example .env.local      # API_INTERNAL_URL, APP_ORIGIN, COOKIE_SECURE
pnpm run dev                    # http://localhost:3000, needs the API on API_INTERNAL_URL
```

The API comes from the root stack (`make up` or `make dev`). Stop the `web`
container first (`docker compose stop web`) so port 3000 is free.

| Command | Purpose |
|---|---|
| `pnpm run lint` · `pnpm run format:check` · `pnpm run typecheck` | ESLint, Prettier, TypeScript (route types generated first) |
| `pnpm run test` | Vitest unit and component tests (API mocked with MSW) |
| `pnpm run test:e2e` | Playwright + axe against `PLAYWRIGHT_BASE_URL` (default `http://localhost:3000`) |
| `pnpm run build` | production build (standalone server, as in the Docker image) |
| `make api-types` (at the root) | regenerate `lib/api/schema.d.ts` from the backend's OpenAPI schema |

`lib/api/schema.d.ts` is generated: never edit it by hand. This project uses a
Next.js version with breaking changes from older releases; read
`node_modules/next/dist/docs/` before using an unfamiliar API (see
[`AGENTS.md`](AGENTS.md)).
