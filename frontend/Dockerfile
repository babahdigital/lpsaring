# frontend/Dockerfile (Versi Optimal - Kembali ke Normal)

# --- Base Stage ---
    FROM node:18-slim AS base
    WORKDIR /app
    ENV PNPM_HOME="/pnpm"
    ENV PATH="$PNPM_HOME:$PATH"
    RUN npm install -g pnpm
    
    # --- Dependencies Stage ---
    FROM base AS deps
    # Copy manifest DAN lockfile dari host
    COPY package.json pnpm-lock.yaml* ./
    # Install pakai lockfile, abaikan script postinstall di sini
    RUN pnpm install --frozen-lockfile --prod=false --ignore-scripts
    
    # --- Development Stage ---
    FROM base AS development
    COPY --from=deps /app/node_modules /app/node_modules
    COPY --from=deps $PNPM_HOME $PNPM_HOME
    COPY . .
    # Jalankan skrip setelah source code ada
    RUN pnpm nuxt prepare
    RUN pnpm run build:icons
    EXPOSE 3010
    CMD ["pnpm", "run", "dev"]
    
    # --- Builder Stage ---
    FROM base AS builder
    COPY --from=deps /app/node_modules /app/node_modules
    COPY --from=deps $PNPM_HOME $PNPM_HOME
    COPY . .
    RUN pnpm nuxt prepare
    RUN pnpm run build:icons
    RUN pnpm build
    RUN pnpm prune --prod
    
    # --- Runtime Stage ---
    FROM base AS runtime
    WORKDIR /app
    ENV NODE_ENV=production
    COPY --from=builder /app/.output /app/.output
    COPY package.json .
    COPY --from=builder /app/node_modules /app/node_modules
    EXPOSE 3010
    CMD ["node", ".output/server/index.mjs"]