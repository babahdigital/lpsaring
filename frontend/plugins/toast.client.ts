// frontend/plugins/toast.client.ts

export default defineNuxtPlugin(() => {
  // Simple toast notification system
  const toast = {
    success(message: string, duration: number = 3000) {
      showToast('success', message, duration)
    },
    error(message: string, duration: number = 5000) {
      showToast('error', message, duration)
    },
    info(message: string, duration: number = 3000) {
      showToast('info', message, duration)
    },
    warning(message: string, duration: number = 4000) {
      showToast('warning', message, duration)
    },
  }

  // Listen for toast events from API plugin or other parts of the app
  if (typeof window !== 'undefined') {
    window.addEventListener('app:toast', ((event: CustomEvent) => {
      const { type, message, duration } = event.detail
      if (type && message && toast[type as keyof typeof toast]) {
        toast[type as keyof typeof toast](message, duration)
      }
    }) as EventListener)
  }

  return {
    provide: {
      toast,
    },
  }
})

function showToast(type: 'success' | 'error' | 'info' | 'warning', message: string, duration: number) {
  if (typeof document === 'undefined') {
    console.log(`[Toast ${type}]`, message)
    return
  }

  try {
    // Map types to colors
    const color = type === 'success'
      ? '#4CAF50'
      : type === 'error'
        ? '#FF5252'
        : type === 'warning'
          ? '#FB8C00'
          : '#2196F3' // info

    // Create and show toast element
    const toast = document.createElement('div')
    toast.className = `app-toast app-toast--${type}`
    toast.style.position = 'fixed'
    toast.style.bottom = '20px'
    toast.style.left = '50%'
    toast.style.transform = 'translateX(-50%)'
    toast.style.zIndex = '9999'
    toast.style.backgroundColor = color
    toast.style.color = 'white'
    toast.style.padding = '16px'
    toast.style.borderRadius = '4px'
    toast.style.minWidth = '300px'
    toast.style.maxWidth = '500px'
    toast.style.boxShadow = '0 3px 5px -1px rgba(0,0,0,.2),0 6px 10px 0 rgba(0,0,0,.14),0 1px 18px 0 rgba(0,0,0,.12)'
    toast.textContent = message

    document.body.appendChild(toast)

    // Auto remove
    setTimeout(() => {
      if (toast && toast.parentNode) {
        toast.parentNode.removeChild(toast)
      }
    }, duration)
  }
  catch (e) {
    console.log(`[Toast ${type} Error]`, message, e)
  }
}
