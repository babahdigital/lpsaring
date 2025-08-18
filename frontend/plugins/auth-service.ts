// plugins/auth-service.ts
// Plugin to register the auth API service

import { defineNuxtPlugin } from '#app'

import { AuthApiService } from '~/services/auth-api.service'

export default defineNuxtPlugin((nuxtApp) => {
  // Cast the $api function to the expected type
  const authApiService = new AuthApiService(nuxtApp.$api as any)

  return {
    provide: {
      authApiService,
    },
  }
})
