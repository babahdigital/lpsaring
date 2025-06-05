# backend/Dockerfile

# --- Base Stage ---
# Menggunakan image Python 3.11 slim sebagai dasar (Debian Bookworm)
FROM python:3.11-slim AS base

# Set environment variables untuk Python dan Pip
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# --- Builder Stage ---
# Tahap untuk menginstall dependensi build sistem dan Python
FROM base AS builder

# Set direktori kerja di dalam container (dipindahkan ke builder agar /app ada saat build)
WORKDIR /app

# Install dependensi sistem yang dibutuhkan untuk build
# Termasuk -dev packages untuk kompilasi extension Python jika ada
# Tambahkan 'locales' di sini agar bisa generate locale di builder jika perlu,
# tapi konfigurasi utamanya nanti di runtime stage.
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    # Dependensi build WeasyPrint (beberapa mungkin tidak wajib tapi aman disertakan)
    libglib2.0-dev \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf2.0-dev \
    locales \
 # Hapus cache apt setelah install untuk menghemat ruang
 && rm -rf /var/lib/apt/lists/*

# Salin file requirements.txt
COPY requirements.txt .

# Install dependensi Python
# Upgrade pip terlebih dahulu
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# --- Runtime Stage ---
# Tahap final untuk menjalankan aplikasi
FROM base AS runtime

# >>> PENAMBAHAN: Install locales dan konfigurasi id_ID.UTF-8 <<<
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    locales \
    # Regenerasi file locale untuk id_ID.UTF-8
    && sed -i -e 's/# id_ID.UTF-8 UTF-8/id_ID.UTF-8 UTF-8/' /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=id_ID.UTF-8
# >>> AKHIR PENAMBAHAN <<<

# Install HANYA dependensi sistem RUNTIME yang dibutuhkan
# Tidak perlu -dev packages di sini
# libffi8 adalah versi runtime untuk libffi-dev di Debian Bookworm
RUN apt-get install -y --no-install-recommends \
    libpq5 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi8 \
    libfontconfig1 \
    libfreetype6 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
 # Hapus cache apt setelah install untuk menghemat ruang
 && rm -rf /var/lib/apt/lists/*

# >>> PENAMBAHAN: Set environment variables untuk locale <<<
ENV LANG=id_ID.UTF-8
ENV LANGUAGE=id_ID:id
ENV LC_ALL=id_ID.UTF-8
# >>> AKHIR PENAMBAHAN <<<

# Buat user dan group non-root untuk keamanan
ARG APP_USER=appuser
ARG APP_GROUP=appgroup
RUN groupadd -r ${APP_GROUP} && useradd -r -g ${APP_GROUP} ${APP_USER}

# Set direktori kerja lagi
WORKDIR /app

# Salin dependensi Python yang sudah terinstall dari tahap builder
# Menyalin seluruh site-packages dan binari yang relevan
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# TIDAK PERLU menyalin library sistem dari builder karena sudah diinstall langsung di runtime

# Salin kode aplikasi dari konteks build saat ini ke direktori kerja di container
# Lakukan ini SETELAH menyalin dependensi agar layer cache Docker lebih efektif
COPY . .

# Berikan kepemilikan direktori /app dan isinya ke user non-root
# Pastikan ini dilakukan SETELAH semua file disalin ke /app
RUN chown -R ${APP_USER}:${APP_GROUP} /app

# Ganti ke user non-root untuk menjalankan aplikasi
USER ${APP_USER}

# Expose port yang akan digunakan oleh aplikasi di dalam container
EXPOSE 5010

# Perintah default untuk menjalankan aplikasi
# Jika ini untuk produksi, SANGAT direkomendasikan menggunakan Gunicorn atau ASGI server lain
# Contoh Gunicorn (sesuaikan 'wsgi:app' jika nama file/app Flask Anda berbeda):
# CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers=4", "--log-level=info", "wsgi:app"]
#
# Tetap menggunakan Flask dev server untuk development:
CMD ["flask", "run", "--host=0.0.0.0", "--port=5010"]