declare module '@vue/runtime-core' {
  import type { ThemeInstance } from 'vuetify'

  interface ComponentCustomProperties {
    $vuetify: {
      theme: ThemeInstance
      display: {
        xs: boolean
        sm: boolean
        md: boolean
        lg: boolean
        xl: boolean
        xxl: boolean
        smAndUp: boolean
        mdAndUp: boolean
        lgAndUp: boolean
        xlAndUp: boolean
        smAndDown: boolean
        mdAndDown: boolean
        lgAndDown: boolean
        xlAndDown: boolean
        width: number
        height: number
      }
    }
  }
}

export {}
