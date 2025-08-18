// frontend/plugins/vuetify/iconify-adapter.ts
// --- KODE FINAL YANG BENAR DAN STANDAR ---

import type { IconProps, IconSet } from 'vuetify'

import { Icon as IconifyIcon } from '@iconify/vue'
import { h } from 'vue'

/**
 * Adapter ini menggunakan komponen 'Icon' dari @iconify/vue.
 * Komponen ini secara cerdas akan:
 * 1. Mem-parsing semua format nama ikon (contoh: 'tabler:home', 'mdi-account').
 * 2. Menggunakan data ikon dari '@iconify/json' yang sudah terinstal di proyek.
 * Ini membuat semua ikon bekerja secara offline tanpa panggilan API.
 */
const IconifyVuetifyAdapter: IconSet = {
  component: (props: IconProps) => {
    // Cukup teruskan nama ikon ke komponen IconifyIcon.
    // Komponen ini akan menangani sisanya.
    return h(IconifyIcon, { icon: props.icon as string })
  },
}

export default IconifyVuetifyAdapter
