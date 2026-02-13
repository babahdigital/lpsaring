import tsPlugin from '@typescript-eslint/eslint-plugin'
import tsParser from '@typescript-eslint/parser'
import importPlugin from 'eslint-plugin-import'
import promisePlugin from 'eslint-plugin-promise'
import sonarjs from 'eslint-plugin-sonarjs'
import casePolice from 'eslint-plugin-case-police'
import regexpPlugin from 'eslint-plugin-regexp'
import vuePlugin from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'
import globalsPkg from 'globals'

const { browser, node } = globalsPkg

export default [
  {
    ignores: [
      '**/migrations/**',
      'public/build/**',
      '.nuxt',
      'dist',
      '**/.pnpm-store/**',
      '**/*.json',
      '**/*.jsonc',
      '**/*.json5',
      'node_modules',
      'server/routes/.well-known/**',
    ],
  },
  {
    files: ['**/*.{js,jsx,ts,tsx,vue}'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        ecmaVersion: 'latest',
        sourceType: 'module',
        extraFileExtensions: ['.vue'],
        project: './.nuxt/tsconfig.json',
      },
      globals: {
        ...browser,
        ...node,
        process: true,
      },
    },
    plugins: {
      vue: vuePlugin,
      '@typescript-eslint': tsPlugin,
      import: importPlugin,
      promise: promisePlugin,
      sonarjs,
      'case-police': casePolice,
      regexp: regexpPlugin,
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
      'vue/valid-v-slot': ['error', { allowModifiers: true }],
      'vue/custom-event-name-casing': 'off',
      '@typescript-eslint/no-redeclare': 'error',
      'no-console': ['warn', { allow: ['info', 'log', 'warn', 'error'] }],
    },
  },
  {
    files: ['*.config.*'],
    rules: {
      'ts/no-var-requires': 'off',
      'no-console': 'off',
    },
  },
  {
    files: ['**/*.json'],
    rules: {
      'ts/*': 'off',
      '@typescript-eslint/*': 'off',
    },
  },
]
