# frontend/Dockerfile (Versi Diperbaiki dan Dioptimalkan)

# --- Base Stage ---
# Mendefinisikan base image yang sama untuk semua stage
FROM node:18-slim AS base
WORKDIR /app
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN npm install -g pnpm

# --- Dependencies Stage ---
# Stage ini hanya bertanggung jawab untuk menginstall SEMUA dependensi (dev & prod)
FROM base AS deps
# Salin hanya file manifest dan lockfile
COPY package.json pnpm-lock.yaml* ./
# Install semua dependensi menggunakan lockfile untuk konsistensi.
# Mengabaikan script postinstall di sini karena source code belum ada.
RUN pnpm install --frozen-lockfile --prod=false

# --- Builder Stage ---
# Stage ini bertanggung jawab untuk membuat build produksi dari aplikasi
FROM base AS builder
# Salin semua dependensi yang sudah ter-install dari stage 'deps'
COPY --from=deps /app/node_modules /app/node_modules
# Salin seluruh source code aplikasi
COPY . .
# Jalankan perintah build yang dibutuhkan.
# Semua devDependencies tersedia di sini.
RUN pnpm nuxt prepare
RUN pnpm run build:icons
RUN pnpm build
# PERHATIKAN: Perintah 'pnpm prune --prod' telah dihapus dari sini.
# Output dari stage ini adalah direktori .output yang berisi hasil build.

# --- Runtime Stage ---
# Stage final yang akan dijalankan di produksi. Dibuat seramping mungkin.
FROM base AS runtime
WORKDIR /app
ENV NODE_ENV=production
# Salin file manifest dan lockfile yang dibutuhkan untuk installasi dependensi produksi
COPY package.json pnpm-lock.yaml* ./
# Install HANYA dependensi produksi. Ini adalah cara yang benar untuk mendapatkan
# node_modules yang bersih dan ramping untuk produksi.
RUN pnpm install --prod --frozen-lockfile
# Salin hasil build (aset final) dari 'builder' stage
COPY --from=builder /app/.output ./.output
# Salin direktori public jika ada aset statis yang tidak diproses oleh build Nuxt
COPY --from=builder /app/public ./public
EXPOSE 3010
# CMD untuk menjalankan aplikasi dari server yang sudah di-build
CMD ["node", ".output/server/index.mjs"]