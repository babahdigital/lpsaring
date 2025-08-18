// plugins/99.performance-optimization.client.ts
// Optimasi khusus untuk aplikasi portal hotspot di jaringan lokal

export default defineNuxtPlugin(() => {
  // Nonaktifkan console warnings yang tidak perlu
  if (process.env.NODE_ENV === 'production') {
    const originalConsoleWarn = console.warn
    console.warn = (...args) => {
      const message = args.join(' ')
      // Skip warning yang sudah diketahui dan tidak berbahaya
      if (
        message.includes('Label')
        && (message.includes('already exists') || message.includes('No such label'))
      ) {
        return
      }
      originalConsoleWarn.apply(console, args)
    }
  }

  // Fix console.time warning untuk development
  if (process.env.NODE_ENV === 'development') {
    const originalTime = console.time
    const originalTimeEnd = console.timeEnd
    const activeTimers = new Set<string>()

    console.time = (label?: string) => {
      if (!label)
        return originalTime.call(console)

      // Special handling for link:prefetch timers which can be called multiple times
      if (label.includes('link:prefetch')) {
        // For link:prefetch timers, if timer exists, silently succeed without warning
        if (activeTimers.has(label)) {
          return
        }
        activeTimers.add(label)
        originalTime.call(console, label)
        return
      }

      // Normal handling for other timers
      if (activeTimers.has(label)) {
        console.debug(`[FIXED] Timer '${label}' already exists, skipping`)
        return
      }
      activeTimers.add(label)
      originalTime.call(console, label)
    }

    console.timeEnd = (label?: string) => {
      if (!label)
        return originalTimeEnd.call(console)

      // Special handling for link:prefetch timers
      if (label.includes('link:prefetch')) {
        // For link:prefetch, if timer doesn't exist, silently ignore
        if (!activeTimers.has(label)) {
          return
        }
        activeTimers.delete(label)
        originalTimeEnd.call(console, label)
        return
      }

      // Normal handling for other timers
      if (!activeTimers.has(label)) {
        console.warn(`[FIXED] No timer '${label}' to end, skipping`)
        return
      }
      activeTimers.delete(label)
      originalTimeEnd.call(console, label)
    }
  }

  // Optimasi untuk loading di jaringan lokal
  if (import.meta.client) {
    console.log('[PERFORMANCE] Performance optimization plugin loaded')

    // Pastikan hideInitialLoader tersedia globally dengan type safety
    const globalWindow = window as any
    if (!globalWindow.hideInitialLoader) {
      console.warn('[PERFORMANCE] hideInitialLoader not found, creating fallback')
      globalWindow.hideInitialLoader = function () {
        const loaderEl = document.querySelector('.loader-overlay')
        if (loaderEl) {
          console.log('[PERFORMANCE] Fallback: hiding loader overlay')
          ; (loaderEl as HTMLElement).style.opacity = '0'
          setTimeout(() => {
            loaderEl.remove()
            document.body.style.overflow = ''
          }, 500)
        }
      }
    }

    // (Dihilangkan) Preload favicon dihapus karena memicu warning Chrome bila tidak segera digunakan.
    // Jika ingin preload lain yang benar-benar kritikal (font / hero image) bisa ditambahkan di sini.

    // Optimasi untuk device dengan memory terbatas
    if (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2) {
      // Kurangi animasi untuk device low-end
      document.documentElement.style.setProperty('--animation-duration', '0.1s')
    }

    // Auto-hide loader sebagai fallback jika terjadi masalah
    setTimeout(() => {
      if (document.querySelector('.loader-overlay')) {
        console.log('[PERFORMANCE] Auto-hiding loader after 5 seconds (fallback)')
        globalWindow.hideInitialLoader?.()
      }
    }, 5000)
  }
})
