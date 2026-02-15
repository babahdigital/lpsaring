import type { RegisterResponse, RegistrationPayload, User, VerifyOtpResponse } from '~/types/auth'
import { navigateTo, useNuxtApp, useRoute } from '#app'
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
  type AccessStatus = 'ok' | 'blocked' | 'inactive' | 'expired' | 'habis' | 'fup'

  const user = ref<User | null>(null)
  const lastKnownUser = ref<User | null>(null)
  const loading = ref(false)
  const loadingUser = ref(false)
  const error = ref<string | null>(null)
  const message = ref<string | null>(null)
  const initialAuthCheckDone = ref(false)
  const lastAuthErrorCode = ref<number | null>(null)
  const autoLoginAttempted = ref(false)
  const lastStatusRedirect = ref<{ status: AccessStatus; sig?: string | null } | null>(null)

  const isLoggedIn = computed(() => user.value != null)
  const currentUser = computed(() => user.value)
  const isAdmin = computed(() => user.value?.role === 'ADMIN' || user.value?.role === 'SUPER_ADMIN')
  const isSuperAdmin = computed(() => user.value?.role === 'SUPER_ADMIN')
  const isKomandan = computed(() => user.value?.role === 'KOMANDAN')
  const isUserApprovedAndActive = computed(() =>
    user.value != null && user.value.is_active === true && user.value.approval_status === 'APPROVED',
  )

  function clearError() {
    error.value = null
    lastAuthErrorCode.value = null
    lastStatusRedirect.value = null
  }
  function clearMessage() {
    message.value = null
  }
  function setUser(userData: User | null) {
    user.value = userData
    if (userData != null)
      lastKnownUser.value = userData
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

  function setStatusRedirect(status: AccessStatus, sig?: string | null) {
    lastStatusRedirect.value = {
      status,
      sig: sig ?? null,
    }
  }

  function getStatusRedirectPath(context: 'login' | 'captive'): string | null {
    if (!lastStatusRedirect.value)
      return null
    const basePath = getRedirectPathForStatus(lastStatusRedirect.value.status, context)
    if (!basePath)
      return null
    const sig = lastStatusRedirect.value.sig
    if (sig) {
      const status = lastStatusRedirect.value.status
      const params = new URLSearchParams({ status, sig })
      return `${basePath}?${params.toString()}`
    }
    return basePath
  }

  function clearSession(reasonCode?: number | null) {
    setUser(null)
    if (reasonCode != null)
      lastAuthErrorCode.value = reasonCode
    else
      lastAuthErrorCode.value = null
    initialAuthCheckDone.value = true
  }

  async function fetchUser(context: 'login' | 'captive' = 'login'): Promise<boolean> {
    const { $api } = useNuxtApp()
    loadingUser.value = true
    try {
      const fetchedUser = await $api<User>('/auth/me', { method: 'GET' })

      // PERBAIKAN: Pengecekan eksplisit
      if (fetchedUser != null && fetchedUser.id != null) {
        setUser(fetchedUser)
        clearError()
        await enforceAccessStatus(context)
        return true
      }
      throw new Error('Format data pengguna dari server tidak valid.')
    }
    catch (err: any) {
      const statusCode = err.response?.status ?? err.statusCode ?? null
      if (statusCode === 401 || statusCode === 403) {
        clearSession(statusCode)
        return false
      }
      setError(extractErrorMessage(err.data, 'Gagal memuat data pengguna.'))
      return false
    }
    finally {
      loadingUser.value = false
    }
  }

  async function enforceAccessStatus(context: 'login' | 'captive' = 'login') {
    const status = getAccessStatusFromUser(user.value)
    if (status === 'ok')
      return
    if (import.meta.client) {
      const route = useRoute()
      const redirectPath = getRedirectPathForStatus(status, context)
      const allowPurchasePaths = status === 'habis' || status === 'expired'
        ? (context === 'captive'
            ? ['/captive/beli', '/payment/finish', redirectPath]
            : ['/beli', '/payment/finish', redirectPath])
        : [redirectPath]

      if (allowPurchasePaths.includes(route.path))
        return

      if (redirectPath)
        await navigateTo(redirectPath, { replace: true })
    }
  }

  async function refreshSessionStatus() {
    const ok = await fetchUser('login')
    if (ok !== true)
      return
  }

  async function requestOtp(phoneNumber: string): Promise<boolean> {
    loading.value = true
    clearError()
    clearMessage()
    try {
      const { $api } = useNuxtApp()
      await $api('/auth/request-otp', {
        method: 'POST',
        body: new URLSearchParams({ phone_number: phoneNumber }),
      })
      setMessage('Kode OTP berhasil dikirim ke nomor WhatsApp Anda.')
      return true
    }
    catch (err: any) {
      // PERBAIKAN: Mengganti || dengan ??
      const statusCode = err.response?.status ?? err.statusCode ?? null
      const isNetworkError = statusCode == null
      let baseErrMsg = 'Terjadi kesalahan saat meminta OTP.'
      if (statusCode === 404)
        baseErrMsg = 'Nomor telepon tidak terdaftar.'
      else if (statusCode === 403)
        baseErrMsg = 'Akun Anda belum aktif atau belum disetujui oleh Admin.'
      else if (statusCode === 429)
        baseErrMsg = 'Terlalu sering meminta OTP. Silakan coba beberapa saat lagi.'
      else if (isNetworkError)
        baseErrMsg = 'Gagal terhubung ke server. Pastikan portal dan API dapat diakses dari jaringan hotspot.'

      setError(extractErrorMessage(err.data, baseErrMsg))
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function adminLogin(username: string, password: string): Promise<boolean> {
    loading.value = true
    clearError()
    try {
      const { $api } = useNuxtApp()
      const normalizedUsername = username.replace(/\s+/g, '')
      const normalizedPassword = password.trim()
      if (!normalizedUsername || !normalizedPassword) {
        setError('Username dan password wajib diisi.')
        return false
      }
      const response = await $api<VerifyOtpResponse>('/auth/admin/login', {
        method: 'POST',
        body: { username: normalizedUsername, password: normalizedPassword },
      })
      // PERBAIKAN: Pengecekan eksplisit
      if (response != null) {
        const userFetched = await fetchUser('login')
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
    loading.value = true
    clearError()
    clearMessage()
    try {
      const { $api } = useNuxtApp()
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

  async function verifyOtp(phoneNumber: string, otpCode: string): Promise<VerifyOtpResponse | null> {
    async function performVerifyOtp(): Promise<VerifyOtpResponse> {
      const { $api } = useNuxtApp()
      const response = await $api<VerifyOtpResponse>('/auth/verify-otp', {
        method: 'POST',
        body: new URLSearchParams({ phone_number: phoneNumber, otp: otpCode }),
      })
      // PERBAIKAN: Pengecekan eksplisit
      if (response != null) {
        const userFetched = await fetchUser('login')
        // PERBAIKAN: Pengecekan boolean dan null eksplisit
        if (userFetched === true && user.value != null) {
          setMessage('Login berhasil!')
          return response
        }
        await logout(false)
        throw new Error('Gagal memuat detail pengguna setelah verifikasi OTP.')
      }
      throw new Error('Respons server tidak valid.')
    }

    loading.value = true
    clearError()
    clearMessage()
    try {
      const response = await performVerifyOtp()
      return response
    }
    catch (err: any) {
      // PERBAIKAN: Mengganti || dengan ??
      const statusCode = err.response?.status ?? err.statusCode
      lastAuthErrorCode.value = statusCode ?? null
      const errorPayload = err?.data ?? err?.response?._data ?? null
      const statusFromPayload = typeof errorPayload?.status === 'string'
        ? (errorPayload.status as AccessStatus)
        : null
      const sigFromPayload = typeof errorPayload?.status_token === 'string'
        ? errorPayload.status_token
        : null
      if (statusFromPayload && sigFromPayload)
        setStatusRedirect(statusFromPayload, sigFromPayload)
      let baseErrMsg = 'Terjadi kesalahan saat verifikasi OTP.'
      if (statusCode === 401 || statusCode === 400)
        baseErrMsg = 'Kode OTP tidak valid atau telah kedaluwarsa.'
      else if (statusCode === 429)
        baseErrMsg = 'Terlalu banyak percobaan OTP. Silakan coba lagi nanti.'

      setError(extractErrorMessage(err.data, baseErrMsg))
      return null
    }
    finally {
      loading.value = false
    }
  }

  async function consumeSessionToken(sessionToken: string): Promise<boolean> {
    loading.value = true
    clearError()
    clearMessage()
    try {
      const { $api } = useNuxtApp()
      await $api<VerifyOtpResponse>('/auth/session/consume', {
        method: 'POST',
        body: { token: sessionToken },
      })
      const userFetched = await fetchUser('login')
      if (userFetched === true)
        return true
      throw new Error('Gagal memuat detail pengguna setelah membuka sesi.')
    }
    catch (err: any) {
      setError(extractErrorMessage(err.data, 'Gagal menukar session token.'))
      return false
    }
    finally {
      loading.value = false
    }
  }

  interface CaptiveVerifyResult {
    response: VerifyOtpResponse | null
    errorMessage?: string
    errorStatus?: AccessStatus | null
  }

  interface CaptiveClientInfo {
    clientIp?: string | null
    clientMac?: string | null
    hotspotLoginContext?: boolean | null
  }

  async function verifyOtpForCaptive(phoneNumber: string, otpCode: string, clientInfo?: CaptiveClientInfo): Promise<CaptiveVerifyResult> {
    loading.value = true
    clearError()
    clearMessage()
    try {
      const { $api } = useNuxtApp()
      const payload = new URLSearchParams({ phone_number: phoneNumber, otp: otpCode })
      payload.set('hotspot_login_context', 'true')
      if (clientInfo?.clientIp)
        payload.set('client_ip', clientInfo.clientIp)
      if (clientInfo?.clientMac)
        payload.set('client_mac', clientInfo.clientMac)
      if (clientInfo?.hotspotLoginContext === true)
        payload.set('hotspot_login_context', 'true')
      const response = await $api<VerifyOtpResponse>('/auth/verify-otp', {
        method: 'POST',
        body: payload,
      })

      if (response != null) {
        const userFetched = await fetchUser('captive')
        if (userFetched === true && user.value != null) {
          setMessage('Login berhasil!')
          return { response }
        }
        await logout(false)
        const errorMessage = 'Gagal memuat detail pengguna setelah verifikasi OTP.'
        setError(errorMessage)
        return { response: null, errorMessage, errorStatus: getAccessStatusFromError(errorMessage) }
      }
      throw new Error('Respons server tidak valid.')
    }
    catch (err: any) {
      const statusCode = err.response?.status ?? err.statusCode
      let baseErrMsg = 'Terjadi kesalahan saat verifikasi OTP.'
      if (statusCode === 401 || statusCode === 400)
        baseErrMsg = 'Kode OTP tidak valid atau telah kedaluwarsa.'
      else if (statusCode === 429)
        baseErrMsg = 'Terlalu banyak percobaan OTP. Silakan coba lagi nanti.'
      const errorPayload = err?.data ?? err?.response?._data ?? null
      const statusFromPayload = typeof errorPayload?.status === 'string'
        ? (errorPayload.status as AccessStatus)
        : null
      const sigFromPayload = typeof errorPayload?.status_token === 'string'
        ? errorPayload.status_token
        : null
      if (statusFromPayload && sigFromPayload)
        setStatusRedirect(statusFromPayload, sigFromPayload)
      const errorMessage = extractErrorMessage(err.data, baseErrMsg)
      setError(errorMessage)
      return { response: null, errorMessage, errorStatus: getAccessStatusFromError(errorMessage) }
    }
    finally {
      loading.value = false
    }
  }

  async function authorizeDevice(): Promise<boolean> {
    const { $api } = useNuxtApp()
    loading.value = true
    clearError()
    clearMessage()
    try {
      await $api('/users/me/devices/bind-current', { method: 'POST' })
      setMessage('Perangkat berhasil diotorisasi.')
      await fetchUser('login')
      return true
    }
    catch (err: any) {
      setError(extractErrorMessage(err.data, 'Gagal mengotorisasi perangkat.'))
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function logout(performRedirect: boolean = true) {
    const { $api } = useNuxtApp()
    const isAdminRoute = import.meta.client ? useRoute().path.startsWith('/admin') : false

    $api('/auth/logout', { method: 'POST' }).catch(() => {})

    setUser(null)
    initialAuthCheckDone.value = false
    if (performRedirect)
      lastKnownUser.value = null

    if (performRedirect && import.meta.client) {
      setMessage('Anda telah berhasil logout.')
      await navigateTo(isAdminRoute ? '/admin' : '/login', { replace: true })
    }
  }

  function getAccessStatusFromUser(inputUser: User | null): AccessStatus {
    if (inputUser == null)
      return 'ok'
    if (inputUser.is_blocked === true)
      return 'blocked'
    if (inputUser.is_active !== true || inputUser.approval_status !== 'APPROVED')
      return 'inactive'
    if (inputUser.is_unlimited_user === true)
      return 'ok'

    const total = inputUser.total_quota_purchased_mb ?? 0
    const used = inputUser.total_quota_used_mb ?? 0
    const remaining = total - used
    const expiryDate = inputUser.quota_expiry_date ? new Date(inputUser.quota_expiry_date) : null
    const isExpired = Boolean(expiryDate && expiryDate.getTime() < Date.now())
    const profileName = (inputUser.mikrotik_profile_name || '').toLowerCase()

    if (isExpired)
      return 'expired'
    if (total <= 0)
      return 'habis'
    if (total > 0 && remaining <= 0)
      return 'habis'
    if (profileName.includes('fup'))
      return 'fup'

    return 'ok'
  }

  function getAccessStatusFromError(errorText: string | null): AccessStatus | null {
    if (!errorText)
      return null

    const text = errorText.toLowerCase()
    if (text.includes('diblokir') || text.includes('blocked'))
      return 'blocked'
    if (text.includes('belum aktif') || text.includes('belum disetujui') || text.includes('not active'))
      return 'inactive'

    return null
  }

  function getRedirectPathForStatus(status: AccessStatus, context: 'login' | 'captive'): string | null {
    if (status === 'ok')
      return null

    const base = context === 'captive' ? '/captive' : '/login'
    const slugMap: Record<AccessStatus, string> = {
      ok: '',
      blocked: context === 'captive' ? 'blokir' : 'blocked',
      inactive: 'inactive',
      expired: 'expired',
      habis: 'habis',
      fup: 'fup',
    }
    return `${base}/${slugMap[status]}`
  }

  async function initializeAuth() {
    const route = useRoute()
    const context: 'login' | 'captive' = route.path.startsWith('/captive') ? 'captive' : 'login'
    const isGuestAuthRoute = route.path === '/login'
      || route.path.startsWith('/login/')
      || route.path === '/admin'
      || route.path === '/admin/login'

    const query = route.query ?? {}
    const clientIp = (query.client_ip ?? query.ip ?? query['client-ip']) as string | undefined
    const clientMac = (query.client_mac ?? query.mac ?? query['mac-address'] ?? query.mac_address) as string | undefined
    const linkLoginOnly = typeof query.link_login_only === 'string' ? query.link_login_only : undefined
    const hasCaptiveHints = Boolean(clientIp || clientMac || linkLoginOnly)

    const shouldAttemptAutoLogin = import.meta.client
      && user.value == null
      && autoLoginAttempted.value !== true
      && !route.path.startsWith('/admin')
      && hasCaptiveHints

    if (initialAuthCheckDone.value === true && !shouldAttemptAutoLogin)
      return

    if (user.value == null && !isGuestAuthRoute) {
      await fetchUser(context)
    }

    if (user.value == null && shouldAttemptAutoLogin) {
      autoLoginAttempted.value = true
      try {
        const { $api } = useNuxtApp()
        const body: Record<string, string> = {}
        if (clientIp)
          body.client_ip = clientIp
        if (clientMac)
          body.client_mac = clientMac
        if (linkLoginOnly)
          body.link_login_only = linkLoginOnly

        const response = await $api<VerifyOtpResponse>('/auth/auto-login', {
          method: 'POST',
          ...(Object.keys(body).length > 0 ? { body } : {}),
        })
        if (response != null) {
          await fetchUser(context)
        }
      }
      catch {
        // Auto-login bersifat best-effort, tidak perlu error ke UI
      }
    }

    initialAuthCheckDone.value = true
  }

  return {
    user,
    lastKnownUser,
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
    setUser,
    setError,
    setMessage,
    clearSession,
    fetchUser,
    requestOtp,
    adminLogin,
    register,
    verifyOtp,
    verifyOtpForCaptive,
    consumeSessionToken,
    authorizeDevice,
    logout,
    initializeAuth,
    lastAuthErrorCode,
    lastStatusRedirect,
    getAccessStatusFromUser,
    getAccessStatusFromError,
    getRedirectPathForStatus,
    getStatusRedirectPath,
    setStatusRedirect,
    refreshSessionStatus,
  }
})
