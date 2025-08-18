// frontend/types/plugins.d.ts

declare module '#app' {
  interface NuxtApp {
    $toast: {
      success: (message: string, duration?: number) => void
      error: (message: string, duration?: number) => void
      info: (message: string, duration?: number) => void
      warning: (message: string, duration?: number) => void
    }
    $api: <T = any>(url: string, options?: any) => Promise<T>
  }
}

// Extend the CustomEventInit interface to include our toast events
interface ToastEventDetail {
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
  duration?: number
}

interface AppToastEvent extends CustomEvent {
  detail: ToastEventDetail
}

declare global {
  interface WindowEventMap {
    'app:toast': AppToastEvent
  }
}

// Make TypeScript happy
export { }
