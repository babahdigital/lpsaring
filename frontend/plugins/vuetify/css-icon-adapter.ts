// frontend/plugins/vuetify/css-icon-adapter.ts
import type { IconProps, IconSet } from 'vuetify'
import { h } from 'vue'

/**
 * Adapter ini mengintegrasikan sistem ikon berbasis CSS (dihasilkan oleh build-icons.ts) dengan Vuetify.
 * Ia akan mengubah nama ikon seperti 'tabler:chevron-down' menjadi elemen <i> dengan
 * kelas CSS yang sesuai, yaitu 'icon--tabler--chevron-down'.
 */
const CssIconAdapter: IconSet = {
  // --- PERBAIKAN DI SINI ---
  // Kita perbarui tipe props untuk menyertakan 'class' yang merupakan fallthrough attribute.
  component: (props: IconProps & { class?: string }) => {
    // Memisahkan nama ikon dari prefix-nya. Contoh: 'tabler:chevron-down'
    const iconName = (props.icon as string) || ''
    const [prefix, name] = iconName.split(':')

    if (!prefix || !name) {
      // Menangani kasus jika format ikon salah
      console.warn(`Invalid icon name format: ${iconName}. Expected format: 'prefix:name'.`)
      return h('i') // Mengembalikan elemen kosong
    }

    // Menghasilkan elemen `<i>` dengan kelas yang akan dicocokkan oleh icons.css
    // Contoh: <i class="icon--tabler--chevron-down"></i>
    const iconClass = `icon--${prefix}--${name}`

    // Menggunakan h() dari Vue untuk membuat elemen secara programmatic
    // Vue akan secara otomatis menggabungkan `props.class` dari parent
    // dengan `iconClass` yang kita definisikan di sini.
    return h('i', {
      ...props,
      class: [iconClass, props.class], // Sekarang props.class dikenali oleh TypeScript
    })
  },
}

export default CssIconAdapter
