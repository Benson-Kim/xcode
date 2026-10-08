# Build from the repository root (docker build -f apps/web/Dockerfile .): the workspace lock and @xcode/shared live there.
FROM node:22.23.3-slim AS build
WORKDIR /repo
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_OUTPUT=standalone
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY apps/mobile/package.json apps/mobile/
COPY packages/shared/package.json packages/shared/
# Every workspace manifest is present so the lock is checked in full, but only web and shared are installed.
RUN npm ci --workspace @xcode/web --workspace @xcode/shared
COPY packages/shared packages/shared
COPY apps/web apps/web
RUN npm run build --workspace @xcode/web

FROM node:22.23.3-slim AS runtime
WORKDIR /repo
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
