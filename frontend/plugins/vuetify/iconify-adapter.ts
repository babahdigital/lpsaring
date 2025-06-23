// frontend/plugins/vuetify/iconify-adapter.ts
// --- KODE BARU DAN FINAL ---

import { defineAsyncComponent, h } from 'vue'
import type { IconProps, IconSet } from 'vuetify'

/**
 * Adapter kustom untuk Vuetify yang terintegrasi dengan `unplugin-icons`.
 * Adapter ini secara dinamis mengimpor komponen ikon dari modul virtual `~icons/...`
 * yang dibuat oleh `unplugin-icons` saat proses build.
 * Ini memastikan bahwa hanya ikon yang digunakan yang masuk ke dalam bundle,
 * dan semuanya bekerja secara offline tanpa panggilan API eksternal.
 */
const UnpluginIconsVuetifyAdapter: IconSet = {
  component: (props: IconProps) => {
    const icon = props.icon as string

    if (!icon)
      return h('span') // Render elemen kosong jika tidak ada ikon

    // Mem-format nama ikon dari 'collection:name' menjadi '~icons/collection/name'
    // Contoh: 'tabler:circle-check' -> '~icons/tabler/circle-check'
    const [collection, name] = icon.split(':')
    if (!collection || !name) {
      // Jika format tidak sesuai, render elemen kosong untuk mencegah error
      console.warn(`[Icon Adapter] Format nama ikon tidak valid: "${icon}". Diharapkan format "koleksi:nama".`)
      return h('span')
    }

    // Menggunakan defineAsyncComponent dari Vue untuk memuat ikon secara dinamis.
    // Komentar /* @vite-ignore */ sangat penting untuk mencegah Vite
    // mencoba menyelesaikan impor ini saat build.
    const component = defineAsyncComponent(() =>
      import(/* @vite-ignore */ `~icons/${collection}/${name}`),
    )

    // Merender komponen ikon yang telah dimuat, sambil meneruskan semua properti lain
    // seperti 'class', 'style', 'size', dan lainnya ke komponen ikon.
    return h(component, props)
  },
}

export default UnpluginIconsVuetifyAdapter