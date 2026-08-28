# Airlock reviewer console. Standalone Next.js output on node:22-alpine.
# syntax=docker/dockerfile:1

FROM node:22-alpine AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /app
RUN corepack enable
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=8080
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 airlock \
 && adduser --system --uid 1001 --ingroup airlock airlock

COPY --from=builder --chown=airlock:airlock /app/.next/standalone ./
COPY --from=builder --chown=airlock:airlock /app/.next/static ./.next/static
COPY --from=builder --chown=airlock:airlock /app/public ./public

USER airlock
EXPOSE 8080

# server.js reads PORT and HOSTNAME, which is what Cloud Run sets.
CMD ["node", "server.js"]
