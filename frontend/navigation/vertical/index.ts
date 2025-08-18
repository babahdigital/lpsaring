// frontend/navigation/vertical/index.ts
// VERSI SEMPURNA: Langsung mengekspor ulang composable horizontal untuk konsistensi

/**
 * Logika untuk navigasi vertikal sengaja dibuat untuk menggunakan logika yang sama
 * dengan navigasi horizontal. Ini memastikan menu yang ditampilkan akan selalu
 * identik, tidak peduli layout mana yang sedang aktif.
 * Kita cukup mengekspor ulang 'useHorizontalNav' dengan nama alias 'useVerticalNav'.
 */
export { useHorizontalNav as useVerticalNav } from '@/navigation/horizontal'
