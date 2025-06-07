# frontend/Dockerfile (Final Corrected Version)

# --- Base Stage ---
# Mendefinisikan base image yang sama untuk semua stage selanjutnya.
FROM node:18-slim AS base
WORKDIR /app
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN npm install -g pnpm

# --- Dependencies Stage ---
# Stage ini hanya bertanggung jawab untuk menginstall SEMUA dependensi (dev & prod).
# Ini dipisahkan untuk memanfaatkan cache layer Docker secara maksimal.
FROM base AS deps
COPY package.json pnpm-lock.yaml* ./
# Install semua dependensi menggunakan lockfile untuk konsistensi.
# --ignore-scripts ditambahkan untuk mencegah postinstall berjalan sebelum source code ada.
RUN pnpm install --frozen-lockfile --prod=false --ignore-scripts

# --- Development Stage ---
# INI ADALAH TARGET yang dicari oleh docker-compose.yml untuk development.
FROM base AS development
# Salin dependensi yang sudah ter-install dari stage 'deps'.
COPY --from=deps /app/node_modules /app/node_modules
# Salin seluruh source code aplikasi.
COPY . .
# Jalankan skrip persiapan yang mungkin diperlukan sebelum server development berjalan.
RUN pnpm nuxt prepare
RUN pnpm run build:icons
EXPOSE 3010
# Perintah untuk menjalankan Nuxt development server dengan hot-reloading.
CMD ["pnpm", "run", "dev"]

# --- Builder Stage ---
# Stage ini digunakan untuk membuat build produksi final.
FROM base AS builder
# Salin dependensi dan source code.
COPY --from=deps /app/node_modules /app/node_modules
COPY . .
# Jalankan perintah build yang dibutuhkan. Semua devDependencies tersedia di sini.
RUN pnpm nuxt prepare
RUN pnpm run build:icons
RUN pnpm build
# Output dari stage ini adalah artifak build final di dalam direktori .output.

# --- Runtime Stage ---
# Stage final yang ramping untuk menjalankan aplikasi di produksi.
FROM base AS runtime
WORKDIR /app
ENV NODE_ENV=production
# Salin file manifest DAN lockfile untuk instalasi produksi yang konsisten.
COPY package.json pnpm-lock.yaml* ./
# Install HANYA dependensi produksi untuk menjaga ukuran image tetap kecil.
RUN pnpm install --prod --frozen-lockfile
# Salin aplikasi yang sudah di-build dari 'builder' stage.
COPY --from=builder /app/.output ./.output
# Salin direktori public jika berisi aset statis.
COPY --from=builder /app/public ./public
EXPOSE 3010
# Perintah untuk menjalankan server produksi.
CMD ["node", ".output/server/index.mjs"]