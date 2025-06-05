// frontend/@core/utils/vuetify.ts
import type { LiteralUnion } from 'type-fest'
import type { ThemeDefinition } from 'vuetify'
// Pastikan cookieRef diimpor dari lokasi yang benar sesuai struktur Vuexy Anda
// Jika @layouts/stores/config adalah alias yang benar dan mengekspor cookieRef
import { cookieRef } from '@layouts/stores/config' // Verifikasi path dan ekspor ini!
// Impor usePreferredDark jika belum ada (biasanya dari @vueuse/core)
import { usePreferredDark } from '@vueuse/core'

// --- PLACEHOLDER: Anda HARUS mengganti ini dengan konfigurasi tema Vuexy yang sebenarnya ---
export const themes: Record<string, ThemeDefinition> = {
  light: {
    dark: false,
    colors: {
      primary: '#673AB7', // Contoh dari plugin Anda
      secondary: '#00BCD4', // Contoh dari plugin Anda
      accent: '#FF4081',
      error: '#F44336',
      info: '#2196F3',
      success: '#4CAF50',
      warning: '#FFC107',
      // Tambahkan warna spesifik Vuexy lainnya di sini
      // 'on-background': '#...',
      // 'on-surface': '#...',
      // 'grey-50': '#...',
      // ...etc
    },
    variables: {
      // Variabel SCSS yang ingin Anda ekspos ke JS jika perlu
      // 'border-color': '#...',
      // ...etc
    },
  },
  dark: {
    dark: true,
    colors: {
      primary: '#7E57C2', // Contoh dari plugin Anda
      secondary: '#26C6DA', // Contoh dari plugin Anda
      // Tambahkan warna spesifik Vuexy lainnya di sini
      // 'on-background': '#...',
      // 'on-surface': '#...',
      // ...etc
    },
    variables: {
      // Variabel SCSS yang ingin Anda ekspos ke JS jika perlu
      // 'border-color': '#...',
      // ...etc
    },
  },
}

// --- PLACEHOLDER: Anda HARUS mengganti ini dengan konfigurasi default komponen Vuexy yang sebenarnya ---
export const defaults: Record<string, any> = {
  VAlert: {
    density: 'comfortable',
    variant: 'tonal',
  },
  VBtn: {
    // Contoh: variant: 'flat',
    // density: 'comfortable',
  },
  VTextField: {
    // Contoh: variant: 'outlined',
    // density: 'comfortable',
  },
  // Tambahkan default komponen Vuexy lainnya di sini
}
// --- Akhir Placeholder ---

export function resolveVuetifyTheme(defaultTheme: LiteralUnion<'light' | 'dark' | 'system', string>): 'light' | 'dark' {
  // usePreferredDark harus diimpor dan digunakan dengan benar
  const isDarkPreferred = usePreferredDark() // Ini adalah ref, jadi .value untuk mendapatkan boolean
  const cookieColorScheme = cookieRef<'light' | 'dark'>('color-scheme', isDarkPreferred.value ? 'dark' : 'light')
  const storedTheme = cookieRef('theme', defaultTheme).value

  if (storedTheme === 'system') {
    return cookieColorScheme.value === 'dark' ? 'dark' : 'light'
  }

  return storedTheme as 'light' | 'dark'
}

// Pastikan cookieRef dan usePreferredDark diimpor dan berfungsi dengan benar.
// Jika cookieRef berasal dari @layouts/stores/config, pastikan file itu ada dan mengekspornya.
// Jika tidak, Anda mungkin perlu menggunakan implementasi cookieRef yang berbeda (misalnya dari @vueuse/nuxt).
