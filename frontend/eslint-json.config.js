import jsoncParser from 'jsonc-eslint-parser'

export default {
  files: ['**/*.json'],
  languageOptions: {
    parser: jsoncParser,
  },
  rules: {
    // Aturan khusus untuk file JSON
    'jsonc/sort-keys': 'error',
    'jsonc/no-bigint-literals': 'error',
    'jsonc/no-dupe-keys': 'error',
  },
}
