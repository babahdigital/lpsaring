// frontend/nuxt.config.ts

import { defineNuxtConfig } from 'nuxt/config'
import { fileURLToPath, URL } from 'node:url'
import vuetify from 'vite-plugin-vuetify'
import svgLoader from 'vite-svg-loader'

// Helper untuk path
const srcDir = fileURLToPath(new URL('.', import.meta.url))

const normalizeUrl = (value: string) => value.replace(/\/+$/, '')
const ensureApiSuffix = (value: string) => (normalizeUrl(value).endsWith('/api') ? normalizeUrl(value) : `${normalizeUrl(value)}/api`)

const publicApiBaseUrl = process.env.NUXT_PUBLIC_API_BASE_URL ?? '/api'
const appBaseUrl = process.env.NUXT_PUBLIC_APP_BASE_URL ?? ''
const externalBaseUrl = process.env.NUXT_PUBLIC_EXTERNAL_BASE_URL ?? appBaseUrl
const adminWhatsapp = process.env.NUXT_PUBLIC_ADMIN_WHATSAPP ?? ''
const whatsappBaseUrl = process.env.NUXT_PUBLIC_WHATSAPP_BASE_URL ?? ''
const merchantName = process.env.NUXT_PUBLIC_MERCHANT_NAME ?? 'Babah Digital'
const merchantLogo = process.env.NUXT_PUBLIC_MERCHANT_LOGO ?? merchantName
const merchantBusinessType = process.env.NUXT_PUBLIC_MERCHANT_BUSINESS_TYPE ?? 'Jasa Telekomunikasi / ISP (Produk Digital)'
const merchantAddress = process.env.NUXT_PUBLIC_MERCHANT_ADDRESS ?? ''
const merchantSupportEmail = process.env.NUXT_PUBLIC_MERCHANT_SUPPORT_EMAIL ?? ''
const merchantSupportWhatsapp = process.env.NUXT_PUBLIC_MERCHANT_SUPPORT_WHATSAPP ?? adminWhatsapp
const demoModeEnabled = process.env.NUXT_PUBLIC_DEMO_MODE_ENABLED ?? 'false'
const captiveSuccessRedirectUrl = process.env.NUXT_PUBLIC_CAPTIVE_SUCCESS_REDIRECT_URL ?? appBaseUrl ?? ''
const midtransSnapUrlProduction = process.env.NUXT_PUBLIC_MIDTRANS_SNAP_URL_PRODUCTION ?? ''
const midtransSnapUrlSandbox = process.env.NUXT_PUBLIC_MIDTRANS_SNAP_URL_SANDBOX ?? ''
const buyNowUrl = process.env.NUXT_PUBLIC_BUY_NOW_URL ?? ''
const devBypassToken = process.env.NUXT_PUBLIC_DEV_BYPASS_TOKEN ?? ''
const statusPageGuardEnabled = process.env.NUXT_PUBLIC_STATUS_PAGE_GUARD_ENABLED ?? 'false'
const internalApiBaseUrl = ensureApiSuffix(process.env.NUXT_INTERNAL_API_BASE_URL ?? 'http://backend:5010')
const internalApiOrigin = normalizeUrl(internalApiBaseUrl).replace(/\/api$/, '')
const internalApiProxyTarget = `${internalApiOrigin}/api/**`
const internalApiDevProxyTarget = internalApiOrigin

// Log environment variables untuk debugging
console.log('Proxy Target:', internalApiBaseUrl)
console.log('Public API URL:', publicApiBaseUrl)

const host = process.env.NUXT_HOST ?? process.env.HOST ?? '0.0.0.0'
const port = Number.parseInt(process.env.NUXT_PORT ?? '3010', 10)

const defaultHmrHost = host === '0.0.0.0' ? 'localhost' : host

const viteHmrHost = process.env.VITE_HMR_HOST?.trim()
const viteHmrProtocol = (process.env.VITE_HMR_PROTOCOL as 'ws' | 'wss' | undefined)?.trim()
const viteHmrClientPortRaw = process.env.VITE_HMR_CLIENT_PORT
const viteHmrPortRaw = process.env.VITE_HMR_PORT
const viteHmrPath = process.env.VITE_HMR_PATH?.trim()

const viteHmrClientPort = viteHmrClientPortRaw ? Number.parseInt(viteHmrClientPortRaw, 10) : undefined
const viteHmrPort = viteHmrPortRaw ? Number.parseInt(viteHmrPortRaw, 10) : undefined

const hmrHost = process.env.NUXT_PUBLIC_HMR_HOST?.trim()
const hmrClientPortEnv = process.env.NUXT_PUBLIC_HMR_CLIENT_PORT
const hmrClientPort = hmrClientPortEnv ? Number.parseInt(hmrClientPortEnv, 10) : undefined
const hmrProtocol = process.env.NUXT_PUBLIC_HMR_PROTOCOL
  ?? ((hmrClientPort === 443) ? 'wss' : 'ws')
const isProductionBuild = process.env.NODE_ENV === 'production'

let derivedHmrHost = hmrHost
let derivedHmrProtocol = hmrProtocol
let derivedHmrClientPort = hmrClientPort
let appUrl: URL | undefined

if (appBaseUrl) {
  try {
    appUrl = new URL(appBaseUrl)
  }
  catch {
    // ignore invalid appBaseUrl
  }
}

// NOTE:
// Jangan otomatis men-derive HMR host dari APP base URL saat dev lokal.
// Jika APP_BASE_URL menunjuk domain https (mis. dev-lpsaring.*), Vite client akan mencoba connect
// ke wss://domain/_nuxt dan gagal jika websocket tidak diproxy.
// Untuk remote dev/HMR lewat domain, set env VITE_HMR_HOST / VITE_HMR_PROTOCOL / VITE_HMR_CLIENT_PORT.
if (isProductionBuild && appUrl && (!derivedHmrHost || !derivedHmrProtocol || !derivedHmrClientPort)) {
  if (!derivedHmrHost)
    derivedHmrHost = appUrl.hostname
  if (!derivedHmrProtocol)
    derivedHmrProtocol = appUrl.protocol === 'https:' ? 'wss' : 'ws'
  if (!derivedHmrClientPort) {
    const appPort = appUrl.port ? Number.parseInt(appUrl.port, 10) : undefined
    derivedHmrClientPort = appPort ?? (derivedHmrProtocol === 'wss' ? 443 : 80)
  }
}

if (!derivedHmrClientPort)
  derivedHmrClientPort = derivedHmrProtocol === 'wss' ? 443 : port

export default defineNuxtConfig({
  compatibilityDate: '2025-04-23',
  ssr: true,
  ignore: [
    '**/plugins/iconify/**',
  ],
  devServer: {
    port,
    host,
  },

  // Definisikan semua alias di sini sebagai "sumber kebenaran tunggal"
  // Nuxt akan otomatis menyinkronkan ini ke Vite dan tsconfig.
  alias: {
    '~': srcDir,
    '@': srcDir,
    '@themeConfig': fileURLToPath(new URL('./themeConfig.ts', import.meta.url)),
    '@core': fileURLToPath(new URL('./@core', import.meta.url)),
    '@layouts': fileURLToPath(new URL('./@layouts', import.meta.url)),
    '@images': fileURLToPath(new URL('./assets/images', import.meta.url)),
    '@styles': fileURLToPath(new URL('./assets/styles', import.meta.url)),
    '@configured-variables': fileURLToPath(new URL('./assets/styles/variables/_template.scss', import.meta.url)),
    '@validators': fileURLToPath(new URL('./@core/utils/validators', import.meta.url)),
  },

  app: {
    head: {
      titleTemplate: '%s - Portal Hotspot',
      title: 'Portal Hotspot',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      ],
      link: [{
        rel: 'icon',
        type: 'image/x-icon',
        href: `${appBaseUrl}/favicon.ico`,
      }],
    },
  },

  devtools: {
    enabled: process.env.NODE_ENV !== 'production',
  },

  css: [
    '@fontsource/public-sans/300.css',
    '@fontsource/public-sans/400.css',
    '@fontsource/public-sans/500.css',
    '@fontsource/public-sans/600.css',
    '@fontsource/public-sans/700.css',
    '@fontsource/public-sans/300-italic.css',
    '@fontsource/public-sans/400-italic.css',
    '@fontsource/public-sans/500-italic.css',
    '@fontsource/public-sans/600-italic.css',
    '@fontsource/public-sans/700-italic.css',
    '@core/scss/template/index.scss',
    '@/assets/styles/styles.scss',
    '@/assets/iconify/icons.css',
  ],

  components: {
    dirs: [
      { path: '@core/components', pathPrefix: false },
      { path: '~/components/global', global: true },
      { path: '~/components', pathPrefix: false },
    ],
  },

  plugins: [
    '~/plugins/vuetify',
    '~/plugins/api.ts',
  ],

  imports: {
    dirs: [
      'composables/**',
      'utils/**',
      'store/**',
      'types/**',
      '@core/composables/**',
      '@core/utils/**',
    ],
  },

  experimental: {
    typedPages: true,
    payloadExtraction: false,
  },

  // Blok typescript tidak lagi diperlukan karena alias sudah diatur di root
  typescript: {
    strict: true,
    tsConfig: {
      compilerOptions: {
        module: 'ESNext',
        types: ['vuetify-shims'],
        typeRoots: ['../types', '../node_modules/@types'],
      },
    },
  },

  sourcemap: {
    server: !isProductionBuild,
    client: !isProductionBuild,
  },

  vue: {
    compilerOptions: {},
  },

  vite: {
    define: {
      'process.env': {
        NODE_ENV: `"${process.env.NODE_ENV ?? 'development'}"`,
        NUXT_PUBLIC_MIDTRANS_CLIENT_KEY: `"${process.env.NUXT_PUBLIC_MIDTRANS_CLIENT_KEY ?? ''}"`,
        NUXT_PUBLIC_MIDTRANS_ENV: `"${process.env.NUXT_PUBLIC_MIDTRANS_ENV ?? 'sandbox'}"`,
      },
    },
    // resolve.alias tidak lagi diperlukan karena sudah diatur di root
    build: {
      chunkSizeWarningLimit: 1600,
    },
    optimizeDeps: {
      exclude: ['vuetify'],
      entries: ['./**/*.vue'],
    },
    server: {
      proxy: {
        '/api': {
          target: internalApiDevProxyTarget,
          changeOrigin: true,
        },
      },
      // IMPORTANT:
      // Jangan memaksa protocol `ws` secara default.
      // Jika dev diakses via HTTPS (mis. reverse proxy / Cloudflare), browser butuh `wss://`.
      // Dengan membiarkan HMR default, Vite akan meng-derive protocol dari `window.location`.
      // Untuk remote HMR yang butuh override host/clientPort, gunakan env VITE_HMR_*.
      hmr: (viteHmrHost && viteHmrHost.length > 0)
        ? {
            protocol: viteHmrProtocol || 'wss',
            host: viteHmrHost,
            clientPort: viteHmrClientPort || (viteHmrProtocol === 'ws' ? 80 : 443),
            // `port` adalah port websocket server yang listen. Jangan default ke 443 karena itu
            // akan membuat Vite mencoba bind port 443 dan gagal.
            port: viteHmrPort,
            path: viteHmrPath || '/_nuxt/',
          }
        : undefined,
    },
    plugins: [
      svgLoader(),
      vuetify({
        styles: { configFile: 'assets/styles/variables/_vuetify.scss' },
      }),
    ],
  },

  build: {
    transpile: ['vuetify', '@iconify/vue'],
  },

  routeRules: {
    '/admin/login': { redirect: '/admin' },
    '/admin/dasboard': { redirect: '/admin/dashboard' },
  },

  modules: [
    '@vueuse/nuxt',
    '@nuxtjs/device',
    '@pinia/nuxt',
    '@nuxt/devtools',
  ],

  runtimeConfig: {
    public: {
      apiBaseUrl: publicApiBaseUrl,
      appBaseUrl,
      externalBaseUrl,
      adminWhatsapp,
      whatsappBaseUrl,
      merchantName,
      merchantLogo,
      merchantBusinessType,
      merchantAddress,
      merchantSupportEmail,
      merchantSupportWhatsapp,
      demoModeEnabled,
      captiveSuccessRedirectUrl,
      midtransClientKey: process.env.NUXT_PUBLIC_MIDTRANS_CLIENT_KEY ?? '',
      midtransEnv: process.env.NUXT_PUBLIC_MIDTRANS_ENV ?? 'sandbox',
      midtransSnapUrlProduction,
      midtransSnapUrlSandbox,
      buyNowUrl,
      devBypassToken,
      statusPageGuardEnabled,
    },
    internalApiBaseUrl,
  },

  nitro: {
    devProxy: {
      '/api': {
        target: internalApiDevProxyTarget,
        changeOrigin: true,
        headers: {
          Connection: 'keep-alive',
        },
      },
    },
    routeRules: {
      '/api/**': {
        proxy: internalApiProxyTarget,
      },
    },
  },
});
