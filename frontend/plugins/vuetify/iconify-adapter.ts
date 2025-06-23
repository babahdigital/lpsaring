import type { IconProps, IconSet } from 'vuetify'
import { Icon as IconifyIcon } from '@iconify/vue'
// frontend/plugins/vuetify/iconify-adapter.ts
import { h } from 'vue'

const IconifyVuetifyAdapter: IconSet = {
  component: (props: IconProps) => {
    const iconName = props.icon ? String(props.icon) : ''
    return h(IconifyIcon, { icon: iconName })
  },
}

export default IconifyVuetifyAdapter
