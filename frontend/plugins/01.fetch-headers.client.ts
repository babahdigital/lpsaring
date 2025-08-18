// plugins/01.fetch-headers.client.ts (deprecated)
// No-op placeholder. Header injection is now centralized in plugins/02.api.client.ts
// to avoid duplicate logic and unexpected overrides of window.fetch.

import { defineNuxtPlugin } from '#app'

export default defineNuxtPlugin(() => {
  // intentionally empty
})
