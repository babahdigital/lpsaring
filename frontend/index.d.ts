import type { RouteLocationRaw } from 'vue-router'

declare module '#app' {
  interface PageMeta {
    action?: string
    subject?: string
    layoutWrapperClasses?: string
    navActiveLink?: RouteLocationRaw
    requiredRole?: string[]

    unauthenticatedOnly?: boolean
    public?: boolean
  }
}

// It is always important to ensure you import/export something when augmenting a type
export {}
