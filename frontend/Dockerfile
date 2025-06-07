# frontend/Dockerfile (Fixed Version)

# --- Base Stage ---
FROM node:18-slim AS base
WORKDIR /app
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN npm install -g pnpm

# --- Dependencies Stage ---
FROM base AS deps
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile --prod=false --ignore-scripts

# --- Development Stage ---
FROM base AS development
COPY --from=deps /app/node_modules /app/node_modules
COPY . .
RUN pnpm nuxt prepare
RUN pnpm run build:icons  # <-- Build ikon di sini untuk development
EXPOSE 3010
CMD ["pnpm", "run", "dev"]

# --- Builder Stage ---
FROM base AS builder
COPY --from=deps /app/node_modules /app/node_modules
COPY . .
RUN pnpm nuxt prepare
# Tambahkan build ikon di sini (wajib untuk produksi)
RUN pnpm run build:icons  # <-- PERBAIKAN: Build ikon selama proses build
RUN pnpm build

# --- Runtime Stage ---
FROM node:18-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production

# Hanya salin hasil build dari builder (TANPA install dependensi)
COPY --from=builder /app/.output ./.output
COPY --from=builder /app/public ./public

EXPOSE 3010
CMD ["node", ".output/server/index.mjs"]