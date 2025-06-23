// frontend/navigation/vertical/index.ts
// VERSI BARU: Mengadopsi menu secara dinamis dari navigasi horizontal

import { getHorizontalNavItems } from '@/navigation/horizontal' // <-- Mengimpor fungsi dari horizontal

// Definisikan tipe yang sama persis dengan yang ada di horizontal/index.ts untuk konsistensi
// Di proyek yang lebih besar, ini bisa diletakkan di file terpusat seperti 'navigation/types.ts'
interface VerticalNavItem {
  title: string
  icon: { icon: string }
  to?: { name?: string, path?: string }
  children?: VerticalNavItem[]
}

// Fungsi ini sekarang menjadi satu-satunya ekspor dari file ini
export function getVerticalNavItems(): VerticalNavItem[] {
  // Karena logika sudah ada di getHorizontalNavItems (termasuk pengecekan login dan peran),
  // kita hanya perlu memanggilnya saja.
  // Hasilnya akan berupa array menu yang sudah disesuaikan dengan peran pengguna yang sedang login.
  const navItems = getHorizontalNavItems()

  // TypeScript akan memastikan bahwa tipe data yang dikembalikan cocok.
  return navItems
}
