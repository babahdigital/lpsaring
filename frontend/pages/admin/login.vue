<script setup lang="ts">
import type { VForm } from 'vuetify/components'

import authV1BottomShape from '@images/svg/auth-v1-bottom-shape.svg?raw'
import authV1TopShape from '@images/svg/auth-v1-top-shape.svg?raw'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { h, ref } from 'vue'
import { useDisplay } from 'vuetify'

import { useSnackbar } from '~/composables/useSnackbar'
import { useAuthStore } from '~/store/auth'

definePageMeta({
  layout: 'blank',
})

const authStore = useAuthStore()
const { smAndUp } = useDisplay()
const snackbar = useSnackbar()

const formRef = ref<InstanceType<typeof VForm> | null>(null)
const form = ref({
  username: '',
  password: '',
})

const isPasswordVisible = ref(false)

const phoneFormatRules = [
  (v: string) => !!v || 'Nomor telepon wajib diisi.',
  (v: string) => {
    const phoneRegex = /^08[1-9]\d{7,11}$/
    return phoneRegex.test(v) || 'Format nomor telepon tidak valid (contoh: 081234567890).'
  },
]

const requiredRule = (v: string) => !!v || 'Password wajib diisi.'

async function handleLogin() {
  if (!formRef.value)
    return

  const { valid } = await formRef.value.validate()
  if (!valid)
    return

  console.log('[AdminLogin] Attempting login...')
  const loginSuccess = await authStore.adminLogin(form.value.username, form.value.password)

  if (loginSuccess) {
    console.log('[AdminLogin] Login successful, checking admin status...')

    // Set explicit admin flag in localStorage
    localStorage.setItem('is_admin_user', 'true')

    // Force a user fetch to ensure we have updated user data
    await authStore.fetchUser()

    // Double check admin status
    console.log('[AdminLogin] Admin status after login:', authStore.isAdmin)

    // If still not showing as admin, force a page reload to refresh state
    if (!authStore.isAdmin) {
      console.warn('[AdminLogin] Admin status not detected in store, forcing page reload')

      // Store destination URL in localStorage to survive the reload
      localStorage.setItem('admin_redirect_after_reload', '/admin/dashboard')

      // Perform a full page reload to reset state
      window.location.href = '/admin/login?reload=true'
      return
    }

    // Force hard refresh to ensure session is properly loaded
    console.log('[AdminLogin] Redirecting to admin dashboard')

    // Use direct URL change to avoid routing issues
    window.location.href = '/admin/dashboard'
  }
  else {
    snackbar.add({
      type: 'error',
      title: 'Login Gagal',
      text: authStore.error || 'Terjadi kesalahan. Periksa kembali data Anda dan koneksi internet.',
    })
  }
}
useHead({ title: 'Login Admin' })

// Check for reload parameter in URL
onMounted(() => {
  const url = new URL(window.location.href)
  const reload = url.searchParams.get('reload')
  if (reload === 'true') {
    console.log('[AdminLogin] Page reloaded for admin role refresh')

    // Check for admin flag
    const isAdminInLocalStorage = localStorage.getItem('is_admin_user') === 'true'
    console.log('[AdminLogin] Admin flag in localStorage:', isAdminInLocalStorage)

    // Check for redirect instruction
    const redirectAfterReload = localStorage.getItem('admin_redirect_after_reload')
    if (redirectAfterReload) {
      console.log('[AdminLogin] Found redirect instruction after reload:', redirectAfterReload)

      // Give a moment for store to initialize
      setTimeout(() => {
        window.location.href = redirectAfterReload
        localStorage.removeItem('admin_redirect_after_reload')
      }, 500)
    }
  }
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <div class="position-relative my-sm-16">
      <VNodeRenderer
        :nodes="h('div', { innerHTML: authV1TopShape })"
        class="text-primary auth-v1-top-shape d-none d-sm-block"
      />

      <VNodeRenderer
        :nodes="h('div', { innerHTML: authV1BottomShape })"
        class="text-primary auth-v1-bottom-shape d-none d-sm-block"
      />

      <VCard
        class="auth-card"
        max-width="460"
        :class="smAndUp ? 'pa-6' : 'pa-0'"
      >
        <VCardText>
          <h4 class="text-h4 mb-1">
            Admin Portal 👋🏻
          </h4>
          <p class="mb-0">
            Silakan masuk untuk melanjutkan ke dasbor admin.
          </p>
        </VCardText>

        <VCardText>
          <VForm
            ref="formRef"
            @submit.prevent="handleLogin"
          >
            <VRow>
              <VCol cols="12">
                <AppTextField
                  v-model="form.username"
                  autofocus
                  label="Nomor Telepon Admin"
                  type="text"
                  placeholder="081234567890"
                  autocomplete="username"
                  :disabled="authStore.loading"
                  :rules="phoneFormatRules"
                />
              </VCol>

              <VCol cols="12">
                <AppTextField
                  v-model="form.password"
                  label="Password"
                  placeholder="············"
                  :type="isPasswordVisible ? 'text' : 'password'"
                  autocomplete="current-password"
                  :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                  :disabled="authStore.loading"
                  :rules="[requiredRule]"
                  @click:append-inner="isPasswordVisible = !isPasswordVisible"
                />

                <div class="my-6">
                  <VBtn
                    block
                    type="submit"
                    :loading="authStore.loading"
                    :disabled="authStore.loading"
                  >
                    Login
                  </VBtn>
                </div>
              </VCol>
            </VRow>
          </VForm>
        </VCardText>
      </VCard>
    </div>
  </div>
</template>

<style lang="scss">
@use "@core/scss/template/pages/page-auth.scss";
</style>
