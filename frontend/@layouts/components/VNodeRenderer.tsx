import type { PropType, VNode } from 'vue'
import { defineComponent } from 'vue'

export const VNodeRenderer = defineComponent({
  name: 'VNodeRenderer',

  props: {
    nodes: {
      type: [Array, Object] as PropType<VNode | VNode[]>,
      required: true,
      validator: (value: unknown) => {
        // Validasi runtime untuk VNode structure
        return Array.isArray(value)
          || (typeof value === 'object' && value !== null && 'type' in value)
      },
    },
  },

  setup(props: { nodes: VNode | VNode[] }) {
    return () => {
      // Handle invalid nodes gracefully
      if (!props.nodes)
        return null

      return props.nodes
    }
  },
})
