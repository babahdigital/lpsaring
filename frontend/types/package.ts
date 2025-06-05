// frontend/types/package.ts

/**
 * Mendefinisikan struktur (interface) untuk objek Paket Hotspot.
 * Properti ini harus cocok dengan data yang dikirim oleh API backend
 * dari endpoint /api/packages.
 */
export interface Package {
  // Properti Wajib (berdasarkan model backend umum)
  id: string // Tipe UUID biasanya string saat di JSON/TS
  name: string
  price: number // Gunakan tipe number untuk nilai numerik
  duration_minutes: number
  is_active: boolean // Status apakah paket aktif/bisa dibeli

  // Properti Opsional (mungkin null atau tidak ada di semua paket)
  description: string | null
  speed_limit: string | null // Contoh format: "1Mbps/512kbps" atau null
  quota_limit_mb: number | null // Batas kuota dalam Megabytes

  // Timestamp (biasanya string ISO 8601 dari backend)
  created_at: string
  updated_at: string

  // Tambahkan properti lain jika ada di model backend Anda
  // Misalnya:
  // user_profile: string | null; // Nama profile di MikroTik
}
