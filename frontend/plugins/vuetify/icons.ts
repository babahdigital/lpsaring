import checkboxChecked from '@images/svg/checkbox-checked.svg'
import checkboxIndeterminate from '@images/svg/checkbox-indeterminate.svg'
import checkboxUnchecked from '@images/svg/checkbox-unchecked.svg'
import radioChecked from '@images/svg/radio-checked.svg'
import radioUnchecked from '@images/svg/radio-unchecked.svg'

const customIcons: Record<string, unknown> = {
  'mdi-checkbox-blank-outline': checkboxUnchecked,
  'mdi-checkbox-marked': checkboxChecked,
  'mdi-minus-box': checkboxIndeterminate,
  'mdi-radiobox-marked': radioChecked,
  'mdi-radiobox-blank': radioUnchecked,
}

function normalizeIconName(icon: string): string {
  const trimmed = icon.trim()
  if (!trimmed)
    return ''

  if (trimmed.startsWith('mdi:'))
    return `mdi-${trimmed.slice(4)}`

  if (trimmed.startsWith('icon--')) {
    const match = /^icon--([^\s]+?)--(.+)$/.exec(trimmed)
    if (match)
      return `${match[1]}-${match[2]}`
  }

  if (trimmed.includes(':')) {
    const [prefix, name] = trimmed.split(':', 2)
    if (prefix && name)
      return `${prefix}-${name}`
  }

  return trimmed
}

const aliases = {
  calendar: 'tabler-calendar',
  collapse: 'tabler-chevron-up',
  complete: 'tabler-check',
  cancel: 'tabler-x',
  close: 'tabler-x',
  delete: 'tabler-circle-x-filled',
  clear: 'tabler-circle-x',
  success: 'tabler-circle-check',
  info: 'tabler-info-circle',
  warning: 'tabler-alert-triangle',
  error: 'tabler-alert-circle',
  prev: 'tabler-chevron-left',
  ratingEmpty: 'tabler-star',
  ratingFull: 'tabler-star-filled',
  ratingHalf: 'tabler-star-half-filled',
  next: 'tabler-chevron-right',
  delimiter: 'tabler-circle',
  sort: 'tabler-arrow-up',
  expand: 'tabler-chevron-down',
  menu: 'tabler-menu-2',
  subgroup: 'tabler-caret-down',
  dropdown: 'tabler-chevron-down',
  edit: 'tabler-pencil',
  loading: 'tabler-refresh',
  first: 'tabler-player-skip-back',
  last: 'tabler-player-skip-forward',
  unfold: 'tabler-arrows-move-vertical',
  file: 'tabler-paperclip',
  plus: 'tabler-plus',
  minus: 'tabler-minus',
  sortAsc: 'tabler-arrow-up',
  sortDesc: 'tabler-arrow-down',
  play: 'tabler-player-play',
  pause: 'tabler-player-pause',
  fullscreen: 'tabler-maximize',
  fullscreenExit: 'tabler-minimize',
  volumeHigh: 'tabler-volume',
  volumeMedium: 'tabler-volume-2',
  volumeLow: 'tabler-volume-2',
  volumeOff: 'tabler-volume-off',
  tableGroupExpand: 'tabler-chevron-right',
  tableGroupCollapse: 'tabler-chevron-down',
}

export const iconify = {
  component: (props: any) => {
    // Load custom SVG directly instead of going through icon component
    if (typeof props.icon === 'string') {
      const normalizedIconName = normalizeIconName(props.icon)
      const iconComponent = customIcons[normalizedIconName]

      if (iconComponent)
        return h(iconComponent)

      const iconClasses = normalizedIconName.startsWith('mdi-')
        ? ['mdi', normalizedIconName]
        : normalizedIconName

      return h(
        props.tag,
        {
          ...props,
          class: [props.class, iconClasses],

          // Remove used props from DOM rendering
          tag: undefined,
          icon: undefined,
        },
      )
    }

    return h(
      props.tag,
      {
        ...props,

        // Remove used props from DOM rendering
        tag: undefined,
        icon: undefined,
      },
    )
  },
}

export const icons = {
  defaultSet: 'iconify',
  aliases,
  sets: {
    iconify,
  },
}
