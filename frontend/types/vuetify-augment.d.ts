import 'vue'

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $vuetify: {
      display: {
        smAndDown: boolean
        smAndUp: boolean
        xs: boolean
        width: number
      }
      theme: {
        current: {
          dark: boolean
        }
      }
    }
  }
}

export {}
