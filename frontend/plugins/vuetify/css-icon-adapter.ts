// frontend/plugins/vuetify/css-icon-adapter.ts
import type { IconProps, IconSet } from 'vuetify'
import { h } from 'vue'

/**
 * Adapter ini mengintegrasikan sistem ikon berbasis CSS (dihasilkan oleh build-icons.ts) dengan Vuetify.
 * Ia akan mengubah nama ikon seperti 'tabler:chevron-down' menjadi elemen <i> dengan
 * kelas CSS yang sesuai, yaitu 'icon--tabler--chevron-down'.
 *
 * Versi ini telah disempurnakan untuk secara cerdas menangani berbagai format nama ikon
 * tanpa menghasilkan peringatan yang tidak perlu di konsol.
 */
const CssIconAdapter: IconSet = {
  component: (props: IconProps & { class?: string }) => {
    const iconName = (props.icon as string) || ''
    let iconClass = ''

    // Pengecekan 1: Menangani ikon MDI yang mungkin salah masuk ke adapter ini.
    if (iconName.startsWith('mdi-')) {
      console.warn(`[Ikon Vuetify] Format ikon MDI salah: "${iconName}". Seharusnya menggunakan format "mdi:nama-ikon".`)
      return h('i', { ...props })
    }

    // Pengecekan 2: Menangani format standar yang sudah benar 'prefix:nama' (contoh: 'tabler:home').
    if (iconName.includes(':')) {
      const [prefix, name] = iconName.split(':', 2)
      iconClass = `icon--${prefix}--${name}`
    }
    // Pengecekan 3: Menangani format umum 'prefix-nama' (contoh: 'tabler-mail-fast') dan memperbaikinya.
    else if (iconName.startsWith('tabler-')) {
      // --- PERBAIKAN LOGIKA ADA DI SINI ---
      // Menggunakan indexOf dan substring untuk memisahkan nama ikon dengan benar,
      // bahkan jika nama ikon mengandung tanda hubung.
      const firstHyphenIndex = iconName.indexOf('-')
      const prefix = iconName.substring(0, firstHyphenIndex) // Hasil: 'tabler'
      const name = iconName.substring(firstHyphenIndex + 1)   // Hasil: 'mail-fast'
      iconClass = `icon--${prefix}--${name}`
    }
    // Pengecekan 4 (Fallback): Menangani format tanpa prefix (contoh: 'chevron-down').
    else {
      iconClass = `icon--tabler--${iconName}`
    }

    return h('i', { ...props, class: [iconClass, props.class] })
  },
}

export default CssIconAdapter