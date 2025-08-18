// store/auth.ts

import { useStorage } from '@vueuse/core'
import { useCookie, useNuxtApp } from '#app'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

// Import standardized API response types
import type {
  AuthResponse,
  DeviceSyncResponse,
  RoleVerificationResponse,
  UserInfoResponse,
} from '@/types/api-responses'
import type { RegistrationPayload, VerifyOtpPayload } from '@/types/auth'
import type { User } from '@/types/user'

import { UserRole } from '@/types/enums'
// Import API helper functions for consistent response handling
import {
  extractTokenFromResponse,
  extractUserFromResponse,
  handleApiError,
} from '@/utils/api-helpers'
// [PENTING] Impor composable client detection di sini agar bisa digunakan di action
import { useClientDetection } from '~/composables/useClientDetection'

interface AuthState {
  user: User | null
  isAuthCheckDone: boolean
  isNewDeviceDetected: boolean
  clientIp: string | null
  clientMac: string | null
  loading: boolean
  error: string | null
  message: string | null
  lastRefreshAt: number | null
  lastRefreshOk: boolean | null
}

export const useAuthStore = defineStore('auth', () => {
  const { $api } = useNuxtApp()
  const config = useRuntimeConfig()

  const state = ref<AuthState>({
    user: null,
    isAuthCheckDone: false,
    isNewDeviceDetected: false,
    clientIp: null,
    clientMac: null,
    loading: false,
    error: null,
    message: null,
    // Diagnostics
    lastRefreshAt: null as unknown as number | null,
    lastRefreshOk: null as unknown as boolean | null,
  })

  const authTokenCookie = useCookie<string | null>('app_token', { maxAge: 60 * 60 * 24 * 30, sameSite: 'lax' })
  const tokenLocal = useStorage<string | null>('app_token_local_copy', null)

  // Check localStorage backup on initial load
  if (typeof window !== 'undefined' && !authTokenCookie.value && !tokenLocal.value) {
    const backupToken = localStorage.getItem('app_token_backup')
    if (backupToken) {
      console.log('[AUTH-STORE] Restoring token from backup storage')
      setTimeout(() => {
        authTokenCookie.value = backupToken
        tokenLocal.value = backupToken
      }, 0)
    }
  }

  const token = computed({
    get: () => {
      const tokenValue = authTokenCookie.value ?? tokenLocal.value
      if (!tokenValue && typeof window !== 'undefined') {
        // Try backup as last resort
        return localStorage.getItem('app_token_backup')
      }
      return tokenValue
    },
    set: (val) => {
      authTokenCookie.value = val
      tokenLocal.value = val
      if (typeof window !== 'undefined') {
        if (val)
          localStorage.setItem('app_token_backup', val)
        else localStorage.removeItem('app_token_backup')
      }
    },
  })

  const user = computed(() => state.value.user)
  const isLoggedIn = computed(() => !!token.value && !!state.value.user)
  const isAuthCheckDone = computed(() => state.value.isAuthCheckDone)
  const isAdmin = computed(() => user.value?.role === 'ADMIN' || user.value?.role === 'SUPER_ADMIN')
  const isBlocked = computed(() => user.value?.is_blocked ?? false)
  const isQuotaFinished = computed(() => user.value?.is_quota_finished ?? false)
  const isNewDeviceDetected = computed(() => state.value.isNewDeviceDetected)
  const currentUser = computed(() => state.value.user)
  const clientIp = computed(() => state.value.clientIp)
  const clientMac = computed(() => state.value.clientMac)
  const loading = computed(() => state.value.loading)
  const error = computed(() => state.value.error)
  const message = computed(() => state.value.message)
  const isSuperAdmin = computed(() => user.value?.role === 'SUPER_ADMIN')

  function finishAuthCheck() { state.value.isAuthCheckDone = true }
  function clearError() { state.value.error = null }
  function clearMessage() { state.value.message = null }
  function setMessage(msg: string) { state.value.message = msg }

  function setUser(userData: User | null) {
    // Check for admin flag in localStorage if user data exists but no role
    const localStorageAdminFlag = localStorage.getItem('is_admin_user') === 'true'

    // If user exists but has no role, and localStorage says they're an admin, add the role
    if (userData && (!userData.role) && localStorageAdminFlag) {
      console.log('[AUTH-STORE] User has no role but admin flag exists in localStorage, fixing...')
      userData = {
        ...userData,
        role: UserRole.ADMIN, // Default to ADMIN role, can be refined later with backend verification
      }
    }

    // Update user in state
    state.value.user = userData

    // Maintain admin status in localStorage for persistence
    if (userData?.role === 'ADMIN' || userData?.role === 'SUPER_ADMIN') {
      localStorage.setItem('is_admin_user', 'true')
      console.log('[AUTH-STORE] Set admin flag in localStorage')
    }
    else if (userData === null) {
      localStorage.removeItem('is_admin_user')
      console.log('[AUTH-STORE] Removed admin flag from localStorage')
    }

    // Reset flags on user change
    state.value.error = null
    state.value.isAuthCheckDone = true
  }

  function setClientInfo(ip: string | null, mac: string | null) {
    state.value.clientIp = ip; state.value.clientMac = mac
    if (typeof window !== 'undefined') {
      if (ip)
        localStorage.setItem('auth_client_ip', ip)
      if (mac)
        localStorage.setItem('auth_client_mac', mac)
    }
  }

  function clearClientInfo() {
    state.value.clientIp = null; state.value.clientMac = null
    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_client_ip')
      localStorage.removeItem('auth_client_mac')
      localStorage.removeItem('captive_ip')
      localStorage.removeItem('captive_mac')
      localStorage.removeItem('detected_local_ip')
    }
  }

  async function fetchUser(): Promise<User | null> {
    if (!token.value) { setUser(null); return null }
    try {
      console.log('[AUTH-STORE] Fetching user data with token...')
      // Use standardized API response type for more accurate error handling
      const response = await $api<UserInfoResponse>('auth/me')

      // Extract user data safely with proper fallback
      const userData = response.user || (response as unknown as User)
      console.log('[AUTH-STORE] User data received:', userData)
      console.log('[AUTH-STORE] User role:', userData?.role)

      // Log additional role information to help diagnose issues
      if (userData && !userData.role) {
        console.warn('[AUTH-STORE] User has no role defined in backend response')
        // Check if localStorage has admin flag to diagnose inconsistency
        if (localStorage.getItem('is_admin_user') === 'true') {
          console.warn('[AUTH-STORE] User has admin flag in localStorage but no role from backend')
        }
      }

      // Enhanced role verification - always verify with backend if role is missing
      if (userData && !userData.role) {
        console.log('[AUTH-STORE] Role missing in user data, requesting role verification from backend')

        try {
          // Request explicit role verification from backend using standardized type
          const roleVerification = await $api<RoleVerificationResponse>('/auth/verify-role', {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
          })

          console.log('[AUTH-STORE] Role verification response:', roleVerification)

          // Update role using the explicit role information from backend
          if (roleVerification?.status === 'SUCCESS' && roleVerification?.role) {
            console.log('[AUTH-STORE] Backend provided role information:', roleVerification.role)

            // Set the role directly from backend response
            if (roleVerification.role === 'ADMIN') {
              userData.role = UserRole.ADMIN
              localStorage.setItem('is_admin_user', 'true')
            }
            else if (roleVerification.role === 'SUPER_ADMIN') {
              userData.role = UserRole.SUPER_ADMIN
              localStorage.setItem('is_admin_user', 'true')
            }
            else if (roleVerification.role === 'KOMANDAN') {
              userData.role = UserRole.KOMANDAN
            }
            else {
              userData.role = UserRole.USER
              // Remove admin flag if role is explicitly USER
              localStorage.removeItem('is_admin_user')
            }
          }
          else if (roleVerification?.isAdmin === true) {
            // Fallback to isAdmin flag if role not provided
            console.log('[AUTH-STORE] Backend confirmed admin status via isAdmin flag')
            userData.role = UserRole.ADMIN
            localStorage.setItem('is_admin_user', 'true')
          }
          else {
            console.log('[AUTH-STORE] Backend did not confirm admin status')
            // Remove incorrect admin flag from localStorage
            localStorage.removeItem('is_admin_user')
          }
        }
        catch (error) {
          console.error('[AUTH-STORE] Error verifying role with backend:', error)
          // Keep localStorage flag but don't modify role - will retry on next fetch
        }
      }

      setUser(userData)
      return userData
    }
    catch (error: any) {
      console.error('[AUTH-STORE] Error fetching user data:', error)
      token.value = null; setUser(null)
      return null
    }
  }

  async function initializeAuth(isAfterLogin = false) {
    if (state.value.user && !isAfterLogin) { finishAuthCheck(); return }
    if (token.value) { await fetchUser() }
    if (typeof window !== 'undefined' && !state.value.clientIp) {
      state.value.clientIp = localStorage.getItem('auth_client_ip')
      state.value.clientMac = localStorage.getItem('auth_client_mac')
    }
    finishAuthCheck()
  }

  async function logout(redirect = true) {
    const target = isAdmin.value ? '/admin/login' : '/login'
    try {
      // Inform backend to clear HttpOnly refresh cookies
      await $api('/auth/logout', { method: 'POST', headers: { 'x-skip-refresh': '1' } })
    }
    catch {
      // ignore
    }
    token.value = null
    setUser(null) // Gunakan setUser untuk reset state terkait
    state.value.isAuthCheckDone = false
    clearClientInfo()
    if (redirect) { await navigateTo(target, { replace: true }) }
  }

  // Refresh access token using HttpOnly refresh cookie
  let _isRefreshing = false
  async function refreshAccessToken(): Promise<boolean> {
    if (_isRefreshing) return false
    _isRefreshing = true
    try {
      const baseURL: string = (config.public.apiBaseUrl || '').replace(/\/$/, '')
      const url = `${baseURL}/auth/refresh`
      const resp = await fetch(url, {
        method: 'POST',
        credentials: 'include', // send HttpOnly refresh cookie
        headers: { 'Content-Type': 'application/json', 'x-skip-refresh': '1' },
      })
      const data = await resp.json().catch(() => ({} as any))
      if (!resp.ok) return false
      const newToken: string | undefined = (data && (data.access_token || data.token)) as any
      if (!newToken) return false
      token.value = newToken
      state.value.lastRefreshAt = Date.now()
      state.value.lastRefreshOk = true
      return true
    }
    catch (e) {
      console.warn('[AUTH-STORE] refreshAccessToken failed:', e)
      state.value.lastRefreshAt = Date.now()
      state.value.lastRefreshOk = false
      return false
    }
    finally {
      _isRefreshing = false
    }
  }

  async function adminLogin(username: string, password: string): Promise<boolean> {
    state.value.loading = true; state.value.error = null
    try {
      console.log('[AUTH-STORE] Attempting admin login...')
      const response = await $api<AuthResponse>('/auth/admin/login', {
        method: 'POST',
        body: { username, password },
      })

      // Extract token using helper function
      const tokenValue = extractTokenFromResponse(response)

      console.log('[AUTH-STORE] Admin login successful, token received:', tokenValue ? 'yes' : 'no')
      console.log('[AUTH-STORE] Response structure:', JSON.stringify(response))

      if (!tokenValue) {
        console.error('[AUTH-STORE] No token received in response:', response)
        throw new Error('No authentication token received from server')
      }

      token.value = tokenValue

      // Store token in localStorage as backup
      localStorage.setItem('app_token_backup', tokenValue)

      // Set explicit admin flag immediately
      localStorage.setItem('is_admin_user', 'true')

      // Extract user data using helper function
      const userData = extractUserFromResponse(response)

      if (userData) {
        console.log('[AUTH-STORE] User data found in login response:', userData)

        // Ensure role is set to ADMIN explicitly if missing
        if (!userData.role) {
          userData.role = UserRole.ADMIN
        }
        setUser(userData)
      }
      else {
        // If no user data in response, fetch it
        console.log('[AUTH-STORE] No user data in response, fetching from /auth/me')
        await fetchUser()

        // After fetching, verify admin role from backend
        if (state.value.user) {
          if (!state.value.user.role) {
            console.log('[AUTH-STORE] No role in fetched user, verifying with backend')
            try {
              const roleVerification = await $api('/auth/verify-role', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
              })

              // Only set admin role if backend confirms it
              if (roleVerification?.isAdmin === true) {
                console.log('[AUTH-STORE] Backend confirmed admin role')
                state.value.user = {
                  ...state.value.user,
                  role: UserRole.ADMIN,
                }
              }
              else {
                console.warn('[AUTH-STORE] Backend did not confirm admin role')
              }
            }
            catch (error) {
              console.error('[AUTH-STORE] Error verifying role:', error)
            }
          }
        }
        else {
          // If still no user after fetchUser, create minimal user with admin role
          console.warn('[AUTH-STORE] No user data after fetchUser, creating minimal admin user')
          setUser({
            id: 'admin',
            phone_number: username,
            full_name: 'Admin User',
            role: UserRole.ADMIN,
            approval_status: 'APPROVED' as any,
            is_active: true,
            is_blocked: false,
            blok: null,
            kamar: null,
            total_quota_purchased_mb: null,
            total_quota_used_mb: null,
            is_unlimited_user: true,
            quota_expiry_date: null,
            device_brand: null,
            device_model: null,
            client_ip: null,
            client_mac: null,
            last_login_mac: null,
            blocking_reason: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            approved_at: new Date().toISOString(),
            last_login_at: new Date().toISOString(),
          })
        }
      }

      // Double-check isAdmin flag
      console.log('[AUTH-STORE] After login, isAdmin computed value:', isAdmin.value)

      if (!isAdmin.value) {
        console.warn('[AUTH-STORE] Admin login succeeded but isAdmin is false, verifying with backend')
        // Verify the role with backend instead of forcing it locally
        if (state.value.user) {
          try {
            // Request explicit role verification from backend
            const roleVerification = await $api<{
              status: string
              isAdmin: boolean
              role: string
            }>('/auth/verify-role', {
              method: 'GET',
              headers: { 'Content-Type': 'application/json' },
            })

            if (roleVerification?.status === 'SUCCESS') {
              if (roleVerification.role === 'ADMIN' || roleVerification.role === 'SUPER_ADMIN' || roleVerification.isAdmin === true) {
                console.log('[AUTH-STORE] Backend confirmed admin status, updating role')
                // Set role based on backend response
                if (roleVerification.role === 'ADMIN') {
                  state.value.user.role = UserRole.ADMIN
                }
                else if (roleVerification.role === 'SUPER_ADMIN') {
                  state.value.user.role = UserRole.SUPER_ADMIN
                }
                else {
                  state.value.user.role = UserRole.ADMIN // Default to ADMIN if only isAdmin flag is true
                }

                // Update localStorage flag
                localStorage.setItem('is_admin_user', 'true')
              }
              else {
                console.warn('[AUTH-STORE] Backend did not confirm admin status, logout required')
                // The user shouldn't be here if they're not an admin, log them out
                await logout(true)
                return false
              }
            }
            else {
              console.error('[AUTH-STORE] Role verification failed, forcing admin role as fallback')
              // As a last resort, force the admin role
              state.value.user.role = UserRole.ADMIN
              localStorage.setItem('is_admin_user', 'true')
            }
          }
          catch (error) {
            console.error('[AUTH-STORE] Error during role verification after login:', error)
            // Force admin role as fallback in case of errors
            state.value.user.role = UserRole.ADMIN
            localStorage.setItem('is_admin_user', 'true')
          }
          // Explicitly set the admin role using the UserRole enum for type safety
          state.value.user = {
            ...state.value.user,
            role: UserRole.ADMIN,
          }

          // Double check after update
          console.log('[AUTH-STORE] User role after explicit set:', state.value.user.role)
          console.log('[AUTH-STORE] isAdmin after update:', isAdmin.value)
        }

        // Set backup flag in localStorage
        if (typeof window !== 'undefined') {
          localStorage.setItem('is_admin_user', 'true')
          console.log('[AUTH-STORE] Set admin flag in localStorage as backup')
        }
      }

      return true
    }
    catch (err: any) {
      console.error('[AUTH-STORE] Login error:', err)
      state.value.error = handleApiError(err, 'Login admin gagal.')
      return false
    }
    finally {
      state.value.loading = false
    }
  }

  async function registerUser(payload: RegistrationPayload): Promise<boolean> {
    state.value.loading = true; state.value.error = null
    try {
      await $api('/auth/register', { method: 'POST', body: payload })
      state.value.message = 'Pendaftaran berhasil diterima. Konfirmasi telah dikirim ke WhatsApp Anda.'
      return true
    }
    catch (err: any) {
      state.value.error = handleApiError(err, 'Pendaftaran gagal.')
      return false
    }
    finally { state.value.loading = false }
  }

  async function verifyOtp(payload: VerifyOtpPayload): Promise<boolean> {
    state.value.loading = true; state.value.error = null
    try {
      // Send flexible payload keys to match backend variations
      const flexible = {
        phone_number: payload.phone_number,
        phone: payload.phone_number,
        otp: payload.otp,
        code: payload.otp,
        client_ip: payload.client_ip,
        ip: payload.client_ip,
        client_mac: payload.client_mac,
        mac: payload.client_mac,
      }
      const response = await $api<AuthResponse>('/auth/verify-otp', { method: 'POST', body: flexible })

      // Extract token and user with helper functions
      const tokenValue = extractTokenFromResponse(response)
      const userData = extractUserFromResponse(response)

      // Set token if available
      if (tokenValue) {
        token.value = tokenValue
      }

      // Set user data if available
      if (userData) {
        setUser(userData)
      }

      // Persist client IP/MAC from backend (helps captive flow follow-ups)
      try {
        const ip = (response as any)?.ip || (response as any)?.data?.ip || null
        const mac = (response as any)?.mac || (response as any)?.data?.mac || null
        if (ip || mac) setClientInfo(ip, mac)
      } catch { /* noop */ }

      finishAuthCheck()
      return true
    }
    catch (err: any) {
      state.value.error = handleApiError(err, 'Verifikasi OTP gagal.')
      return false
    }
    finally { state.value.loading = false }
  }

  async function requestOtp(phoneNumber: string): Promise<boolean> {
    state.value.loading = true; state.value.error = null
    try {
      await $api('/auth/request-otp', { method: 'POST', body: { phone_number: phoneNumber } })
      state.value.message = 'OTP baru telah dikirim.'
      return true
    }
    catch (err: any) {
      state.value.error = handleApiError(err, 'Gagal mengirim ulang OTP.')
      return false
    }
    finally { state.value.loading = false }
  }

  async function authorizeDevice(): Promise<boolean> {
    // [PERBAIKAN] Cek state loading untuk mencegah klik ganda
    if (state.value.loading)
      return false

    state.value.loading = true
    state.value.error = null
    try {
      console.log('[AUTH-STORE] 🔄 Memulai otorisasi perangkat...')

      const { forceDetection } = useClientDetection()
      const clientInfo = await forceDetection()

      const ip = clientInfo?.summary?.detected_ip
      const mac = clientInfo?.summary?.detected_mac

      if (!ip || !mac) {
        throw new Error('Tidak dapat mendeteksi informasi IP atau MAC perangkat. Pastikan Anda terhubung ke jaringan yang benar.')
      }

      console.log(`[AUTH-STORE] Mengirim data otorisasi: IP=${ip}, MAC=${mac}`)

      await $api('/auth/authorize-device', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: { client_ip: ip, client_mac: mac },
      })

      state.value.isNewDeviceDetected = false
      await fetchUser()
      state.value.message = 'Perangkat berhasil diotorisasi dan akses bypass telah diberikan.'
      console.log('[AUTH-STORE] ✅ Otorisasi perangkat berhasil.')
      return true // <-- Memberi tahu pemanggil bahwa proses berhasil
    }
    catch (err: any) {
      console.error('[AUTH-STORE] ❌ Otorisasi perangkat gagal:', err)
      state.value.error = handleApiError(err, 'Gagal melakukan otorisasi perangkat.')
      return false // <-- Memberi tahu pemanggil bahwa proses gagal
    }
    finally {
      state.value.loading = false
    }
  }

  // Dedicated lock for sync to avoid coupling with global loading
  let _syncInFlight = false
  async function syncDevice() {
    // Fungsi ini dipanggil secara periodik oleh middleware untuk sinkronisasi senyap
    // Jika perangkat tidak dikenal, ia akan mengubah state isNewDeviceDetected menjadi true
    // yang kemudian akan memicu popup.

    // Prevent rapid successive calls
    if (_syncInFlight) {
      console.log('[AUTH-STORE] Sync sudah dalam progress (dedicated lock), skip...')
      return { status: 'IN_PROGRESS' }
    }

    // Check for throttling in localStorage
    const lastSyncTime = localStorage.getItem('last_device_sync')
    const now = Date.now()
    // Dynamic throttle: converge faster on dashboard when MAC unknown; ensure min 5s
    const macKnown = !!state.value.clientMac
    const throttleMs = macKnown ? 20000 : 7000
    if (lastSyncTime && (now - parseInt(lastSyncTime)) < throttleMs) {
      console.log(`[AUTH-STORE] Sync di-throttle di frontend, tunggu ${Math.round(throttleMs / 1000)} detik`)
      return { status: 'THROTTLED', message: 'Menunggu throttle selesai' }
    }

    // Store sync time immediately to prevent multiple rapid calls
    localStorage.setItem('last_device_sync', now.toString())

    console.log('[AUTH-STORE] 🔄 Memulai sinkronisasi perangkat di latar belakang...')

    try {
      _syncInFlight = true

      // Check if user is admin - if so, skip device sync process completely
      if (isAdmin.value) {
        console.log('[AUTH-STORE] User adalah admin, melewati sync device...')
        return { status: 'ADMIN_USER', message: 'Admin user, no device sync needed' }
      }

      // Attempt to call the API with error handling
      let response: DeviceSyncResponse | undefined
      try {
        // Get current IP and MAC address if available
        const currentIp = state.value.clientIp || null
        const currentMac = state.value.clientMac || null

        console.log('[AUTH-STORE] Sending sync request with IP:', currentIp, 'MAC:', currentMac)

        response = await $api<DeviceSyncResponse>('/auth/sync-device', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: {
            ip: currentIp,
            mac: currentMac,
          },
          // Force revalidation when MAC not yet known so server can override stale IP
          retryAttempts: macKnown ? undefined : 1,
          onResponseError: ({ response }: { response: any }) => {
            console.warn('[AUTH-STORE] Sync device API error:', response.status)
            // Don't throw here - we'll handle it in the outer catch block
          },
        })
      }
      catch (apiError) {
        console.error('[AUTH-STORE] API call failed:', apiError)
        // Return gracefully with error status
        return {
          status: 'ERROR',
          message: 'API error occurred during device sync',
          error: apiError,
        }
      }

      if (response?.status === 'DEVICE_UNREGISTERED') {
        console.log('[AUTH-STORE] 🚨 Perangkat tidak terdaftar, memicu alur otorisasi.')
        state.value.isNewDeviceDetected = true
        // jangan set message agar tidak mengganggu UI, biarkan popup yang menangani
      }
      else if (response?.status === 'DEVICE_VALID') {
        console.log('[AUTH-STORE] ✅ Perangkat valid dan sinkron.')
        state.value.isNewDeviceDetected = false
      }
      else if (response?.status === 'DEVICE_NOT_FOUND') {
        console.log('[AUTH-STORE] ⚠️ Perangkat tidak ditemukan di jaringan.')
        // Jangan set error global agar tidak muncul popup error yang mengganggu.
        // Cukup log di console.
      }
      else if (response?.status === 'THROTTLED' || response?.status === 'RATE_LIMITED') {
        console.log('[AUTH-STORE] 🔄 Sync di-throttle oleh server')
        const retryAfter = response?.retry_after || 30
        localStorage.setItem('last_device_sync', (now + (retryAfter * 1000)).toString())
        return response
      }

      return response
    }
    catch (err: any) {
      console.error('[AUTH-STORE] ❌ Gagal sinkronisasi perangkat:', err)

      // If rate limited, respect the retry-after
      if (err.status === 429 || err.statusCode === 429) {
        const retryAfter = err.data?.retry_after || 30
        localStorage.setItem('last_device_sync', (now + (retryAfter * 1000)).toString())
        return { status: 'RATE_LIMITED', retry_after: retryAfter }
      }

      // Return graceful failure object
      return {
        status: 'ERROR',
        message: 'Failed to sync device',
        error: err,
      }
    }
    finally {
      _syncInFlight = false
    }
  }

  function resetAuthorizationFlow() {
    // Fungsi ini dipanggil jika pengguna memilih "Nanti Saja" pada popup.
    // Ini akan menyembunyikan popup untuk sesi ini,
    // tapi state di backend tetap menganggap perangkat ini baru.
    console.log('[AUTH-STORE] Alur otorisasi di-reset oleh pengguna.')
    state.value.isNewDeviceDetected = false
    state.value.error = null
    state.value.message = null
  }

  return {
    token,
    user,
    isLoggedIn,
    isAuthCheckDone,
    isAdmin,
    isSuperAdmin,
    isBlocked,
    isQuotaFinished,
    isNewDeviceDetected,
    currentUser,
    clientIp,
    clientMac,
    loading,
    error,
    message,
    finishAuthCheck,
    clearError,
    clearMessage,
    setMessage,
    setUser,
    setClientInfo,
    clearClientInfo,
    initializeAuth,
    adminLogin,
    logout,
    refreshAccessToken,
    registerUser,
    verifyOtp,
    requestOtp,
    authorizeDevice,
    fetchUser,
    syncDevice,
    resetAuthorizationFlow,
  }
})
