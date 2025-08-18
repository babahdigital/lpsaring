import { useConfigStore } from '@core/stores/config'
import { cookieRef, namespaceConfig } from '@layouts/stores/config'
import { themeConfig } from '@themeConfig'
import { useStorage } from '@vueuse/core'
import { useTheme } from 'vuetify'

function _syncAppRtl() {
  const configStore = useConfigStore()
  const storedLang = cookieRef<string | null>('language', null)

  // Since i18n is disabled, we'll skip the i18n related code
  if (!themeConfig.app.i18n.enable) {
    return
  }

  // watch and change lang attribute of html on language change
  watch(
    storedLang,
    (val) => {
      // Update lang attribute of html tag
      if (typeof document !== 'undefined' && val)
        document.documentElement.setAttribute('lang', val)

      // set isAppRtl value based on selected language
      if (themeConfig.app.i18n.langConfig && themeConfig.app.i18n.langConfig.length) {
        themeConfig.app.i18n.langConfig.forEach((lang) => {
          if (lang.i18nLang === val)
            configStore.isAppRTL = lang.isRTL
        })
      }
    },
    { immediate: true },
  )
}

function _handleSkinChanges() {
  const { themes } = useTheme()
  const configStore = useConfigStore()

  // Create skin default color so that we can revert back to original (default skin) color when switch to default skin from bordered skin
  Object.values(themes.value).forEach((t) => {
    t.colors['skin-default-background'] = t.colors.background
    t.colors['skin-default-surface'] = t.colors.surface
  })

  watch(
    () => configStore.skin,
    (val) => {
      Object.values(themes.value).forEach((t) => {
        const backgroundKey = `skin-${val}-background` as keyof typeof t.colors
        const surfaceKey = `skin-${val}-surface` as keyof typeof t.colors

        if (t.colors[backgroundKey]) {
          t.colors.background = t.colors[backgroundKey] as string
        }
        if (t.colors[surfaceKey]) {
          t.colors.surface = t.colors[surfaceKey] as string
        }
      })
    },
    { immediate: true },
  )
}

/*
    ℹ️ Set current theme's surface color in localStorage

    Why? Because when initial loader is shown (before vue is ready) we need to what's the current theme's surface color.
    We will use color stored in localStorage to set the initial loader's background color.

    With this we will be able to show correct background color for the initial loader even before vue identify the current theme.
  */
function _syncInitialLoaderTheme() {
  const vuetifyTheme = useTheme()

  // Initialize theme colors in localStorage immediately for the initial loader
  if (typeof localStorage !== 'undefined') {
    // Set initial values based on theme (dark mode default)
    const initialBg = '#121212'
    const initialColor = '#7367F0'

    // Store these values for use by both initial HTML template and Vue components
    localStorage.setItem(namespaceConfig('initial-loader-bg'), initialBg)
    localStorage.setItem(namespaceConfig('initial-loader-color'), initialColor)

    // If we're in a browser environment, try to immediately update the loader background
    if (typeof document !== 'undefined') {
      // Try to find and update the initial loader that was created by app.html template
      const loaderElement = document.getElementById('nuxt-loading')
      if (loaderElement) {
        loaderElement.style.backgroundColor = initialBg
      }
    }
  }

  watch(
    () => useConfigStore().theme,
    (_theme) => {
      // ℹ️ We are not using theme.current.colors.surface because watcher is independent and when this watcher is ran `theme` computed is not updated
      const surface = vuetifyTheme.current.value.colors.surface
      const primary = vuetifyTheme.current.value.colors.primary

      useStorage<string | null>(namespaceConfig('initial-loader-bg'), null).value = surface
      useStorage<string | null>(namespaceConfig('initial-loader-color'), null).value = primary

      // Update loader background if it still exists
      if (typeof document !== 'undefined') {
        const loaderElement = document.getElementById('nuxt-loading')
        if (loaderElement) {
          loaderElement.style.backgroundColor = surface
        }
      }
    },
    { immediate: true },
  )
}

function initCore() {
  _syncInitialLoaderTheme()
  _handleSkinChanges()

  // ℹ️ We don't want to trigger i18n in SK
  if (themeConfig.app.i18n.enable)
    _syncAppRtl()
}

export default initCore
