// Plugin untuk CSS loading optimization
export default defineNuxtPlugin({
  name: 'css-loader-optimization',
  parallel: false,
  setup() {
    if (!import.meta.client)
      return

    // CSS sudah di-preprocess oleh Nuxt/Vite, tidak perlu dynamic import
    console.log('🎨 CSS pre-processing completed by Nuxt/Vite')

    // Hide initial loader setelah plugin ready
    const hideLoader = () => {
      if (window.hideInitialLoader) {
        window.hideInitialLoader()
      }
      else {
        // Fallback: manual hide loader jika function tidak tersedia
        const loaderEl = document.querySelector('.loader-overlay') as HTMLElement
        if (loaderEl) {
          loaderEl.style.opacity = '0'
          setTimeout(() => {
            loaderEl.remove()
            document.body.style.overflow = ''
          }, 500)
        }
      }
    }

    // Coba beberapa kali dengan interval untuk memastikan function tersedia
    let attempts = 0
    const checkAndHide = () => {
      attempts++
      if (window.hideInitialLoader || attempts >= 5) {
        hideLoader()
      }
      else {
        setTimeout(checkAndHide, 200)
      }
    }

    // Delay awal untuk memastikan DOM ready
    setTimeout(checkAndHide, 500)
  },
})

// Extend window type untuk TypeScript
declare global {
  interface Window {
    hideInitialLoader?: () => void
  }
}
