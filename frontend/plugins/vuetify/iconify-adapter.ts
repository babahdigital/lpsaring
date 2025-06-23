// frontend/plugins/vuetify/iconify-adapter.ts
import { h } from 'vue'
import { Icon as IconifyIcon } from '@iconify/vue'
import type { IconSet, IconProps } from 'vuetify'

const IconifyVuetifyAdapter: IconSet = {
  component: (props: IconProps) => {
    const iconName = (props.icon !== null && props.icon !== undefined)
      ? String(props.icon)
      : ''

    // PENTING: Pastikan Anda mengembalikan h(IconifyIcon, { icon: iconName })
    // dan BUKAN hanya string SVG mentah jika props.icon adalah string SVG.
    // Dalam kasus 'tabler:check', props.icon seharusnya adalah string "tabler:check",
    // dan IconifyIcon akan menanganinya.
    return h(IconifyIcon, { icon: iconName })
  },
}

export default IconifyVuetifyAdapter