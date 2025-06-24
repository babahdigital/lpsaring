// frontend/plugins/vuetify/css-icon-adapter.ts
import type { IconProps, IconSet } from 'vuetify'
import { h } from 'vue'

/**
 * Adapter ini mengintegrasikan sistem ikon berbasis CSS (dihasilkan oleh build-icons.ts) dengan Vuetify.
 * Ia akan mengubah nama ikon seperti 'tabler:chevron-down' menjadi elemen <i> dengan
 * kelas CSS yang sesuai, yaitu 'icon--tabler--chevron-down'.
 *
 * Versi ini lebih tangguh untuk menangani format ikon yang salah.
 */
const CssIconAdapter: IconSet = {
  component: (props: IconProps & { class?: string }) => {
    const iconName = (props.icon as string) || ''

    // Pengecekan 1: Menangani ikon MDI yang salah format (menggunakan 'mdi-' bukan 'mdi:')
    // Ikon ini seharusnya di-routing ke 'mdi' set, bukan ke sini (adapter 'tabler').
    if (iconName.startsWith('mdi-')) {
      console.warn(`[Ikon Vuetify] Format ikon MDI salah: "${iconName}". Seharusnya menggunakan format "mdi:nama-ikon" (dengan titik dua) agar dapat di-render dengan benar oleh set 'mdi'. Ikon ini akan dilewati oleh adapter 'tabler'.`)
      // Kembalikan elemen kosong agar tidak error, tapi teruskan props seperti class
      return h('i', { ...props })
    }

    // Pengecekan 2: Menangani format standar 'prefix:nama'
    if (iconName.includes(':')) {
      const [prefix, name] = iconName.split(':', 2)
      const iconClass = `icon--${prefix}--${name}`
      return h('i', { ...props, class: [iconClass, props.class] })
    }

    // Pengecekan 3: Menangani format yang berpotensi salah seperti 'tabler-nama'
    if (iconName.includes('-')) {
        console.warn(`[Ikon Vuetify] Format ikon berpotensi salah: "${iconName}". Adapter mengharapkan format "prefix:nama". Mohon periksa kembali kode Anda.`)
    }

    // Penanganan Fallback: Asumsikan ikon tanpa prefix adalah bagian dari 'tabler' set
    // Ini akan menangani kasus seperti 'chevron-down'
    const prefix = 'tabler'
    const name = iconName
    const iconClass = `icon--${prefix}--${name}`

    return h('i', { ...props, class: [iconClass, props.class] })
  },
}

export default CssIconAdapter