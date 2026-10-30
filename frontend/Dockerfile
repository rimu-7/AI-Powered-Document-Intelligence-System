# syntax=docker/dockerfile:1.7
# Web app: Next.js UI + BFF (route handlers under /bff that hold the session
# cookies and call the API server-side). Stages: deps → test | build → runtime.

ARG NODE_IMAGE=node:24.22.2-alpine3.24@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85

# --- deps: install exactly what the lockfile pins ----------------------------------
FROM ${NODE_IMAGE} AS deps
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH NEXT_TELEMETRY_DISABLED=1 COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /app
# package.json pins pnpm (packageManager); pnpm-workspace.yaml holds the build-script allow-list.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store pnpm install --frozen-lockfile

# --- test: lint, type-check and unit/component tests (CI and `make test-docker`) ---
FROM deps AS test
COPY . .
CMD ["sh", "-c", "pnpm run lint && pnpm run typecheck && pnpm run format:check && pnpm run test"]

# --- build: standalone server bundle ------------------------------------------------
FROM deps AS build
COPY . .
RUN pnpm run build

# --- runtime: only the standalone output, as an unprivileged user -------------------
FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S -g 10001 docintel && adduser -S -u 10001 -G docintel -h /app docintel
COPY --from=build --chown=docintel:docintel /app/public ./public
COPY --from=build --chown=docintel:docintel /app/.next/standalone ./
COPY --from=build --chown=docintel:docintel /app/.next/static ./.next/static
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1:3000/bff/health || exit 1
CMD ["node", "server.js"]
