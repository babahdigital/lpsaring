import type { RegisterResponse, RegistrationPayload, User, VerifyOtpResponse } from '~/types/auth'
import { navigateTo, useCookie, useNuxtApp, useRoute } from '#app'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

function extractErrorMessage(errorData: any, defaultMessage: string): string {
  // PERBAIKAN: Pengecekan null/undefined yang eksplisit
  if (errorData == null)
    return defaultMessage
  if (typeof errorData === 'string')
    return errorData
  if (typeof errorData.error === 'string')
    return errorData.error
  if (typeof errorData.message === 'string')
    return errorData.message

  let detailMsg: string | null = null
  if (typeof errorData.detail === 'string') {
    detailMsg = errorData.detail
  }
  else if (Array.isArray(errorData.detail) && errorData.detail.length > 0) {
    if (typeof errorData.detail[0] === 'object' && errorData.detail[0] !== null)
      // PERBAIKAN: Mengganti || dengan ??
      detailMsg = errorData.detail.map((e: any) => `${e.loc?.join('.') ?? 'field'} - ${e.msg}`).join('; ')
    else
      detailMsg = errorData.detail.join('; ')
  }
  // PERBAIKAN: Mengganti || dengan ??
  return detailMsg ?? defaultMessage
}

export const useAuthStore = defineStore('auth', () => {
  const tokenCookie = useCookie<string | null>('auth_token', {
    maxAge: 60 * 60 * 24 * 7, // 7 hari
    sameSite: 'lax',
    path: '/',
    secure: false, // Untuk debug saja jika tanpa HTTPS
  })

  const user = ref<User | null>(null)
  const loading = ref(false)
  const loadingUser = ref(false)
  const error = ref<string | null>(null)
  const message = ref<string | null>(null)
  const initialAuthCheckDone = ref(false)

  const token = computed(() => tokenCookie.value)
  // PERBAIKAN: Pengecekan eksplisit untuk isLoggedIn
  const isLoggedIn = computed(() => token.value != null && user.value != null)
  const currentUser = computed(() => user.value)
  const isAdmin = computed(() => user.value?.role === 'ADMIN' || user.value?.role === 'SUPER_ADMIN')
  const isSuperAdmin = computed(() => user.value?.role === 'SUPER_ADMIN')
  const isKomandan = computed(() => user.value?.role === 'KOMANDAN')
  const isUserApprovedAndActive = computed(() =>
    user.value != null && user.value.is_active === true && user.value.approval_status === 'APPROVED',
  )

  function clearError() {
    error.value = null
  }
  function clearMessage() {
    message.value = null
  }
  function setUser(userData: User | null) {
    user.value = userData
  }
  function setError(errorMessage: string) {
    error.value = errorMessage
    message.value = null
    loading.value = false
    loadingUser.value = false
  }
  function setMessage(successMessage: string) {
    message.value = successMessage
    error.value = null
  }

  async function fetchUser(): Promise<boolean> {
    const { $api } = useNuxtApp()
    // PERBAIKAN: Pengecekan eksplisit
    if (token.value == null) {
      setUser(null)
      return false
    }

    loadingUser.value = true
    try {
      const fetchedUser = await $api<User>('/auth/me', { method: 'GET' })

      // PERBAIKAN: Pengecekan eksplisit
      if (fetchedUser != null && fetchedUser.id != null) {
        setUser(fetchedUser)
        clearError()
        return true
      }
      throw new Error('Format data pengguna dari server tidak valid.')
    }
    catch (err: any) {
      setError(extractErrorMessage(err.data, 'Gagal memuat data pengguna.'))
      return false
    }
    finally {
      loadingUser.value = false
    }
  }

  async function requestOtp(phoneNumber: string): Promise<boolean> {
    const { $api } = useNuxtApp()
    loading.value = true
    clearError()
    clearMessage()
    try {
      await $api('/auth/request-otp', {
        method: 'POST',
        body: { phone_number: phoneNumber },
      })
      setMessage('Kode OTP berhasil dikirim ke nomor WhatsApp Anda.')
      return true
    }
    catch (err: any) {
      // PERBAIKAN: Mengganti || dengan ??
      const statusCode = err.response?.status ?? err.statusCode
      let baseErrMsg = 'Terjadi kesalahan saat meminta OTP.'
      if (statusCode === 404)
        baseErrMsg = 'Nomor telepon tidak terdaftar.'
      else if (statusCode === 403)
        baseErrMsg = 'Akun Anda belum aktif atau belum disetujui oleh Admin.'

      setError(extractErrorMessage(err.data, baseErrMsg))
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function adminLogin(username: string, password: string): Promise<boolean> {
    const { $api } = useNuxtApp()
    loading.value = true
    clearError()
    try {
      const response = await $api<VerifyOtpResponse>('/auth/admin/login', {
        method: 'POST',
        body: { username, password },
      })
      // PERBAIKAN: Pengecekan eksplisit
      if (response != null && response.access_token != null) {
        tokenCookie.value = response.access_token
        const userFetched = await fetchUser()
        // PERBAIKAN: Pengecekan boolean eksplisit
        if (userFetched === true && isAdmin.value === true) {
          setMessage('Login berhasil!')
          return true
        }
        await logout(false)
        setError('Login berhasil, namun gagal memverifikasi hak akses admin.')
        return false
      }
      throw new Error('Respons server tidak valid.')
    }
    catch (err: any) {
      setError(extractErrorMessage(err.data, 'Username atau password salah.'))
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function register(payload: RegistrationPayload): Promise<boolean> {
    const { $api } = useNuxtApp()
    loading.value = true
    clearError()
    clearMessage()
    try {
      const response = await $api<RegisterResponse>('/auth/register', { method: 'POST', body: payload })
      // PERBAIKAN: Mengganti || dengan ??
      const successMsg = response.message ?? 'Registrasi berhasil! Akun Anda menunggu persetujuan Admin.'
      setMessage(successMsg)
      return true
    }
    catch (err: any) {
      // PERBAIKAN: Mengganti || dengan ??
      const statusCode = err.response?.status ?? err.statusCode
      let baseErrMsg = 'Terjadi kesalahan saat proses registrasi.'
      if (statusCode === 409)
        baseErrMsg = 'Nomor telepon atau email ini sudah terdaftar.'
      else if (statusCode === 422)
        baseErrMsg = 'Data yang dimasukkan tidak valid.'

      setError(extractErrorMessage(err.data, baseErrMsg))
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function verifyOtp(phoneNumber: string, otpCode: string): Promise<boolean> {
    const { $api } = useNuxtApp()
    loading.value = true
    clearError()
    clearMessage()
    try {
      const response = await $api<VerifyOtpResponse>('/auth/verify-otp', {
        method: 'POST',
        body: { phone_number: phoneNumber, otp: otpCode },
      })
      // PERBAIKAN: Pengecekan eksplisit
      if (response != null && response.access_token != null) {
        tokenCookie.value = response.access_token
        const userFetched = await fetchUser()
        // PERBAIKAN: Pengecekan boolean dan null eksplisit
        if (userFetched === true && user.value != null) {
          setMessage('Login berhasil!')
          if (import.meta.client)
            await navigateTo('/dashboard', { replace: true })

          return true
        }
        else {
          await logout(false)
          setError('Gagal memuat detail pengguna setelah verifikasi OTP.')
          return false
        }
      }
      else {
        throw new Error('Respons server tidak valid.')
      }
    }
    catch (err: any) {
      // PERBAIKAN: Mengganti || dengan ??
      const statusCode = err.response?.status ?? err.statusCode
      let baseErrMsg = 'Terjadi kesalahan saat verifikasi OTP.'
      if (statusCode === 401 || statusCode === 400)
        baseErrMsg = 'Kode OTP tidak valid atau telah kedaluwarsa.'

      setError(extractErrorMessage(err.data, baseErrMsg))
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function logout(performRedirect: boolean = true) {
    const { $api } = useNuxtApp()
    const isAdminRoute = import.meta.client ? useRoute().path.startsWith('/admin') : false

    // PERBAIKAN: Pengecekan eksplisit
    if (token.value != null)
      $api('/auth/logout', { method: 'POST' }).catch(() => {})

    tokenCookie.value = null
    setUser(null)
    initialAuthCheckDone.value = false

    if (performRedirect && import.meta.client) {
      setMessage('Anda telah berhasil logout.')
      await navigateTo(isAdminRoute ? '/admin' : '/login', { replace: true })
    }
  }

  async function initializeAuth() {
    if (initialAuthCheckDone.value === true)
      return

    // PERBAIKAN: Pengecekan eksplisit
    if (token.value != null)
      await fetchUser()

    initialAuthCheckDone.value = true
  }

  return {
    user,
    token,
    isLoggedIn,
    currentUser,
    isAdmin,
    isSuperAdmin,
    isKomandan,
    isUserApprovedAndActive,
    loading,
    loadingUser,
    error,
    message,
    initialAuthCheckDone,
    clearError,
    clearMessage,
    setError,
    setMessage,
    fetchUser,
    requestOtp,
    adminLogin,
    register,
    verifyOtp,
    logout,
    initializeAuth,
  }
})
