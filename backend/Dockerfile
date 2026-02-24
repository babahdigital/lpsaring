# backend/Dockerfile (Versi Disempurnakan)

# --- Base Stage ---
# Menggunakan image Python 3.11 slim sebagai dasar (pin ke Debian Bookworm)
# Penting untuk menjaga versi `postgresql-client` stabil dan kompatibel dengan server Postgres 15.
FROM python:3.11-slim-bookworm AS base

# Set environment variables untuk Python dan Pip
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    # Menambahkan path untuk venv
    PATH="/opt/venv/bin:$PATH"

# --- Builder Stage ---
# Tahap untuk menginstall dependensi build sistem dan Python
FROM base AS builder

# Set direktori kerja
WORKDIR /app

# Install dependensi sistem yang dibutuhkan untuk build
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    # Dependensi build WeasyPrint
    libglib2.0-dev \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf-xlib-2.0-dev \
    # Hapus cache apt setelah install untuk menghemat ruang
    && rm -rf /var/lib/apt/lists/*

# Salin file requirements.txt
COPY requirements.txt .

# --- OPTIMASI #1: Membuat dan menggunakan virtual environment ---
RUN python -m venv /opt/venv
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# --- Runtime Stage ---
# Tahap final untuk menjalankan aplikasi
FROM base AS runtime

# Buat user dan group non-root terlebih dahulu
ARG APP_USER=appuser
ARG APP_GROUP=appgroup
RUN groupadd -r ${APP_GROUP} && useradd -r -g ${APP_GROUP} ${APP_USER}

# Set direktori kerja
WORKDIR /app

# --- OPTIMASI #2: Menggabungkan instalasi apt-get dan konfigurasi locale ---
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    # Dependensi locale
    locales \
    # Dependensi runtime sistem
    libpq5 \
    libffi8 \
    postgresql-client-15 \
    # Dependensi runtime WeasyPrint
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-xlib-2.0-0 \
    libfontconfig1 \
    libfreetype6 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    # Konfigurasi locale di dalam satu layer
    && sed -i -e 's/# id_ID.UTF-8 UTF-8/id_ID.UTF-8 UTF-8/' /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=id_ID.UTF-8 \
    # Hapus cache apt setelah semua selesai
    && rm -rf /var/lib/apt/lists/*

# Set environment variables untuk locale
ENV LANG=id_ID.UTF-8
ENV LANGUAGE=id_ID:id
ENV LC_ALL=id_ID.UTF-8

# BUAT DIREKTORI CACHE YANG DAPAT DITULIS DAN SET IZINNYA
RUN mkdir -p /app/.cache/fontconfig && \
    chown -R ${APP_USER}:${APP_GROUP} /app/.cache

# Set environment variable untuk fontconfig
ENV XDG_CACHE_HOME=/app/.cache

# Salin virtual environment yang sudah berisi dependensi Python dari builder
COPY --from=builder /opt/venv /opt/venv

# Salin kode aplikasi dari konteks build saat ini
COPY . .

# Berikan kepemilikan direktori /app ke user non-root
# Bagian ini sudah mencakup /app/.cache karena sudah di chown sebelumnya.
RUN chown -R ${APP_USER}:${APP_GROUP} /app

# Ganti ke user non-root
USER ${APP_USER}

# Expose port yang akan digunakan
EXPOSE 5010

# Perintah default untuk menjalankan aplikasi
# Untuk produksi, gunakan Gunicorn atau ASGI server lainnya.
# CMD ["gunicorn", "--bind", "0.0.0.0:5010", "--workers=4", "--log-level=info", "nama_file_wsgi:app"]
CMD ["flask", "run", "--host=0.0.0.0", "--port=5010"]