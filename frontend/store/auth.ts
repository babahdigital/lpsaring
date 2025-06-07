// frontend/store/auth.ts

import type { RegisterResponse, RegistrationPayload, User, VerifyOtpResponse } from '~/types/auth'
import { navigateTo, useCookie, useNuxtApp } from '#app'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

function extractErrorMessage(errorData: any, defaultMessage: string): string {
  if (!errorData) {
    return defaultMessage
  }
  if (typeof errorData === 'string') {
    return errorData
  }
  if (typeof errorData.error === 'string') {
    return errorData.error
  }
  if (typeof errorData.message === 'string') {
    return errorData.message
  }

  let detailMsg: string | null = null
  if (typeof errorData.detail === 'string') {
    detailMsg = errorData.detail
  }
  else if (Array.isArray(errorData.detail) && errorData.detail.length > 0) {
    if (typeof errorData.detail[0] === 'string') {
      detailMsg = errorData.detail.join('; ')
    }
    else if (typeof errorData.detail[0] === 'object' && errorData.detail[0] !== null) {
      detailMsg = errorData.detail.map((e: any) => `${e.loc?.join('.') || 'field'} - ${e.msg}`).join('; ')
    }
  }
  else if (typeof errorData.details === 'string') {
    detailMsg = errorData.details
  }
  else if (Array.isArray(errorData.details)) {
    detailMsg = errorData.details.map((d: any) => d.msg || JSON.stringify(d)).join(', ')
  }

  return detailMsg || defaultMessage
}

export const useAuthStore = defineStore('auth', () => {
  const tokenCookie = useCookie<string | null>('auth_token', {
    maxAge: 60 * 60 * 24 * 7, // 7 hari
    sameSite: 'lax',
    path: '/',
    secure: import.meta.env.PROD,
    httpOnly: false,
  })

  const user = ref<User | null>(null)
  const loading = ref(false)
  const loadingUser = ref(false)
  const error = ref<string | null>(null)
  const message = ref<string | null>(null)
  const isInitialized = ref(false)

  const token = computed(() => tokenCookie.value)
  const isLoggedIn = computed(() => !!tokenCookie.value && !!user.value)
  const getUser = computed(() => user.value)
  const isAdmin = computed(() => user.value?.role === 'ADMIN' || user.value?.role === 'SUPER_ADMIN')
  
  // ===================================================================
  // == PENAMBAHAN GETTER BARU ==
  // ===================================================================
  const isSuperAdmin = computed(() => user.value?.role === 'SUPER_ADMIN')
  // ===================================================================

  const isUserApprovedAndActive = computed(() =>
    !!user.value && user.value.is_active === true && user.value.approval_status === 'APPROVED',
  )
  const isLoading = computed(() => loading.value)
  const isLoadingUserOp = computed(() => loadingUser.value)
  const getError = computed(() => error.value)
  const getMessage = computed(() => message.value)

  function clearError() {
    error.value = null
  }

  function clearMessage() {
    message.value = null
  }

  function setError(errorMessage: string, keepLoading: boolean = false) {
    error.value = errorMessage
    message.value = null
    if (!keepLoading) {
      loading.value = false
      loadingUser.value = false
    }
  }

  function setMessage(successMessage: string) {
    message.value = successMessage
    error.value = null
  }

  function setUser(userData: User | null) {
    user.value = userData
  }

  async function fetchUser(): Promise<boolean> {
    const { $api } = useNuxtApp()
    if (!tokenCookie.value) {
      setUser(null)
      return false
    }
    loadingUser.value = true
    try {
      const fetchedUser = await $api<User>('/auth/me', { method: 'GET' })
      if (fetchedUser && fetchedUser.id) {
        setUser(fetchedUser)
        clearError()
        return true
      }
      else {
        setUser(null)
        setError('Format data pengguna dari server tidak sesuai.')
        return false
      }
    }
    catch (err: any) {
      const status = err.response?.status || err.statusCode
      const errorData = err.data || err.response?._data
      const errMsg = extractErrorMessage(errorData, 'Gagal memuat data pengguna.')
      setUser(null)
      if (status !== 401) {
        setError(errMsg)
      }
      return false
    }
    finally {
      loadingUser.value = false
    }
  }

  async function requestOtp(phoneNumber: string): Promise<boolean> {
    const { $api } = useNuxtApp()
    clearError()
    clearMessage()
    loading.value = true
    try {
      await $api('/auth/request-otp', { method: 'POST', body: { phone_number: phoneNumber } })
      setMessage('Kode OTP telah dikirim ke nomor WhatsApp Anda.')
      return true
    }
    catch (err: any) {
      const errorData = err.data || err.response?._data
      const errMsg = extractErrorMessage(errorData, 'Terjadi kesalahan saat meminta OTP.')
      setError(errMsg)
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function verifyOtp(phoneNumber: string, otpCode: string): Promise<boolean> {
    const { $api } = useNuxtApp()
    clearError()
    clearMessage()
    loading.value = true
    try {
      const response = await $api<VerifyOtpResponse>('/auth/verify-otp', {
        method: 'POST',
        body: { phone_number: phoneNumber, otp: otpCode },
      })
      if (response && response.access_token) {
        tokenCookie.value = response.access_token
        const userFetched = await fetchUser()
        if (userFetched && user.value) {
          setMessage('Login berhasil!')
          if (import.meta.client) {
            await navigateTo('/dashboard', { replace: true })
          }
          return true
        }
        else {
          if (!error.value) {
            setError('Gagal memuat detail pengguna setelah verifikasi OTP.')
          }
          if (tokenCookie.value) {
            await logout(false)
          }
          return false
        }
      }
      else {
        setError('Respons server tidak valid (token tidak ditemukan).')
        tokenCookie.value = null
        setUser(null)
        return false
      }
    }
    catch (err: any) {
      const statusCode = err.response?.status || err.statusCode
      const errorData = err.data || err.response?._data
      let baseErrMsg = 'Terjadi kesalahan saat verifikasi OTP.'
      if (statusCode === 401 || statusCode === 400) {
        baseErrMsg = 'Kode OTP tidak valid atau telah kedaluwarsa.'
      }
      else if (statusCode === 404) {
        baseErrMsg = 'Nomor telepon tidak terdaftar atau OTP tidak ditemukan.'
      }
      else if (statusCode === 403) {
        baseErrMsg = 'Verifikasi OTP tidak diizinkan.'
      }
      const errMsg = extractErrorMessage(errorData, baseErrMsg)
      setError(errMsg)
      return false
    }
    finally {
      loading.value = false
    }
  }
  
  async function adminLogin(username: string, password: string): Promise<boolean> {
    const { $api } = useNuxtApp()
    clearError()
    clearMessage()
    loading.value = true
    try {
      const response = await $api<VerifyOtpResponse>('/auth/admin/login', {
        method: 'POST',
        body: { username, password },
      })
      
      if (response && response.access_token) {
        tokenCookie.value = response.access_token
        const userFetched = await fetchUser()
        
        if (userFetched && user.value && (user.value.role === 'ADMIN' || user.value.role === 'SUPER_ADMIN')) {
          setMessage('Login admin berhasil!')
          return true
        }
        else {
          if (!error.value) {
            setError('Gagal memverifikasi hak akses admin setelah login.')
          }
          if (tokenCookie.value) {
            await logout(false)
          }
          return false
        }
      }
      else {
        setError('Respons server tidak valid (token tidak ditemukan).')
        tokenCookie.value = null
        setUser(null)
        return false
      }
    }
    catch (err: any) {
      const statusCode = err.response?.status || err.statusCode
      const errorData = err.data || err.response?._data
      let baseErrMsg = 'Terjadi kesalahan saat login.'
      if (statusCode === 401 || statusCode === 400) {
        baseErrMsg = 'Username atau password salah.'
      }
      else if (statusCode === 403) {
        baseErrMsg = 'Anda tidak memiliki hak akses untuk masuk.'
      }
      const errMsg = extractErrorMessage(errorData, baseErrMsg)
      setError(errMsg)
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function register(payload: RegistrationPayload): Promise<boolean> {
    const { $api } = useNuxtApp()
    clearError()
    clearMessage()
    loading.value = true
    try {
      const response = await $api<RegisterResponse>('/auth/register', { method: 'POST', body: payload })
      const successMsg = response.message || 'Registrasi berhasil! Akun Anda menunggu persetujuan Admin.'
      setMessage(successMsg)
      return true
    }
    catch (err: any) {
      const statusCode = err.response?.status || err.statusCode
      const errorData = err.data || err.response?._data
      let baseErrMsg = 'Terjadi kesalahan saat proses registrasi.'
      if (statusCode === 409) {
        baseErrMsg = 'Nomor telepon atau email ini sudah terdaftar.'
      }
      else if (statusCode === 422) {
        baseErrMsg = 'Data yang dimasukkan tidak valid. Periksa kembali isian Anda.'
      }
      const errMsg = extractErrorMessage(errorData, baseErrMsg)
      setError(errMsg)
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function logout(performRedirectAndSetMessage: boolean = true) {
    const { $api } = useNuxtApp()
    const redirectPath = (user.value?.role === 'ADMIN' || user.value?.role === 'SUPER_ADMIN') ? '/admin' : '/login'
    
    if (tokenCookie.value) {
      try {
        await $api('/auth/logout', { method: 'POST' })
      }
      catch {
        /* Abaikan error logout dari server, tetap bersihkan sisi klien */
      }
    }
    tokenCookie.value = null
    setUser(null)
    isInitialized.value = false
    if (performRedirectAndSetMessage) {
      if (!error.value) {
        setMessage('Anda telah berhasil logout.')
      }
      if (import.meta.client) {
        await new Promise(resolve => setTimeout(resolve, error.value || message.value ? 200 : 50))
        try {
          await navigateTo(redirectPath, { replace: true })
        }
        catch {
          window.location.assign(redirectPath)
        }
      }
    }
  }

  async function initializeAuth() {
    if (isInitialized.value && ((tokenCookie.value && user.value) || !tokenCookie.value)) {
      return
    }
    if (loadingUser.value) {
      return
    }
    loadingUser.value = true
    if (tokenCookie.value) {
      if (!user.value) {
        await fetchUser()
      }
    }
    else {
      setUser(null)
    }
    isInitialized.value = true
    loadingUser.value = false
  }

  return {
    user,
    token,
    isInitialized,
    isLoggedIn,
    getUser,
    isAdmin,
    isSuperAdmin, // <-- Daftarkan getter baru di sini
    isUserApprovedAndActive,
    isLoading,
    isLoadingUserOp,
    getError,
    getMessage,
    fetchUser,
    requestOtp,
    verifyOtp,
    register,
    adminLogin,
    logout,
    initializeAuth,
    clearError,
    clearMessage,
    setError,
    setMessage,
  }
})
