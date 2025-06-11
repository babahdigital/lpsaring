-- backend/migrations/fix_enum_data.sql
-- Skrip ini dirancang untuk memperbaiki nilai Enum yang tidak konsisten
-- pada kolom 'blok' dan 'kamar' di tabel 'users'.
-- PASTIKAN UNTUK MEMBACKUP DATABASE SEBELUM MENJALANKAN SKRIP INI.

-- LANGKAH 1: Ubah tipe kolom sementara menjadi TEXT untuk memungkinkan perubahan data tidak valid
-- Ini penting karena nilai yang ada ('1', '2', dst.) mungkin tidak valid untuk tipe ENUM native saat ini.
ALTER TABLE users
ALTER COLUMN blok TYPE TEXT;

ALTER TABLE users
ALTER COLUMN kamar TYPE TEXT;

-- LANGKAH 2: Memperbaiki nilai data di kolom 'blok' (sekarang TEXT)
-- Sekarang kita bisa UPDATE nilai-nilai yang tidak valid ke representasi string Enum yang benar.
UPDATE users
SET blok = 'A'
WHERE blok = '1';

UPDATE users
SET blok = 'B'
WHERE blok = '2';

UPDATE users
SET blok = 'C'
WHERE blok = '3';

UPDATE users
SET blok = 'D'
WHERE blok = '4';

UPDATE users
SET blok = 'E'
WHERE blok = '5';

UPDATE users
SET blok = 'F'
WHERE blok = '6';

-- LANGKAH 3: Memperbaiki nilai data di kolom 'kamar' (sekarang TEXT)
-- Pastikan klausa WHERE menargetkan nilai string numerik yang tidak valid.
UPDATE users
SET kamar = 'Kamar_1'
WHERE kamar = '1';

UPDATE users
SET kamar = 'Kamar_2'
WHERE kamar = '2';

UPDATE users
SET kamar = 'Kamar_3'
WHERE kamar = '3';

UPDATE users
SET kamar = 'Kamar_4'
WHERE kamar = '4';

UPDATE users
SET kamar = 'Kamar_5'
WHERE kamar = '5';

UPDATE users
SET kamar = 'Kamar_6'
WHERE kamar = '6';

-- LANGKAH DIAGNOSTIK BARU: Periksa definisi Enum native di PostgreSQL
-- Jalankan kueri berikut di psql secara manual atau periksa output saat menjalankan skrip.
-- Ini akan menampilkan daftar nilai yang tepat yang diterima oleh tipe ENUM native di database Anda.
-- Perhatikan huruf besar/kecil dan spasi.
SELECT enum_range('userblokenum'::regtype);
SELECT enum_range('userkamarenum'::regtype);

-- LANGKAH 4: Ubah tipe kolom kembali ke ENUM yang benar, dengan melakukan CAST
-- Klausa 'USING' penting untuk mengarahkan PostgreSQL bagaimana mengonversi nilai TEXT
-- yang telah diperbaiki ke tipe ENUM native.
-- Jika ada masalah di atas, baris ini mungkin masih gagal.
ALTER TABLE users
ALTER COLUMN blok TYPE userblokenum USING blok::userblokenum;

ALTER TABLE users
ALTER COLUMN kamar TYPE userkamarenum USING kamar::userkamarenum;

-- Opsional: Tambahkan log atau verifikasi jika diperlukan setelah migrasi
-- Anda bisa menjalankan query ini secara manual di psql untuk memverifikasi.
-- SELECT COUNT(*) FROM users WHERE blok NOT IN ('A', 'B', 'C', 'D', 'E', 'F');
-- SELECT COUNT(*) FROM users WHERE kamar NOT IN ('Kamar_1', 'Kamar_2', 'Kamar_3', 'Kamar_4', 'Kamar_5', 'Kamar_6');

-- Tinjau beberapa baris untuk melihat perubahan:
-- SELECT id, blok, kamar FROM users LIMIT 10;
