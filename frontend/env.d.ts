/// <reference types="nuxt" />
/// <reference types="vue/macros-global" />
/// <reference path="./types/vuetify-shims.d.ts" />
/// <reference types="vuetify-shims" />

import type { RouteLocationRaw } from 'vue-router'
import 'vue'

declare module 'vue-router' {
  interface RouteMeta {
    action?: string
    subject?: string
    layoutWrapperClasses?: string
    navActiveLink?: RouteLocationRaw
    layout?: 'blank' | 'default'
    unauthenticatedOnly?: boolean
    public?: boolean
  }
}

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

declare module 'vuetify/styles' {}
