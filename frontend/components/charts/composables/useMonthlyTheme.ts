import { hexToRgb } from '@core/utils/colorConverter'
/* composables/useMonthlyTheme.ts */
import { computed } from 'vue'
import { useTheme } from 'vuetify'

export function useMonthlyTheme() {
  const vuetifyTheme = useTheme()

  const currentThemeColors = computed(() => vuetifyTheme.current.value.colors)
  const currentThemeVariables = computed(() => vuetifyTheme.current.value.variables)

  const chartPrimaryColor = computed(
    () => currentThemeColors.value.primary ?? '#A672FF',
  )

  const legendColor = computed(() => {
    const onBg = hexToRgb(currentThemeColors.value['on-background'] ?? (vuetifyTheme.current.value.dark ? '#FFF' : '#000'))
    const op = currentThemeVariables.value['high-emphasis-opacity'] ?? 0.87
    return onBg ? `rgba(${onBg},${op})` : (vuetifyTheme.current.value.dark ? 'rgba(255,255,255,0.87)' : 'rgba(0,0,0,0.87)')
  })

  const themeBorderColor = computed(() => {
    const borderColorVar = String(currentThemeVariables.value['border-color'] ?? '')
    const opacity = currentThemeVariables.value['border-opacity'] ?? 0.12
    const rgb = borderColorVar ? hexToRgb(borderColorVar) : null
    if (rgb)
      return `rgba(${rgb},${opacity})`
    const fallback = hexToRgb(currentThemeColors.value['on-surface'] ?? '#000')
    return fallback ? `rgba(${fallback},${opacity})` : 'rgba(0,0,0,0.12)'
  })

  const themeLabelColor = computed(() => {
    const onSurface = hexToRgb(currentThemeColors.value['on-surface'] ?? (vuetifyTheme.current.value.dark ? '#FFF' : '#000'))
    const op = currentThemeVariables.value['disabled-opacity'] ?? 0.38
    return onSurface ? `rgba(${onSurface},${op})` : (vuetifyTheme.current.value.dark ? 'rgba(255,255,255,0.38)' : 'rgba(0,0,0,0.38)')
  })

  const errorDisplayColor = computed(() => currentThemeColors.value.error ?? '#FF5252')

  return {
    vuetifyTheme,
    chartPrimaryColor,
    legendColor,
    themeBorderColor,
    themeLabelColor,
    errorDisplayColor,
  }
}
