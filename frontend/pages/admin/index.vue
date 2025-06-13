<script setup lang="ts">
import { useAuthStore } from '~/store/auth'
import { h } from 'vue'
import authV1BottomShape from '@images/svg/auth-v1-bottom-shape.svg?raw'
import authV1TopShape from '@images/svg/auth-v1-top-shape.svg?raw'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'

definePageMeta({
  layout: 'blank',
  auth: {
    unauthenticatedOnly: true,
    navigateAuthenticatedTo: '/admin/dashboard',
  },
})

// --- State Management dan Logika Login (Sama seperti sebelumnya) ---
const authStore = useAuthStore()
const router = useRouter()

const form = ref({
  username: '',
  password: '',
})

const isPasswordVisible = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)

const handleLogin = async () => {
  loading.value = true
  error.value = null
  try {
    const loginSuccess = await authStore.adminLogin(form.value.username, form.value.password)
    if (loginSuccess) {
      await router.push('/admin/dashboard')
    }
    else {
      error.value = authStore.getError || 'Login gagal, periksa kembali username dan password Anda.'
    }
  }
  catch (err: any) {
    error.value = authStore.getError || 'Terjadi kesalahan yang tidak terduga.'
    console.error('Admin login exception:', err)
  }
  finally {
    loading.value = false
  }
}
useHead({ title: 'Login Admin' })
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
        :class="$vuetify.display.smAndUp ? 'pa-6' : 'pa-0'"
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
          <ClientOnly>
            <VForm @submit.prevent="handleLogin">
              <VRow>
                <VCol cols="12">
                  <AppTextField
                    v-model="form.username"
                    autofocus
                    label="Telpon"
                    type="text"
                    placeholder="0811xxxx"
                    autocomplete="username"
                    :disabled="loading"
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
                    :disabled="loading"
                    @click:append-inner="isPasswordVisible = !isPasswordVisible"
                  />

                  <div class="my-6">
                    <VBtn
                      block
                      type="submit"
                      :loading="loading"
                      :disabled="loading"
                    >
                      Login
                    </VBtn>
                  </div>
                </VCol>

                <VCol
                  v-if="error"
                  cols="12"
                >
                  <VAlert
                    type="error"
                    variant="tonal"
                  >
                    {{ error }}
                  </VAlert>
                </VCol>
              </VRow>
            </VForm>
          </ClientOnly>
          </VCardText>
      </VCard>
    </div>
  </div>
</template>

<style lang="scss">
@use "@core/scss/template/pages/page-auth";
</style>