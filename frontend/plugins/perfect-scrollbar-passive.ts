// plugins/perfect-scrollbar-passive.ts
export default defineNuxtPlugin(() => {
  if (import.meta.client) {
    // @ts-expect-error – type lint abaikan
    window.PerfectScrollbar && (window.PerfectScrollbar.prototype.eventElement = function (...args: any[]) {
      const [element, event, handler, capture] = args
      element.addEventListener(event, handler, { passive: true, capture })
    })
  }
})
