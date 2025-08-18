// eslint.config.js - VERSI FINAL DAN DIREKOMENDASIKAN

import antfu from '@antfu/eslint-config'

export default antfu(
  // Opsi utama untuk preset antfu.
  // Secara otomatis mengaktifkan aturan untuk Vue, TypeScript, dll.
  {
    vue: true,
    nuxt: true,
    typescript: true,

    // Folder dan file yang akan diabaikan oleh ESLint.
    ignores: [
      '.output',
      '.nuxt',
      'dist',
      'node_modules',
      'public/build/**',
      '**/migrations/**',
      // Documentation files with code blocks
      'guide/**',
      '.vscode-server/**',
      '**/README.md',
    ],
  },

  // Blok override untuk file-file spesifik.
  // Aturan di sini akan menimpa atau menambahkan aturan dari preset dasar.
  {
    files: ['**/*.{ts,tsx,vue}'],
    rules: {
      /* ---------- Penyesuaian proyek ---------- */
      /* 1. Ketatkan yg perlu, longgarkan sisanya */
      'vue/require-explicit-emits': 'warn',
      'vue/custom-event-name-casing': 'off',
      'style/max-statements-per-line': 'off',
      'ts/no-unused-expressions': 'off',
      '@typescript-eslint/no-redeclare': 'off', // Fix for VNodeRenderer.tsx
      'ts/no-redeclare': 'off',

      // Izinkan modifier pada v-slot
      'vue/valid-v-slot': ['error', { allowModifiers: true }],

      // Mengizinkan console.log, warn, dll. saat development, tapi memberi peringatan saat production.
      'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
      'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',

      // Aturan spesifik proyek Anda bisa ditambahkan di sini.
      // Contoh: menonaktifkan aturan yang terlalu ketat untuk proyek Anda.
      'unicorn/prefer-number-properties': 'off',
      'vue/no-required-prop-with-default': 'warn',

      // Mengubah aturan 'unused-vars' menjadi warning, bukan error.
      'unused-imports/no-unused-vars': ['warn', {
        vars: 'all',
        varsIgnorePattern: '^_',
        args: 'after-used',
        argsIgnorePattern: '^_',
        ignoreRestSiblings: true,
        caughtErrors: 'none', // Mengabaikan variabel error pada blok catch
      }],

      // Styling dan formatting rules - untuk hasil yang lebih bersih
      'style/no-trailing-spaces': 'error',
      'style/indent': ['error', 2],
      'style/quotes': ['error', 'single'],
      'style/semi': ['error', 'never'],

      // Import sorting untuk konsistensi
      'perfectionist/sort-imports': ['error', {
        type: 'alphabetical',
        order: 'asc',
        ignoreCase: true,
        newlinesBetween: 'always',
        groups: [
          'type',
          ['builtin', 'external'],
          'internal-type',
          'internal',
          ['parent-type', 'sibling-type', 'index-type'],
          ['parent', 'sibling', 'index'],
          'object',
          'unknown',
        ],
      }],

      // Vue attribute order untuk konsistensi
      'vue/attributes-order': ['warn', {
        order: [
          'DEFINITION',
          'LIST_RENDERING',
          'CONDITIONALS',
          'RENDER_MODIFIERS',
          'GLOBAL',
          ['UNIQUE', 'SLOT'],
          'TWO_WAY_BINDING',
          'OTHER_DIRECTIVES',
          'OTHER_ATTR',
          'EVENTS',
          'CONTENT',
        ],
        alphabetical: false,
      }],

      // Relax some overly strict rules for development
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/html-self-closing': ['error', {
        html: {
          void: 'always',
          normal: 'always',
          component: 'always',
        },
        svg: 'always',
        math: 'always',
      }],
    },
  },

  // Blok override untuk file-file konfigurasi (misal: nuxt.config.ts)
  {
    files: ['*.config.{js,ts}', 'plugins/**/*.ts'],
    rules: {
      // Mematikan aturan no-console untuk file konfigurasi
      'no-console': 'off',
      'node/prefer-global/process': 'off',
    },
  },
)
