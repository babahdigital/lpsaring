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
  delete: 'tabler:trash',
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
  loading: 'tabler:refresh',

  // Input & Seleksi
  checkboxOn: 'tabler:checkbox',
  checkboxOff: 'tabler:square',
  checkboxIndeterminate: 'tabler:square-minus',
  // --- PERBAIKAN DI SINI ---
  radioOn: 'tabler:circle-dot',
  radioOff: 'tabler:circle',
  ratingEmpty: 'tabler:star',
  ratingFull: 'tabler:star-filled',
  ratingHalf: 'tabler:star-half-filled',

  // Tabel & Urutan
  sort: 'tabler:arrow-up',
  sortAsc: 'tabler:arrow-up',
  sortDesc: 'tabler:arrow-down',
  unfold: 'tabler:arrows-sort',
  delimiter: 'tabler:circle',

  // Lain-lain
  first: 'tabler:player-skip-back',
  last: 'tabler:player-skip-forward',
  file: 'tabler:paperclip',
  plus: 'tabler:plus',
  minus: 'tabler:minus',
}

export const icons = aliases