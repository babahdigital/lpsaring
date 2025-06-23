// frontend/plugins/vuetify/iconify-adapter.ts
import { h } from 'vue'
import { Icon as IconifyIcon } from '@iconify/vue'
import type { IconSet, IconProps } from 'vuetify'

const IconifyVuetifyAdapter: IconSet = {
  component: (props: IconProps) => {
    // Pastikan props.icon adalah string.
    // Jika props.icon adalah undefined, kita bisa memberikan string kosong atau ikon default sebagai fallback.
    // Memberikan string kosong mungkin akan merender ikon kosong, yang lebih baik daripada error tipe.
    const iconName = props.icon ? String(props.icon) : '' // Konversi ke string atau gunakan string kosong jika undefined

    // Penting: IconifyIcon juga bisa menerima objek IconifyIcon (untuk data JSON ikon langsung),
    // namun dalam konteks Vuetify dengan alias, biasanya yang datang adalah string.
    // Jika ada kemungkinan props.icon adalah objek IconifyIcon yang sudah diproses,
    // maka perlu penanganan lebih lanjut, tetapi untuk alias 'tabler:x', itu akan menjadi string.

    return h(IconifyIcon, { icon: iconName })
  },
}

export default IconifyVuetifyAdapter