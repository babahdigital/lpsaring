// frontend/plugins/vuetify/iconify-adapter.ts
// --- KODE VERSI FINAL (SOLUSI SATU FILE) ---

import { defineAsyncComponent, h } from 'vue'
import type { IconProps, IconSet } from 'vuetify'

const FinalVuetifyIconAdapter: IconSet = {
  component: (props: IconProps) => {
    let icon = props.icon as string

    if (!icon)
      return h('span')

    // --- LOGIKA KUNCI: Secara otomatis memperbaiki format 'tabler-' ---
    // Ini adalah kunci untuk menghindari perubahan di banyak file.
    // Ia akan mengubah 'tabler-cash' menjadi 'tabler:cash' secara otomatis.
    if (icon.startsWith('tabler-')) {
      icon = icon.replace('-', ':')
    }

    // Cek apakah ikon sekarang menggunakan format 'koleksi:nama'
    if (icon.includes(':')) {
      const component = defineAsyncComponent(() => import(/* @vite-ignore */ `~icons/${icon.replace(':', '/')}`))

      return h(component, props)
    }

    // Cek jika ikon adalah format mdi- (contoh: 'mdi-account')
    if (icon.startsWith('mdi-')) {
      const component = defineAsyncComponent(() => import(/* @vite-ignore */ `~icons/mdi/${icon.substring(4)}`))

      return h(component, props)
    }

    // Jika tidak ada kondisi di atas yang terpenuhi (contoh: 'chevron-down'),
    // anggap ikon tersebut berasal dari koleksi 'tabler' sebagai default.
    const component = defineAsyncComponent(() => import(/* @vite-ignore */ `~icons/tabler/${icon}`))

    return h(component, props)
  },
}

export default FinalVuetifyIconAdapter