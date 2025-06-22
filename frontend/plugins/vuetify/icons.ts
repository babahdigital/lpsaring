// frontend/plugins/vuetify/icons.ts
import type { IconAliases } from 'vuetify'

/**
 * Definisikan alias ikon untuk komponen internal Vuetify.
 * Komponen seperti VAlert, VDataTable, VRating, VCheckbox, dll., menggunakan alias ini.
 * Kita gunakan nama ikon dari set 'tabler' dengan prefix 'tabler:'
 * agar kompatibel dengan Iconify yang kemungkinan digunakan oleh nuxt-icon atau <Icon>.
 */
const aliases: Partial<IconAliases> = {
  // Navigasi & Kontrol Dasar
  collapse: 'tabler:chevron-up',
  expand: 'tabler:chevron-down',
  complete: 'tabler:check',
  cancel: 'tabler:x',
  close: 'tabler:x',
  prev: 'tabler:chevron-left',
  next: 'tabler:chevron-right',
  edit: 'tabler:pencil',
  delete: 'tabler:trash', // Lebih umum pakai 'trash' daripada 'circle-x-filled' untuk delete
  clear: 'tabler:circle-x',
  calendar: 'tabler:calendar',
  menu: 'tabler:menu-2',
  dropdown: 'tabler:chevron-down',
  subgroup: 'tabler:caret-down',

  // Status & Feedback
  success: 'tabler:circle-check',
  info: 'tabler:info-circle',
  warning: 'tabler:alert-triangle',
  error: 'tabler:alert-circle',
  loading: 'tabler:refresh', // Atau 'tabler:loader-2' (animasi)

  // Input & Seleksi
  checkboxOn: 'tabler:checkbox', // Menggunakan ikon checkbox standar tabler
  checkboxOff: 'tabler:square',
  checkboxIndeterminate: 'tabler:square-minus',
  radioOn: 'tabler:radio', // Menggunakan ikon radio standar tabler
  radioOff: 'tabler:circle',
  ratingEmpty: 'tabler:star',
  ratingFull: 'tabler:star-filled',
  ratingHalf: 'tabler:star-half-filled',

  // Tabel & Urutan
  sort: 'tabler:arrow-up', // Ikon default saat bisa di-sort
  sortAsc: 'tabler:arrow-up',
  sortDesc: 'tabler:arrow-down',
  unfold: 'tabler:arrows-sort', // Lebih cocok untuk 'show/hide details' di tabel
  delimiter: 'tabler:circle', // Untuk VStepper, VBreadcrumbs

  // Lain-lain (jika diperlukan oleh komponen spesifik atau custom)
  first: 'tabler:player-skip-back',
  last: 'tabler:player-skip-forward',
  file: 'tabler:paperclip',
  plus: 'tabler:plus',
  minus: 'tabler:minus',

  // Anda bisa menambahkan alias kustom lain di sini jika diperlukan
}

// Ekspor objek konfigurasi ikon untuk Vuetify
// Kita hanya menyediakan 'aliases'. Vuetify akan menggunakan set ikon default
// yang terintegrasi dengannya (biasanya Material Design Icons via @mdi/font atau
// via Iconify jika dikonfigurasi) ATAU mengandalkan komponen <Icon> eksternal
// untuk merender ikon berdasarkan nama alias ini.
export const icons = {
  aliases,
  // Tidak perlu mendefinisikan 'defaultSet' atau 'sets' jika
  // Anda secara konsisten menggunakan komponen <Icon icon="prefix:nama-ikon" />
  // di template Anda untuk ikon-ikon spesifik.
}
