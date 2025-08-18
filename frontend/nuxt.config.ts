// nuxt.config.ts - VERSI DISEMPURNAKAN

import { resolve } from 'node:path'
import vuetifyPlugin from 'vite-plugin-vuetify'
import svgLoader from 'vite-svg-loader'

const host = process.env.NUXT_HOST ?? '0.0.0.0'
const port = Number(process.env.NUXT_PORT ?? '3000')

const allowedHosts = (process.env.NUXT_DEV_ALLOWED_HOSTS ?? '')
  .split(',')
  .map(h => h.trim().replace(/^https?:\/\//, ''))
  .filter(Boolean)

// Determine HMR configuration based on environment
function getHmrConfig() {
  if (process.env.NODE_ENV !== 'development' || process.env.DISABLE_HMR === 'true') {
    return false
  }

  // If we have explicit HMR configuration from environment
  if (process.env.NUXT_HMR_HOST && process.env.NUXT_HMR_PORT) {
    return {
      protocol: process.env.NUXT_HMR_PROTOCOL === 'wss' ? 'wss' : 'ws',
      host: process.env.NUXT_HMR_HOST,
      port: Number(process.env.NUXT_HMR_PORT),
      clientPort: Number(process.env.NUXT_HMR_PORT),
    }
  }

  // Check if we're likely in a Docker + proxy setup
  const isProxiedSetup = allowedHosts.includes('dev.sobigidul.com')

  if (isProxiedSetup) {
    // For Docker + HTTPS proxy setup, try to use the proxy for HMR too
    return {
      protocol: 'wss',
      host: 'dev.sobigidul.com',
      port: 443,
      clientPort: 443,
    }
  }

  // Default local development
  return {
    protocol: 'ws',
    host: 'localhost',
    port: Number(port) + 1000,
    clientPort: Number(port) + 1000,
  }
}

export default defineNuxtConfig({
  // [PENYEMPURNAAN] Menggunakan tanggal saat ini. Menjamin kompatibilitas dengan fitur stabil terbaru.
  // Hindari menggunakan tanggal di masa depan kecuali Anda secara spesifik ingin menguji fitur yang akan datang.
  compatibilityDate: '2025-07-24',

  // [OPTIMIZED FOR LOCAL NETWORK HOTSPOT] Nuxt 4 Edition
  // SPA mode untuk kecepatan maksimal pada jaringan lokal
  // Tidak perlu SEO karena ini aplikasi internal/offline
  ssr: false,

  // [TAMBAHAN OPTIMASI SPA]
  // Optimasi khusus untuk mengatasi network timeout di local hotspot
  nitro: {
    preset: 'static',
    prerender: {
      crawlLinks: false, // Disable crawling untuk SPA
      routes: ['/'], // Hanya prerender halaman utama
    },
    // Optimasi untuk local network
    minify: process.env.NODE_ENV === 'production',
    compressPublicAssets: false, // Disable compression untuk local network speed
  },

  // [PENYEMPURNAAN] Mode debug hanya aktif saat development, dan nonaktif saat produksi untuk keamanan.
  debug: process.env.NODE_ENV === 'development',

  devServer: {
    host,
    port,
    https: process.env.NUXT_DEV_HTTPS === 'true'
      ? {
        key: process.env.NUXT_SSL_KEY || '.ssl/key.pem',
        cert: process.env.NUXT_SSL_CERT || '.ssl/cert.pem',
      }
      : false,
  },

  app: {
    head: {
      titleTemplate: '%s - Portal Hotspot',
      title: 'Portal Hotspot',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        // Cache control meta tags untuk mencegah browser caching
        { 'http-equiv': 'Cache-Control', 'content': 'no-cache, no-store, must-revalidate' },
        { 'http-equiv': 'Pragma', 'content': 'no-cache' },
        { 'http-equiv': 'Expires', 'content': '0' },
        // Tambahan untuk mobile browsers
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'mobile-web-app-capable', content: 'yes' },
      ],
      link: [
        {
          rel: 'icon',
          type: 'image/png',
          href: `${process.env.NUXT_APP_BASE_URL ?? ''}/favicon.png`,
        },
        // Don't preload favicon - causes warning in captive browsers
      ],
      // [PERBAIKAN KRUSIAL] Mencegah 'Flash of Unstyled Content' (FOUC).
      // Aturan CSS ini memastikan <body> memiliki background gelap sejak render pertama oleh browser,
      // bahkan sebelum file JavaScript (Vue/Vite) selesai dimuat dan dieksekusi.
      style: [
        {
          innerHTML: `
            body { 
              background-color: #2F3349; 
              margin: 0; 
              padding: 0; 
              min-height: 100vh;
              overflow: hidden; /* Hide scrollbar during initial load */
              scrollbar-width: none; /* Firefox */
              -ms-overflow-style: none; /* IE and Edge */
            }
            body::-webkit-scrollbar {
              display: none; /* Chrome, Safari and Opera */
            }
            .loader-overlay {
              position: fixed;
              top: 0;
              left: 0;
              width: 100%;
              height: 100%;
              background-color: #2F3349;
              display: flex;
              justify-content: center;
              align-items: center;
              z-index: 9999;
              transition: opacity 0.5s ease-out;
            }
            .s-loader {
              width: 100px;
              height: 100px;
              overflow: visible;
            }
            .s-path-base {
              fill: #4A4A61;
            }
            .s-path-animated-fill {
              fill: url(#fill-gradient);
            }
            .mask-path {
              fill: none;
              stroke: white;
              stroke-width: 15;
              stroke-linecap: round;
              stroke-dasharray: 244;
              stroke-dashoffset: 244;
              animation: fill-and-erase 4s ease-in-out infinite;
            }
            @keyframes fill-and-erase {
              0% { stroke-dashoffset: 244; }
              40% { stroke-dashoffset: 0; }
              60% { stroke-dashoffset: 0; }
              100% { stroke-dashoffset: -244; }
            }
          `,
        },
      ],
      script: [
        {
          innerHTML: `
            window.addEventListener('DOMContentLoaded', function() {
              // Buat initial loader dengan gaya baru
              var loader = document.createElement('div');
              loader.className = 'loader-overlay';
              loader.innerHTML = \`
                <svg class="s-loader" viewBox="0 12.65 40.4 35" xmlns="http://www.w3.org/2000/svg">
                  <defs>
                    <linearGradient id="fill-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stop-color="#FFC1CC" />
                      <stop offset="100%" stop-color="#A2D2FF" />
                    </linearGradient>
                    <mask id="s-fill-mask">
                      <rect x="0" y="0" width="100%" height="100%" fill="black" />
                      <path
                        class="mask-path"
                        fill="none"
                        d="M40.40 37.65Q40.40 40.40 39.05 42.67Q37.70 44.95 35.45 46.30Q33.20 47.65 30.40 47.65L0 47.65L0 42.65L30.40 42.65Q32.50 42.65 33.95 41.17Q35.40 39.70 35.40 37.65Q35.40 35.60 33.95 34.13Q32.50 32.65 30.40 32.65L10 32.65Q7.25 32.65 4.98 31.30Q2.70 29.95 1.35 27.67Q0 25.40 0 22.65Q0 19.90 1.35 17.62Q2.70 15.35 4.98 14Q7.25 12.65 10 12.65L37.90 12.65L37.90 17.65L10 17.65Q7.95 17.65 6.48 19.12Q5 20.60 5 22.65Q5 24.70 6.48 26.17Q7.95 27.65 10 27.65L30.40 27.65Q33.20 27.65 35.45 29.00Q37.70 30.35 39.05 32.63Q40.40 34.90 40.40 37.65Z"
                      />
                    </mask>
                  </defs>
                  <path
                    class="s-path-base"
                    d="M40.40 37.65Q40.40 40.40 39.05 42.67Q37.70 44.95 35.45 46.30Q33.20 47.65 30.40 47.65L0 47.65L0 42.65L30.40 42.65Q32.50 42.65 33.95 41.17Q35.40 39.70 35.40 37.65Q35.40 35.60 33.95 34.13Q32.50 32.65 30.40 32.65L10 32.65Q7.25 32.65 4.98 31.30Q2.70 29.95 1.35 27.67Q0 25.40 0 22.65Q0 19.90 1.35 17.62Q2.70 15.35 4.98 14Q7.25 12.65 10 12.65L37.90 12.65L37.90 17.65L10 17.65Q7.95 17.65 6.48 19.12Q5 20.60 5 22.65Q5 24.70 6.48 26.17Q7.95 27.65 10 27.65L30.40 27.65Q33.20 27.65 35.45 29.00Q37.70 30.35 39.05 32.63Q40.40 34.90 40.40 37.65Z"
                  />
                  <path
                    class="s-path-animated-fill"
                    mask="url(#s-fill-mask)"
                    d="M40.40 37.65Q40.40 40.40 39.05 42.67Q37.70 44.95 35.45 46.30Q33.20 47.65 30.40 47.65L0 47.65L0 42.65L30.40 42.65Q32.50 42.65 33.95 41.17Q35.40 39.70 35.40 37.65Q35.40 35.60 33.95 34.13Q32.50 32.65 30.40 32.65L10 32.65Q7.25 32.65 4.98 31.30Q2.70 29.95 1.35 27.67Q0 25.40 0 22.65Q0 19.90 1.35 17.62Q2.70 15.35 4.98 14Q7.25 12.65 10 12.65L37.90 12.65L37.90 17.65L10 17.65Q7.95 17.65 6.48 19.12Q5 20.60 5 22.65Q5 24.70 6.48 26.17Q7.95 27.65 10 27.65L30.40 27.65Q33.20 27.65 35.45 29.00Q37.70 30.35 39.05 32.63Q40.40 34.90 40.40 37.65Z"
                  />
                </svg>
              \`;
              document.body.appendChild(loader);
              
            window.hideInitialLoader = function() {
                var loaderEl = document.querySelector('.loader-overlay');
                if (loaderEl) {
                  loaderEl.style.opacity = '0';
                  setTimeout(function() {
                    loaderEl.remove();
                    // Restore scrollbar after loader is completely removed
                    document.body.style.overflow = '';
                  }, 500);
                }
              };
            });
          `,
          type: 'text/javascript',
        },
      ],
    },
    rootId: '__nuxt',
    pageTransition: { name: 'page', mode: 'out-in' },
  },

  css: [
    '@/assets/styles/styles.scss',
    '@/assets/css/fonts.css',
    '@core/scss/template/index.scss',
    '@core/scss/template/libs/vuetify/index.scss',
  ],

  // [OPTIMASI SPA] Konfigurasi khusus untuk mengatasi loading issues
  spaLoadingTemplate: false, // Disable default loading template untuk custom loader

  components: {
    dirs: [
      { path: '~/components', pathPrefix: false },
      { path: '@core/components', pathPrefix: false },
    ],
  },

  alias: {
    '@themeConfig': resolve(__dirname, './themeConfig.ts'),
    '@core': resolve(__dirname, './@core'),
    '@layouts': resolve(__dirname, './@layouts'),
    '@images': resolve(__dirname, './assets/images'),
    '@styles': resolve(__dirname, './assets/styles'),
    '@configured-variables': resolve(__dirname, './assets/styles/variables/_template.scss'),
    '@validators': resolve(__dirname, './@core/utils/validators'),
  },

  typescript: {
    strict: true,
    shim: false,
    tsConfig: { exclude: ['node_modules', '.output', '.nuxt', 'dist'] },
  },

  vite: {
    plugins: [
      svgLoader(),
      vuetifyPlugin({
        styles: {
          configFile: 'assets/styles/variables/_vuetify.scss',
        },
      }),
    ],
    optimizeDeps: {
      include: [
        // Core dependencies
        'apexcharts',
        'vue3-apexcharts',
        'vue',
        'vue-router',
        '@vueuse/core',
        'date-fns',
        'date-fns/locale',
        // Authorization & permissions
        '@casl/ability',
        '@casl/vue',
        // UI & UX dependencies
        'webfontloader',
        '@floating-ui/dom',
        'vue3-perfect-scrollbar',
        // Additional common dependencies
        'pinia',
        '@vueuse/nuxt',
      ],
      exclude: ['vuetify'],
      force: false, // Changed to false untuk cache dependencies yang sudah dioptimasi
      entries: [
        // Pre-scan entry points untuk optimasi yang lebih baik
        './app.vue',
        './pages/**/*.vue',
        './components/**/*.vue',
      ],
    },
    build: {
      chunkSizeWarningLimit: 1600,
      // Optimasi agresif untuk jaringan lokal
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['vue', 'vue-router', '@vueuse/core'],
            vuetify: ['vuetify'],
            charts: ['apexcharts', 'vue3-apexcharts'],
            utils: ['date-fns'],
          },
        },
      },
      // Optimasi untuk SPA loading
      minify: process.env.NODE_ENV === 'production' ? 'esbuild' : false,
      target: 'esnext',
      cssMinify: true,
    },
    // Konfigurasi untuk jaringan lokal yang cepat
    server: {
      allowedHosts,
      // Intelligent HMR configuration based on environment
      hmr: getHmrConfig(),
      // Tambahan optimasi untuk local network
      cors: true,
      headers: {
        'Cache-Control': 'max-age=31536000',
      },
      // Warm up untuk dependencies yang sering digunakan
      warmup: {
        clientFiles: [
          './app.vue',
          './layouts/**/*.vue',
          './pages/**/*.vue',
          './components/**/*.vue',
        ],
      },
    },
    // CSS inline untuk menghindari network request
    css: {
      preprocessorOptions: {
        scss: {
          // Fix SASS @use/@import order issue
          additionalData: '@use "@configured-variables" as *;',
        },
      },
    },
  },

  build: { transpile: ['vuetify', '@iconify/vue'] },

  modules: [
    '@vueuse/nuxt',
    '@nuxtjs/device',
    '@pinia/nuxt',
    'pinia-plugin-persistedstate/nuxt',
  ],

  runtimeConfig: {
    internalApiBaseUrl: process.env.NUXT_INTERNAL_API_BASE_URL,
    public: {
      apiBaseUrl: process.env.NUXT_PUBLIC_API_BASE_URL ?? '/api',
      midtransClientKey: process.env.NUXT_PUBLIC_MIDTRANS_CLIENT_KEY ?? '',
      midtransEnv: process.env.NUXT_PUBLIC_MIDTRANS_ENV ?? 'sandbox',
      mapboxAccessToken: process.env.MAPBOX_ACCESS_TOKEN ?? '',
      mikrotikLoginUrl: process.env.NUXT_PUBLIC_MIKROTIK_LOGIN_URL ?? 'http://dev.login.sobigidul.com',
      profileAktifName: process.env.NUXT_PUBLIC_MIKROTIK_PROFILE_AKTIF ?? 'profile-aktif',
      profileUnlimitedName: process.env.NUXT_PUBLIC_MIKROTIK_PROFILE_UNLIMITED ?? 'profile-unlimited',
      profileInactiveName: process.env.NUXT_PUBLIC_MIKROTIK_PROFILE_INACTIVE ?? 'inactive',
      profileFupName: process.env.NUXT_PUBLIC_MIKROTIK_PROFILE_FUP ?? 'profile-fup',
      profileHabisName: process.env.NUXT_PUBLIC_MIKROTIK_PROFILE_HABIS ?? 'profile-habis',
      profileBlokirName: process.env.NUXT_PUBLIC_MIKROTIK_PROFILE_BLOKIR ?? 'profile-blokir',
    },
  },

  routeRules: {
    // API proxy
    '/api/**': {
      proxy: `${process.env.NUXT_INTERNAL_API_BASE_URL}/**`,
    },

    // ===== OPTIMIZED FOR LOCAL NETWORK HOTSPOT =====
    // Semua halaman sebagai SPA untuk kecepatan maksimal di jaringan lokal
    // Tidak perlu SEO karena ini aplikasi internal/offline

    // Static assets caching untuk mengurangi network requests
    '/_nuxt/**': {
      headers: {
        'Cache-Control': 'max-age=31536000, immutable',
      },
    },

    // CSS dan JS files dengan aggressive caching
    '/**/*.css': {
      headers: {
        'Cache-Control': 'max-age=31536000, immutable',
      },
    },
    '/**/*.js': {
      headers: {
        'Cache-Control': 'max-age=31536000, immutable',
      },
    },

    // SPA fallback untuk semua routes dengan aggressive no-cache
    '/**': {
      isr: false,
      prerender: false,
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    },

    // Specific no-cache untuk halaman auth dan detection
    '/login/**': {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    },
    '/register/**': {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    },
    '/admin/**': {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    },
  },

  experimental: {
    typedPages: true,
    payloadExtraction: false,
    // Nuxt 4 optimizations untuk jaringan lokal
    asyncContext: true,
    componentIslands: false, // Disable untuk performance di local network
    writeEarlyHints: false, // Tidak perlu untuk local network
    // Nuxt 4 specific optimizations
    scanPageMeta: 'after-resolve', // Faster page loading untuk local network
    appManifest: false, // Tidak perlu untuk local app
    // Tambahan optimasi SPA
    crossOriginPrefetch: false, // Disable untuk local network
    viewTransition: false, // Disable view transitions untuk stability
    headNext: true, // Enable optimized head management
  },
  sourcemap: { server: false, client: false }, // Disable sourcemap untuk production performance
  devtools: { enabled: false },
})
