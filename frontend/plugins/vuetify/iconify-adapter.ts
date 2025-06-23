import type { IconProps, IconSet } from 'vuetify'
import { Icon as IconifyIcon } from '@iconify/vue'
// frontend/plugins/vuetify/iconify-adapter.ts
import { h } from 'vue'

const IconifyVuetifyAdapter: IconSet = {
  component: (props: IconProps) => {
    // PERBAIKAN: Periksa secara eksplisit apakah props.icon tidak null dan tidak undefined.
    const iconName = (props.icon !== null && props.icon !== undefined)
      ? String(props.icon) // Pastikan dikonversi ke string jika valid
      : '' // Default ke string kosong jika null atau undefined

    // Penting: IconifyIcon juga bisa menerima objek IconifyIcon (untuk data JSON ikon langsung),
    // namun dalam konteks Vuetify dengan alias, biasanya yang datang adalah string.
    // Jika ada kemungkinan props.icon adalah objek IconifyIcon yang sudah diproses,
    // maka perlu penanganan lebih lanjut, tetapi untuk alias 'tabler:x', itu akan menjadi string.

    return h(IconifyIcon, { icon: iconName })
  },
}

export default IconifyVuetifyAdapter
