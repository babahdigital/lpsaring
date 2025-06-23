import antfu from '@antfu/eslint-config'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import nPlugin from 'eslint-plugin-n'
import globalsPkg from 'globals'

const { browser, node } = globalsPkg

export default antfu(
  {
    vue: true,
    typescript: true,
    plugins: {
      '@typescript-eslint': tsPlugin,
      'n': nPlugin,
    },
    languageOptions: {
      globals: {
        ...browser,
        ...node,
        process: true,
      },
    },
    rules: {
      // --- TAMBAHKAN ATURAN BARU DI SINI ---
      'vue/v-slot-style': [
        'error',
        {
          atComponent: 'shorthand',
          default: 'shorthand',
          named: 'shorthand',
        },
      ],
      // --- AKHIR ATURAN BARU ---

      'n/prefer-global/process': 'off',
      '@typescript-eslint/no-redeclare': 'error',
      'ts/no-redeclare': 'off',
      'no-console': ['warn', { allow: ['info', 'log', 'warn', 'error'] }],
    },
    overrides: [
      // Aturan khusus untuk file TypeScript/Vue
      {
        files: ['**/*.{ts,tsx,vue}'],
        rules: {
          'ts/strict-boolean-expressions': [
            'error',
            {
              allowString: true,
              allowNumber: true,
              allowNullableObject: true,
            },
          ],
          'unused-imports/no-unused-vars': [
            'error',
            {
              vars: 'all',
              varsIgnorePattern: '^_',
              args: 'after-used',
              argsIgnorePattern: '^_',
              ignoreRestSiblings: true,
              destructuredArrayIgnorePattern: '^_',
            },
          ],
          'no-console': ['warn', { allow: ['info', 'log', 'warn', 'error'] }],
        },
      },
      // Aturan khusus untuk file konfigurasi
      {
        files: ['*.config.*'],
        rules: {
          'ts/no-var-requires': 'off',
          'no-console': 'off',
        },
      },
      // Nonaktifkan aturan TypeScript untuk file JSON
      {
        files: ['**/*.json'],
        rules: {
          'ts/*': 'off',
          '@typescript-eslint/*': 'off',
        },
      },
    ],
    ignores: [
      '**/migrations/**',
      'public/build/**',
      '.nuxt',
      'dist',
      'node_modules',
    ],
  },
)
