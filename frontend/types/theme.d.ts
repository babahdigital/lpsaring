// frontend/types/theme.d.ts
import type { UserThemeConfig } from '@core/types'

declare module '@theme' {
  export const themeConfig: UserThemeConfig
  export const layoutConfig: UserThemeConfig
}
