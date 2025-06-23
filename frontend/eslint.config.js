import antfu from '@antfu/eslint-config'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import nPlugin from 'eslint-plugin-n'
import globalsPkg from 'globals'

const { browser, node } = globalsPkg

export default antfu(
  // Objek Konfigurasi Utama
  {
    vue: true,
    typescript: true,
    ignores: [
      '**/migrations/**',
      'public/build/**',
      '.nuxt',
      'dist',
      'node_modules',
    ],
    languageOptions: {
      globals: {
        ...browser,
        ...node,
        process: true,
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'n': nPlugin,
    },
    rules: {
      'vue/v-slot-style': [
        'error',
        {
          atComponent: 'shorthand',
          default: 'shorthand',
          named: 'shorthand',
        },
      ],
      'n/prefer-global/process': 'off',
      '@typescript-eslint/no-redeclare': 'error',
      'ts/no-redeclare': 'off',
      'no-console': ['warn', { allow: ['info', 'log', 'warn', 'error'] }],
    },
  },

  // Objek Konfigurasi Terpisah untuk Override File Vue/TypeScript
  {
    files: ['**/*.{ts,tsx,vue}'],
    rules: {
      'vue/valid-v-slot': ['error', {
        allowModifiers: true,
      }],
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

  // Objek Konfigurasi Terpisah untuk Override File Konfigurasi
  {
    files: ['*.config.*'],
    rules: {
      'ts/no-var-requires': 'off',
      'no-console': 'off',
    },
  },

  // Objek Konfigurasi Terpisah untuk Override File JSON
  {
    files: ['**/*.json'],
    rules: {
      'ts/*': 'off',
      '@typescript-eslint/*': 'off',
    },
  },
)