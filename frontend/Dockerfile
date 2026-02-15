# frontend/Dockerfile (Optimized for Windows & CI)

# --- Base Stage ---
FROM node:18-slim AS base
WORKDIR /app
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN npm install -g pnpm

# --- Dependencies Stage ---
FROM base AS deps
COPY package.json pnpm-lock.yaml* ./
# Gunakan cache terpisah untuk instalasi dependensi
RUN --mount=type=cache,target=/root/.pnpm-store \
    pnpm install --frozen-lockfile --prod=false --ignore-scripts \
    --prefer-offline \
    --fetch-retries=5 \
    --fetch-retry-factor=2 \
    --fetch-retry-mintimeout=10000 \
    --fetch-retry-maxtimeout=120000

# --- Development Stage ---
FROM base AS development
COPY --from=deps /app/node_modules /app/node_modules
COPY . .
RUN pnpm run build:icons
EXPOSE 3010
CMD ["pnpm", "run", "dev"]

# --- Builder Stage ---
FROM base AS builder
COPY --from=deps /app/node_modules /app/node_modules
COPY . .
# Gunakan cache untuk build Nuxt/Vite
RUN --mount=type=cache,target=/app/.nuxt \
    --mount=type=cache,target=/app/node_modules/.vite \
    pnpm run build:icons --if-present && \
    pnpm run build

# --- Runtime Stage ---
FROM node:18-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.output ./.output
COPY --from=builder /app/public ./public
EXPOSE 3010
CMD ["node", ".output/server/index.mjs"]