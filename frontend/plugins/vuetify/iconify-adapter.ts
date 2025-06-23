// frontend/plugins/vuetify/iconify-adapter.ts
import { h } from 'vue'
import { Icon as IconifyIcon } from '@iconify/vue'
import type { IconSet, IconProps } from 'vuetify'

const IconifyVuetifyAdapter: IconSet = {
  component: (props: IconProps) => {
    const iconName = props.icon ? String(props.icon) : ''
    return h(IconifyIcon, { icon: iconName })
  },
}

export default IconifyVuetifyAdapter