import type { IconifyJSON } from '@iconify/types'
/**
 * This is an advanced example for creating icon bundles for Iconify SVG Framework.
 *
 * It creates a bundle from:
 * - All SVG files in a directory.
 * - Custom JSON files.
 * - Iconify icon sets.
 * - SVG framework.
 *
 * This example uses Iconify Tools to import and clean up icons.
 * For Iconify Tools documentation visit https://docs.iconify.design/tools/tools2/
 */
import { promises as fs } from 'node:fs'
import { createRequire } from 'node:module'

import { dirname, join } from 'node:path'
// Installation: npm install --save-dev @iconify/tools @iconify/utils @iconify/json @iconify/iconify
import { cleanupSVG, importDirectory, isEmptyColor, parseColors, runSVGO } from '@iconify/tools'
import { getIcons, getIconsCSS, stringToIcon } from '@iconify/utils'

// Create require function for ES modules
const require = createRequire(import.meta.url)

/**
 * Script configuration
 */
interface BundleScriptCustomSVGConfig {

  // Path to SVG files
  dir: string

  // True if icons should be treated as monotone: colors replaced with currentColor
  monotone: boolean

  // Icon set prefix
  prefix: string
}

interface BundleScriptCustomJSONConfig {

  // Path to JSON file
  filename: string

  // List of icons to import. If missing, all icons will be imported
  icons?: string[]
}

interface BundleScriptConfig {

  // Custom SVG to import and bundle
  svg?: BundleScriptCustomSVGConfig[]

  // Icons to bundled from @iconify/json packages
  icons?: string[]

  // List of JSON files to bundled
  // Entry can be a string, pointing to filename or a BundleScriptCustomJSONConfig object (see type above)
  // If entry is a string or object without 'icons' property, an entire JSON file will be bundled
  json?: (string | BundleScriptCustomJSONConfig)[]
}

const tablerIcons = [
  'adjustments-horizontal',
  'activity-heartbeat',
  'alarm',
  'alert-circle',
  'alert-circle-filled',
  'alert-octagon',
  'alert-triangle',
  'align-center',
  'align-justified',
  'align-left',
  'align-right',
  'archive',
  'arrow-bar-to-down',
  'arrow-down',
  'arrow-down-circle',
  'arrow-down-right',
  'arrow-left',
  'arrow-right',
  'arrows-move-vertical',
  'arrow-up',
  'arrow-up-circle',
  'ban',
  'battery',
  'bell',
  'bell-ringing',
  'bold',
  'bolt',
  'box',
  'brand-amazon',
  'brand-android',
  'brand-angular',
  'brand-apple',
  'brand-facebook',
  'brand-facebook-filled',
  'brand-firebase',
  'brand-github-filled',
  'brand-google-filled',
  'brand-html5',
  'brand-linkedin',
  'brand-linux',
  'brand-react-native',
  'brand-telegram',
  'brand-twitter',
  'brand-twitter-filled',
  'brand-vue',
  'brand-whatsapp',
  'brand-windows',
  'broadcast',
  'building',
  'building-bank',
  'building-community',
  'calendar',
  'calendar-check',
  'calendar-due',
  'calendar-exclamation',
  'calendar-off',
  'calendar-plus',
  'calendar-stats',
  'calendar-time',
  'calendar-today',
  'calendar-x',
  'caret-down',
  'cash',
  'chart-bar',
  'chart-bar-off',
  'chart-donut-3',
  'chart-infographic',
  'chart-pie',
  'chart-pie-off',
  'check',
  'checkbox',
  'checks',
  'checkup-list',
  'chevron-down',
  'chevron-left',
  'chevron-right',
  'chevrons-left',
  'chevrons-right',
  'chevron-up',
  'circle',
  'circle-check',
  'circle-dot',
  'circle-filled',
  'circle-x',
  'circle-x-filled',
  'clock',
  'clock-check',
  'clock-off',
  'code',
  'color-picker',
  'copy',
  'corner-down-left',
  'corner-left-down',
  'credit-card',
  'database',
  'database-export',
  'database-import',
  'database-off',
  'database-plus',
  'device-desktop',
  'device-desktop-analytics',
  'device-desktop-question',
  'device-floppy',
  'device-laptop',
  'device-mobile',
  'devices',
  'discount',
  'discount-check',
  'door',
  'dots-vertical',
  'download',
  'edit',
  'edit-circle',
  'error-404',
  'external-link',
  'eye',
  'eye-off',
  'file-alert',
  'file-dollar',
  'file-download',
  'file-invoice',
  'file-off',
  'file-text',
  'file-type-csv',
  'file-type-pdf',
  'filter',
  'filter-off',
  'gauge',
  'gift',
  'hash',
  'hand-stop',
  'help-circle',
  'history',
  'hourglass',
  'hourglass-high',
  'id',
  'id-badge-2',
  'infinity',
  'infinity-off',
  'info-circle',
  'info-triangle',
  'italic',
  'key',
  'key-off',
  'language',
  'layout-dashboard',
  'layout-grid-add',
  'link',
  'list-details',
  'loader-2',
  'lock',
  'lock-access',
  'login',
  'logout',
  'mail',
  'mail-check',
  'mail-fast',
  'mail-forward',
  'mail-off',
  'mail-opened',
  'mail-plus',
  'map-pin',
  'math-function',
  'maximize',
  'menu-2',
  'message',
  'minimize',
  'minus',
  'moon-stars',
  'network',
  'notes',
  'package',
  'package-off',
  'paperclip',
  'pencil',
  'phone',
  'player-pause',
  'player-play',
  'player-skip-back',
  'player-skip-forward',
  'plug-connected',
  'plug-connected-x',
  'plus',
  'printer',
  'question-mark',
  'qrcode',
  'receipt',
  'receipt-2',
  'refresh',
  'refresh-dot',
  'repeat',
  'reload',
  'robot',
  'router',
  'scan',
  'search',
  'send',
  'server',
  'server-2',
  'shield-exclamation',
  'settings',
  'settings-cog',
  'shield-check',
  'shield-lock',
  'shopping-cart',
  'shopping-cart-plus',
  'smart-home',
  'star',
  'star-filled',
  'star-half-filled',
  'strikethrough',
  'sun',
  'sun-high',
  'table',
  'tool',
  'trash',
  'truck',
  'typography',
  'underline',
  'upload',
  'user',
  'user-check',
  'user-circle',
  'user-cog',
  'user-edit',
  'user-exclamation',
  'user-off',
  'user-plus',
  'user-question',
  'users',
  'user-search',
  'users-group',
  'user-shield',
  'user-x',
  'volume',
  'volume-2',
  'volume-off',
  'wallet',
  'wifi',
  'x',
]

const sources: BundleScriptConfig = {

  svg: [
    // {
    //   dir: 'src/assets/images/iconify-svg',
    //   monotone: true,
    //   prefix: 'custom',
    // },

    // {
    //   dir: 'emojis',
    //   monotone: false,
    //   prefix: 'emoji',
    // },
  ],

  icons: [
    // 'mdi:home',
    // 'mdi:account',
    // 'mdi:login',
    // 'mdi:logout',
    // 'octicon:book-24',
    // 'octicon:code-square-24',
  ],

  json: [
    // Custom JSON file
    // 'json/gg.json',

    // Iconify JSON file (@iconify/json is a package name, /json/ is directory where files are, then filename)
    {
      filename: require.resolve('@iconify-json/tabler/icons.json'),
      icons: tablerIcons,
    },
    {
      filename: require.resolve('@iconify-json/mdi/icons.json'),
      icons: [
        'close-circle',
        'language-javascript',
        'language-typescript',
      ],
    },
    {
      filename: require.resolve('@iconify-json/fa/icons.json'),
      icons: [
        'circle',
      ],
    },

    // Custom file with only few icons
    // {
    //   filename: require.resolve('@iconify-json/line-md/icons.json'),
    //   icons: [
    //     'home-twotone-alt',
    //     'github',
    //     'document-list',
    //     'document-code',
    //     'image-twotone',
    //   ],
    // },
  ],
}

// File to save bundle to
const target = join(__dirname, '..', '..', 'assets', 'iconify', 'icons.css')

/**
 * Do stuff!
 */

;(async function () {
  // Create directory for output if missing
  const dir = dirname(target)
  try {
    await fs.mkdir(dir, {
      recursive: true,
    })
  }
  catch {
    //
  }

  const allIcons: IconifyJSON[] = []

  /**
   * Convert sources.icons to sources.json
   */
  if (sources.icons) {
    const sourcesJSON = sources.json ? sources.json : (sources.json = [])

    // Sort icons by prefix
    const organizedList = organizeIconsList(sources.icons)

    for (const prefix in organizedList) {
      const filename = require.resolve(`@iconify/json/json/${prefix}.json`)

      sourcesJSON.push({
        filename,
        icons: organizedList[prefix],
      })
    }
  }

  /**
   * Bundle JSON files and collect icons
   */
  if (sources.json) {
    for (let i = 0; i < sources.json.length; i++) {
      const item = sources.json[i]

      // Load icon set
      const filename = typeof item === 'string' ? item : item.filename
      const content = JSON.parse(await fs.readFile(filename, 'utf8')) as IconifyJSON

      for (const key in content) {
        if (key === 'prefix' && content.prefix === 'tabler') {
          for (const k in content.icons)
            content.icons[k].body = content.icons[k].body.replace(/stroke-width="2"/g, 'stroke-width="1.5"')
        }
      }

      // Filter icons
      if (typeof item !== 'string' && item.icons?.length) {
        const filteredContent = getIcons(content, item.icons)

        if (!filteredContent)
          throw new Error(`Cannot find required icons in ${filename}`)

        // Collect filtered icons
        allIcons.push(filteredContent)
      }
      else {
        // Collect all icons from the JSON file
        allIcons.push(content)
      }
    }
  }

  /**
   * Bundle custom SVG icons and collect icons
   */
  if (sources.svg) {
    for (let i = 0; i < sources.svg.length; i++) {
      const source = sources.svg[i]

      // Import icons
      const iconSet = await importDirectory(source.dir, {
        prefix: source.prefix,
      })

      // Validate, clean up, fix palette, etc.
      await iconSet.forEach(async (name, type) => {
        if (type !== 'icon')
          return

        // Get SVG instance for parsing
        const svg = iconSet.toSVG(name)

        if (!svg) {
          // Invalid icon
          iconSet.remove(name)

          return
        }

        // Clean up and optimise icons
        try {
          // Clean up icon code
          await cleanupSVG(svg)

          if (source.monotone) {
            // Replace color with currentColor, add if missing
            // If icon is not monotone, remove this code
            await parseColors(svg, {
              defaultColor: 'currentColor',
              callback: (attr, colorStr, color) => {
                return !color || isEmptyColor(color) ? colorStr : 'currentColor'
              },
            })
          }

          // Optimise
          await runSVGO(svg)
        }
        catch (err) {
          // Invalid icon
          console.error(`Error parsing ${name} from ${source.dir}:`, err)
          iconSet.remove(name)

          return
        }

        // Update icon from SVG instance
        iconSet.fromSVG(name, svg)
      })

      // Collect the SVG icon
      allIcons.push(iconSet.export())
    }
  }

  // Generate CSS from collected icons
  const cssContent = allIcons
    .map(iconSet => getIconsCSS(
      iconSet,
      Object.keys(iconSet.icons),
      {
        iconSelector: '.{prefix}-{name}',
        mode: 'mask',
      },
    ))
    .join('\n')

  // Save the CSS to a file
  await fs.writeFile(target, cssContent, 'utf8')

  console.log(`Saved CSS to ${target}!`)
})().catch((err) => {
  console.error(err)
  process.exitCode = 1
})

/**
 * Sort icon names by prefix
 */
function organizeIconsList(icons: string[]): Record<string, string[]> {
  const sorted: Record<string, string[]> = Object.create(null)

  icons.forEach((icon) => {
    const item = stringToIcon(icon)

    if (!item)
      return

    const prefix = item.prefix
    const prefixList = sorted[prefix] ? sorted[prefix] : (sorted[prefix] = [])
    const name = item.name

    if (!prefixList.includes(name))
      prefixList.push(name)
  })

  return sorted
}
