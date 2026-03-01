import type {
  ApiErrorEnvelope,
  AuthRegisterRequestContract,
  AuthRegisterResponseContract,
  AuthVerifyOtpResponseContract,
  UserMeResponseContract,
} from '~/types/api/contracts'
import { navigateTo, useNuxtApp, useRoute } from '#app'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { resolveAccessStatusFromUser } from '@/utils/authAccess'
import { getStatusRouteForAccessStatus, isLegalPublicPath } from '~/utils/authRoutePolicy'

type RegisterResponse = AuthRegisterResponseContract
type RegistrationPayload = AuthRegisterRequestContract
type User = UserMeResponseContract
type VerifyOtpResponse = AuthVerifyOtpResponseContract

function extractErrorMessage(errorData: ApiErrorEnvelope | any, defaultMessage: string): string {
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
  const LAST_MIKROTIK_LOGIN_HINT_KEY = 'lpsaring:last-mikrotik-login-link'
  const LAST_AUTOLOGIN_ATTEMPT_KEY = 'lpsaring:last-autologin-attempt'
  const AUTO_LOGIN_RETRY_COOLDOWN_MS = 20000

  const user = ref<User | null>(null)
  const lastKnownUser = ref<User | null>(null)
  const loading = ref(false)
  const loadingUser = ref(false)
  const error = ref<string | null>(null)
  const message = ref<string | null>(null)
  const initialAuthCheckDone = ref(false)
  const lastUserFetchAt = ref(0)
  const lastAuthErrorCode = ref<number | null>(null)
  const autoLoginAttempted = ref(false)
  const lastAutoLoginAttemptAt = ref(0)
  const lastAutoLoginAttemptSignature = ref('')
  const lastStatusRedirect = ref<{ status: AccessStatus; sig?: string | null } | null>(null)
  const logoutInProgress = ref(false)
  const resetLoginInProgress = ref(false)

  const isLoggedIn = computed(() => user.value != null)
  const currentUser = computed(() => user.value)
  const isAdmin = computed(() => user.value?.role === 'ADMIN' || user.value?.role === 'SUPER_ADMIN')
  const isSuperAdmin = computed(() => user.value?.role === 'SUPER_ADMIN')
  const isKomandan = computed(() => user.value?.role === 'KOMANDAN')
  const isUserApprovedAndActive = computed(() =>
    user.value != null && user.value.is_active === true && user.value.approval_status === 'APPROVED',
  )

  function getFirstQueryValue(query: Record<string, unknown>, keys: string[]): string {
    for (const key of keys) {
      const raw = query[key]
      const value = Array.isArray(raw) ? String(raw[0] ?? '').trim() : String(raw ?? '').trim()
      if (value.length > 0)
        return value
    }
    return ''
  }

  function decodeOnceSafe(input: string): string {
    try {
      return decodeURIComponent(input)
    }
    catch {
      return input
    }
  }

  function readMikrotikLoginHintFromRoute(query: Record<string, unknown>): string {
    const direct = getFirstQueryValue(query, ['link_login_only', 'link-login-only', 'link_login', 'link-login', 'linkloginonly'])
    if (direct.length > 0)
      return direct

    const redirectRaw = getFirstQueryValue(query, ['redirect'])
    if (!redirectRaw || !redirectRaw.includes('link_login_only='))
      return ''

    try {
      const parsed = new URL(redirectRaw, 'https://example.invalid')
      const nested = String(parsed.searchParams.get('link_login_only') ?? '').trim()
      if (nested.length > 0)
        return decodeOnceSafe(nested)
    }
    catch {
      const decoded = decodeOnceSafe(redirectRaw)
      const marker = 'link_login_only='
      const markerIndex = decoded.indexOf(marker)
      if (markerIndex >= 0) {
        const afterMarker = decoded.slice(markerIndex + marker.length)
        const endIndex = afterMarker.indexOf('&')
        return decodeOnceSafe((endIndex >= 0 ? afterMarker.slice(0, endIndex) : afterMarker).trim())
      }
    }

    return ''
  }

  function pickHotspotIdentityFromQuery(query: Record<string, unknown>): { clientIp: string, clientMac: string } {
    const clientIp = getFirstQueryValue(query, ['client_ip', 'ip', 'client-ip'])
    const clientMac = getFirstQueryValue(query, ['client_mac', 'mac', 'mac-address', 'client-mac'])
    return { clientIp, clientMac }
  }

  function rememberMikrotikLoginHint(link: string) {
    if (!import.meta.client)
      return
    const normalized = String(link ?? '').trim()
    if (normalized.length === 0)
      return
    try {
      sessionStorage.setItem(LAST_MIKROTIK_LOGIN_HINT_KEY, normalized)
    }
    catch {
      // ignore storage errors
    }
  }

  function getStoredMikrotikLoginHint(): string {
    if (!import.meta.client)
      return ''
    try {
      return String(sessionStorage.getItem(LAST_MIKROTIK_LOGIN_HINT_KEY) ?? '').trim()
    }
    catch {
      return ''
    }
  }

  function isIPhoneSafari(): boolean {
    if (!import.meta.client)
      return false
    const ua = String(window.navigator.userAgent ?? '')
    const isIphone = /iPhone/i.test(ua)
    const isSafari = /Safari/i.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/i.test(ua)
    return isIphone && isSafari
  }

  function shouldAvoidDirectExternalRedirect(target: URL): boolean {
    return isIPhoneSafari() && target.hostname.toLowerCase().endsWith('.local')
  }

  function resolveMikrotikLinkFromContext(
    query: Record<string, unknown>,
    runtimeConfig: ReturnType<typeof useRuntimeConfig>,
  ): string {
    const fromRoute = readMikrotikLoginHintFromRoute(query)
    if (fromRoute.length > 0)
      return fromRoute

    const fromStoredHint = getStoredMikrotikLoginHint()
    if (fromStoredHint.length > 0)
      return fromStoredHint

    const appLink = String(runtimeConfig.public.appLinkMikrotik ?? '').trim()
    if (appLink.length > 0)
      return appLink

    return String(runtimeConfig.public.mikrotikLoginUrl ?? '').trim()
  }

  function getAutoLoginAttemptSignature(routePath: string, clientIp: string, clientMac: string): string {
    return [routePath || '-', clientIp || '-', clientMac || '-'].join('|')
  }

  function rememberAutoLoginAttempt(signature: string) {
    const nowMs = Date.now()
    lastAutoLoginAttemptAt.value = nowMs
    lastAutoLoginAttemptSignature.value = signature

    if (!import.meta.client)
      return
    try {
      sessionStorage.setItem(LAST_AUTOLOGIN_ATTEMPT_KEY, JSON.stringify({ signature, at: nowMs }))
    }
    catch {
      // ignore storage errors
    }
  }

  function readStoredAutoLoginAttempt(): { signature: string, at: number } | null {
    if (!import.meta.client)
      return null
    try {
      const raw = sessionStorage.getItem(LAST_AUTOLOGIN_ATTEMPT_KEY)
      if (!raw)
        return null
      const parsed = JSON.parse(raw) as { signature?: unknown, at?: unknown }
      const signature = typeof parsed?.signature === 'string' ? parsed.signature : ''
      const at = Number(parsed?.at ?? 0)
      if (!signature || !Number.isFinite(at) || at <= 0)
        return null
      return { signature, at }
    }
    catch {
      return null
    }
  }

  function isAutoLoginRetryCoolingDown(signature: string): boolean {
    const nowMs = Date.now()
    if (lastAutoLoginAttemptSignature.value === signature && (nowMs - lastAutoLoginAttemptAt.value) < AUTO_LOGIN_RETRY_COOLDOWN_MS)
      return true

    const stored = readStoredAutoLoginAttempt()
    if (!stored)
      return false

    const isSameSignature = stored.signature === signature
    const isWithinCooldown = (nowMs - stored.at) < AUTO_LOGIN_RETRY_COOLDOWN_MS
    if (isSameSignature && isWithinCooldown) {
      lastAutoLoginAttemptSignature.value = stored.signature
      lastAutoLoginAttemptAt.value = stored.at
      return true
    }
    return false
  }

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
    lastUserFetchAt.value = 0
    if (reasonCode != null)
      lastAuthErrorCode.value = reasonCode
    else
      lastAuthErrorCode.value = null
    initialAuthCheckDone.value = true
  }

  async function fetchUser(context: 'login' | 'captive' = 'login', currentPath?: string): Promise<boolean> {
    const { $api } = useNuxtApp()
    loadingUser.value = true
    try {
      const fetchedUser = await $api<User>('/auth/me', { method: 'GET' })

      // PERBAIKAN: Pengecekan eksplisit
      if (fetchedUser != null && fetchedUser.id != null) {
        setUser(fetchedUser)
        lastUserFetchAt.value = Date.now()
        clearError()
        await enforceAccessStatus(context, currentPath)
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

  async function enforceAccessStatus(context: 'login' | 'captive' = 'login', currentPath?: string) {
    // Admin/Super Admin tidak boleh dikenai guard kuota/status end-user.
    // Jika data kuota admin di DB = 0 atau expired, jangan redirect ke halaman status/beli.
    if (isAdmin.value === true)
      return

    const status = getAccessStatusFromUser(user.value)
    if (status === 'ok')
      return
    if (import.meta.client) {
      const path = currentPath ?? useRoute().path
      if (isLegalPublicPath(path))
        return

      const redirectPath = getRedirectPathForStatus(status, context)
      const allowPurchasePaths = status === 'habis' || status === 'expired'
        ? ['/beli', '/payment/status', '/payment/finish', redirectPath]
        : [redirectPath]

      if (allowPurchasePaths.includes(path))
        return

      if (redirectPath)
        await navigateTo(redirectPath, { replace: true })
    }
  }

  async function refreshSessionStatus(currentPath?: string) {
    const ok = await fetchUser('login', currentPath)
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

  async function verifyOtp(
    phoneNumber: string,
    otpCode: string,
    clientInfo?: { clientIp?: string | null; clientMac?: string | null; hotspotLoginContext?: boolean | null },
  ): Promise<VerifyOtpResponse | null> {
    async function performVerifyOtp(): Promise<VerifyOtpResponse> {
      const { $api } = useNuxtApp()
      const payload = new URLSearchParams({ phone_number: phoneNumber, otp: otpCode })
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
    if (logoutInProgress.value)
      return

    logoutInProgress.value = true
    const { $api } = useNuxtApp()
    const shouldRedirectToAdminLogin = isAdmin.value === true

    // Penting: tunggu request logout selesai agar cookie auth/refresh benar-benar terhapus
    // sebelum kita redirect ke halaman yang punya guard (mis. /admin).
    try {
      await $api('/auth/logout', { method: 'POST' })
    }
    catch {
      // Jika gagal, tetap lanjut bersihkan state lokal agar user tidak "terkunci".
    }

    setUser(null)
    lastUserFetchAt.value = 0
    initialAuthCheckDone.value = false
    autoLoginAttempted.value = false
    lastStatusRedirect.value = null
    lastAuthErrorCode.value = null
    if (performRedirect)
      lastKnownUser.value = null

    try {
      if (performRedirect && import.meta.client) {
        const runtimeConfig = useRuntimeConfig()
        const route = useRoute()
        const routeQuery = (route?.query ?? {}) as Record<string, unknown>
        const routeLinkHint = readMikrotikLoginHintFromRoute(routeQuery)
        if (routeLinkHint.length > 0)
          rememberMikrotikLoginHint(routeLinkHint)
        const mikrotikLink = resolveMikrotikLinkFromContext(routeQuery, runtimeConfig)
        const { clientIp, clientMac } = pickHotspotIdentityFromQuery(routeQuery)
        if (!shouldRedirectToAdminLogin && mikrotikLink.length > 0) {
          const target = new URL(mikrotikLink, window.location.origin)
          if (clientIp)
            target.searchParams.set('client_ip', clientIp)
          if (clientMac)
            target.searchParams.set('client_mac', clientMac)

          rememberMikrotikLoginHint(target.toString())

          if (shouldAvoidDirectExternalRedirect(target)) {
            setMessage('iPhone Safari terdeteksi. Buka login hotspot secara manual dari tombol pada halaman berikutnya.')
            const queryParams = new URLSearchParams()
            if (clientIp)
              queryParams.set('client_ip', clientIp)
            if (clientMac)
              queryParams.set('client_mac', clientMac)
            const hotspotRequiredPath = queryParams.toString().length > 0
              ? `/login/hotspot-required?${queryParams.toString()}`
              : '/login/hotspot-required'
            await navigateTo(hotspotRequiredPath, { replace: true })
            return
          }

          window.location.assign(target.toString())

          // iOS Safari kadang tidak menjalankan redirect eksternal saat context tertentu.
          // Fallback: pastikan user tetap keluar ke halaman login portal.
          setTimeout(() => {
            void navigateTo('/login', { replace: true })
          }, 1200)
          return
        }

        setMessage('Anda telah berhasil logout.')
        if (shouldRedirectToAdminLogin) {
          await navigateTo('/admin', { replace: true })
          return
        }

        const queryParams = new URLSearchParams()
        if (clientIp)
          queryParams.set('client_ip', clientIp)
        if (clientMac)
          queryParams.set('client_mac', clientMac)
        const captivePath = queryParams.toString().length > 0
          ? `/captive?${queryParams.toString()}`
          : '/captive'
        await navigateTo(captivePath, { replace: true })
      }
    }
    finally {
      logoutInProgress.value = false
    }
  }

  async function resetLogin(): Promise<boolean> {
    if (resetLoginInProgress.value)
      return false

    resetLoginInProgress.value = true
    clearError()
    clearMessage()
    try {
      const { $api } = useNuxtApp()
      await $api('/auth/reset-login', { method: 'POST' })

      // Sinkronkan state klien segera setelah reset sesi server berhasil.
      clearSession(401)
      lastKnownUser.value = null

      if (import.meta.client) {
        const runtimeConfig = useRuntimeConfig()
        const route = useRoute()
        const routeQuery = (route?.query ?? {}) as Record<string, unknown>
        const routeLinkHint = readMikrotikLoginHintFromRoute(routeQuery)
        if (routeLinkHint.length > 0)
          rememberMikrotikLoginHint(routeLinkHint)
        const mikrotikLink = resolveMikrotikLinkFromContext(routeQuery, runtimeConfig)
        const { clientIp, clientMac } = pickHotspotIdentityFromQuery(routeQuery)
        if (mikrotikLink.length > 0) {
          const target = new URL(mikrotikLink, window.location.origin)
          if (clientIp)
            target.searchParams.set('client_ip', clientIp)
          if (clientMac)
            target.searchParams.set('client_mac', clientMac)

          rememberMikrotikLoginHint(target.toString())

          if (shouldAvoidDirectExternalRedirect(target)) {
            setMessage('iPhone Safari terdeteksi. Buka login hotspot secara manual dari tombol pada halaman berikutnya.')
            const queryParams = new URLSearchParams()
            if (clientIp)
              queryParams.set('client_ip', clientIp)
            if (clientMac)
              queryParams.set('client_mac', clientMac)
            const hotspotRequiredPath = queryParams.toString().length > 0
              ? `/login/hotspot-required?${queryParams.toString()}`
              : '/login/hotspot-required'
            await navigateTo(hotspotRequiredPath, { replace: true })
            return true
          }

          window.location.assign(target.toString())

          // Fallback khusus browser mobile (terutama iPhone) jika redirect eksternal tidak terjadi.
          setTimeout(() => {
            void navigateTo('/login', { replace: true })
          }, 1200)
          return true
        }

        const queryParams = new URLSearchParams()
        if (clientIp)
          queryParams.set('client_ip', clientIp)
        if (clientMac)
          queryParams.set('client_mac', clientMac)
        const captivePath = queryParams.toString().length > 0
          ? `/captive?${queryParams.toString()}`
          : '/captive'
        await navigateTo(captivePath, { replace: true })
        return true
      }

      setMessage('Reset login berhasil. Silakan login hotspot ulang jika diperlukan.')
      return true
    }
    catch (err: any) {
      setError(extractErrorMessage(err.data, 'Reset login gagal. Silakan coba lagi.'))
      return false
    }
    finally {
      resetLoginInProgress.value = false
    }
  }

  function getAccessStatusFromUser(inputUser: User | null): AccessStatus {
    if (inputUser == null)
      return 'ok'
    return resolveAccessStatusFromUser(inputUser)
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
    return getStatusRouteForAccessStatus(status, context)
  }

  async function initializeAuth(routeInfo?: { path: string; query?: Record<string, unknown> }) {
    const route = routeInfo ?? useRoute()
    const routePath = route?.path ?? ''
    const context: 'login' | 'captive' = routePath.startsWith('/captive') ? 'captive' : 'login'
    const query = (route as any)?.query ?? {}
    const mikrotikHint = readMikrotikLoginHintFromRoute(query as Record<string, unknown>)
    if (mikrotikHint.length > 0)
      rememberMikrotikLoginHint(mikrotikHint)

    const queryRecord = query as Record<string, unknown>
    const clientIp = getFirstQueryValue(queryRecord, ['client_ip', 'ip', 'client-ip'])
    const clientMac = getFirstQueryValue(queryRecord, ['client_mac', 'mac', 'mac-address', 'client-mac'])
    const hasIdentityHints = Boolean(clientIp || clientMac)
    const shouldAttemptAutoLoginForRoute = hasIdentityHints
    const autoLoginSignature = getAutoLoginAttemptSignature(routePath, clientIp, clientMac)
    const autoLoginCoolingDown = shouldAttemptAutoLoginForRoute && isAutoLoginRetryCoolingDown(autoLoginSignature)
    const shouldAttemptAutoLogin = import.meta.client
      && user.value == null
      && autoLoginAttempted.value !== true
      && shouldAttemptAutoLoginForRoute
      && autoLoginCoolingDown !== true

    if (initialAuthCheckDone.value === true && !shouldAttemptAutoLogin) {
      const staleAfterMs = 15000
      if (user.value != null && (Date.now() - lastUserFetchAt.value) > staleAfterMs)
        await fetchUser(context, routePath)
      return
    }

    try {
      if (user.value == null) {
        await fetchUser(context, routePath)
      }

      if (user.value == null && shouldAttemptAutoLogin) {
        autoLoginAttempted.value = true
        rememberAutoLoginAttempt(autoLoginSignature)
        try {
          if (!routePath.startsWith('/admin')) {
            const { $api } = useNuxtApp()
            const body: Record<string, string> = {}
            if (clientIp)
              body.client_ip = clientIp
            if (clientMac)
              body.client_mac = clientMac

            const response = await $api<VerifyOtpResponse>('/auth/auto-login', {
              method: 'POST',
              ...(Object.keys(body).length > 0 ? { body } : {}),
            })
            if (response != null) {
              await fetchUser(context, routePath)
            }
          }
        }
        catch {
          // Auto-login bersifat best-effort, tidak perlu error ke UI
        }
      }
    }
    finally {
      initialAuthCheckDone.value = true
    }
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
    resetLogin,
    initializeAuth,
    lastAuthErrorCode,
    lastStatusRedirect,
    resetLoginInProgress,
    getAccessStatusFromUser,
    getAccessStatusFromError,
    getRedirectPathForStatus,
    getStatusRedirectPath,
    setStatusRedirect,
    refreshSessionStatus,
  }
})
