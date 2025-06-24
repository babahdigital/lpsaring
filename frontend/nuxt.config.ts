// frontend/nuxt.config.ts

import { fileURLToPath, URL } from 'node:url'
import vuetify from 'vite-plugin-vuetify'
import svgLoader from 'vite-svg-loader'

// Helper untuk path
const srcDir = fileURLToPath(new URL('.', import.meta.url))

// Log environment variables untuk debugging
console.log('Proxy Target:', process.env.NUXT_INTERNAL_API_BASE_URL)
console.log('Public API URL:', process.env.NUXT_PUBLIC_API_BASE_URL)

const host = process.env.NUXT_HOST ?? 'localhost'
const port = Number.parseInt(process.env.NUXT_PORT ?? '3010', 10)

export default defineNuxtConfig({
  compatibilityDate: '2025-04-23',
  ssr: true,
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
        href: `${process.env.NUXT_APP_BASE_URL ?? ''}/favicon.ico`,
      }],
    },
  },

  devtools: {
    enabled: true,
  },

  css: [
    '@core/scss/template/index.scss',
    '@/assets/styles/styles.scss',
    '@/plugins/iconify/icons.css',
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
    '~/plugins/apexcharts.client.ts',
    '~/plugins/midtrans.client.ts',
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
  },

  sourcemap: {
    server: true,
    client: true,
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
    plugins: [
      svgLoader(),
      vuetify({
        styles: { configFile: 'assets/styles/variables/_vuetify.scss' },
      }),
    ],
    server: {
      hmr: {
        protocol: 'ws',
        host,
        port,
      },
    },
  },

  build: {
    transpile: ['vuetify', '@iconify/vue'],
  },

  modules: [
    '@vueuse/nuxt',
    '@nuxtjs/device',
    '@pinia/nuxt',
    '@nuxt/devtools',
  ],

  runtimeConfig: {
    fonnteToken: '',
    public: {
      apiBaseUrl: process.env.NUXT_PUBLIC_API_BASE_URL ?? '/api',
      midtransClientKey: process.env.NUXT_PUBLIC_MIDTRANS_CLIENT_KEY ?? '',
      midtransEnv: process.env.NUXT_PUBLIC_MIDTRANS_ENV ?? 'sandbox',
      mapboxAccessToken: process.env.MAPBOX_ACCESS_TOKEN ?? '',
    },
    internalApiBaseUrl: process.env.NUXT_INTERNAL_API_BASE_URL ?? 'http://backend:5010/api',
  },

  nitro: {
    devProxy: {
      '/api': {
        target: process.env.NUXT_INTERNAL_API_BASE_URL ?? 'http://backend:5010/api',
        changeOrigin: true,
        headers: {
          Connection: 'keep-alive',
        },
      },
    },
  },
})
