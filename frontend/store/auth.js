// store/auth.js

export function state() {
  return {
    user: null,
    token: null,
    refreshToken: null,
    clientIp: null,
    clientMac: null,
    deviceRequiringAuth: null,
    isDeviceAuthModalVisible: false,
    error: null, // Add error state for handling authorization errors
  }
}

export const getters = {
  isAuthenticated: state => !!state.token,
  user: state => state.user,
  requiresDeviceAuth: state => !!state.deviceRequiringAuth,
  deviceAuthInfo: state => state.deviceRequiringAuth || {},
  // Getter for new device detection
  isNewDeviceDetected: state => !!state.deviceRequiringAuth,
}

export const mutations = {
  SET_USER(state, user) {
    state.user = user
  },
  SET_TOKEN(state, { token, refreshToken }) {
    state.token = token
    state.refreshToken = refreshToken
  },
  CLEAR_AUTH(state) {
    state.user = null
    state.token = null
    state.refreshToken = null
    state.deviceRequiringAuth = null
    state.error = null
  },
  SET_CLIENT_IP_MAC(state, { ip, mac }) {
    state.clientIp = ip
    state.clientMac = mac
  },
  SET_DEVICE_REQUIRING_AUTH(state, deviceInfo) {
    state.deviceRequiringAuth = deviceInfo
    state.isDeviceAuthModalVisible = !!deviceInfo
    if (!deviceInfo) {
      state.error = null
    }
  },
  SET_DEVICE_AUTH_MODAL_VISIBLE(state, visible) {
    state.isDeviceAuthModalVisible = visible
  },

  SET_ERROR(state, error) {
    state.error = error
  },
}

export const actions = {
  // Login action
  async login({ commit, dispatch }, { phone, password }) {
    try {
      const { token, refresh_token, user } = await this.$api.auth.login(phone, password)

      // Store tokens
      commit('SET_TOKEN', { token, refreshToken: refresh_token })
      commit('SET_USER', user)

      // Store in localStorage
      localStorage.setItem('token', token)
      localStorage.setItem('refresh_token', refresh_token)

      // Setup axios auth header
      this.$axios.setToken(token, 'Bearer')

      // Get client IP and MAC
      await dispatch('detectClientIpMac')

      // Sync device
      const syncResult = await dispatch('syncDevice')
      return syncResult
    }
    catch (error) {
      console.error('Login failed:', error)
      throw error
    }
  },

  // Detect client IP and MAC from network info
  async detectClientIpMac({ commit }) {
    try {
      // For IP, we'll rely on the server to detect it
      // For MAC, we need to implement a client-side detection method or rely on server
      const networkInfo = await this.$api.network.getClientInfo()

      commit('SET_CLIENT_IP_MAC', {
        ip: networkInfo.ip,
        mac: networkInfo.mac,
      })

      return networkInfo
    }
    catch (error) {
      console.error('Failed to detect client IP/MAC:', error)
      return null
    }
  },

  // Sync device with server
  async syncDevice({ state, commit }) {
    try {
      const response = await this.$api.auth.syncDevice(state.clientIp, state.clientMac)

      if (response.status === 'DEVICE_UNREGISTERED' && response.requires_explicit_authorization) {
        // Device requires authorization
        commit('SET_DEVICE_REQUIRING_AUTH', {
          ip: response.ip || state.clientIp,
          mac: response.mac || state.clientMac,
          userAgent: navigator.userAgent,
        })
        return {
          success: false,
          requiresAuth: true,
          message: response.message,
        }
      }

      if (response.status === 'DEVICE_VALID') {
        // Device is already authorized
        commit('SET_DEVICE_REQUIRING_AUTH', null)
        return {
          success: true,
          requiresAuth: false,
        }
      }

      // Handle other statuses
      return {
        success: false,
        requiresAuth: false,
        message: response.message,
      }
    }
    catch (error) {
      console.error('Failed to sync device:', error)
      return {
        success: false,
        requiresAuth: false,
        error: error.message,
      }
    }
  },

  // Authorize device
  async authorizeDevice({ state, commit, dispatch }) {
    try {
      if (!state.deviceRequiringAuth)
        return false

      const deviceName = getDeviceNameFromUserAgent(state.deviceRequiringAuth.userAgent)

      await this.$api.auth.authorizeDevice(
        state.deviceRequiringAuth.ip,
        state.deviceRequiringAuth.mac,
        deviceName,
      )

      // Clear device requiring auth
      commit('SET_DEVICE_REQUIRING_AUTH', null)

      // Sync device again to confirm
      await dispatch('syncDevice')

      return true
    }
    catch (error) {
      console.error('Failed to authorize device:', error)
      commit('SET_ERROR', error.message || 'Failed to authorize device')
      return false
    }
  },

  // Reset device authorization flow
  resetAuthorizationFlow({ commit }) {
    commit('SET_DEVICE_REQUIRING_AUTH', null)
    commit('SET_ERROR', null)
  },

  // Load user data from stored token
  async loadUser({ commit, dispatch }) {
    try {
      const token = localStorage.getItem('token')
      const refreshToken = localStorage.getItem('refresh_token')

      if (!token || !refreshToken)
        return false

      // Set token in store and axios
      commit('SET_TOKEN', { token, refreshToken })
      this.$axios.setToken(token, 'Bearer')

      // Get user profile
      const user = await this.$api.auth.getProfile()
      commit('SET_USER', user)

      // Get client IP and MAC
      await dispatch('detectClientIpMac')

      // Sync device
      await dispatch('syncDevice')

      return true
    }
    catch (error) {
      console.error('Failed to load user:', error)
      dispatch('logout')
      return false
    }
  },

  // Logout
  logout({ commit }) {
    try {
      // Try to call logout API
      this.$api.auth.logout().catch(e => console.error('Logout API error:', e))
    }
    finally {
      // Clear local storage
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')

      // Clear store state
      commit('CLEAR_AUTH')

      // Remove axios token
      this.$axios.setToken(false)
    }
  },
}

// Helper function to get device name from user agent
function getDeviceNameFromUserAgent(userAgent) {
  if (!userAgent)
    return 'Unknown Device'

  const ua = userAgent.toLowerCase()
  let deviceName = 'Unknown'

  // Detect device type
  if (ua.includes('iphone')) {
    deviceName = 'iPhone'
  }
  else if (ua.includes('ipad')) {
    deviceName = 'iPad'
  }
  else if (ua.includes('android')) {
    deviceName = ua.includes('mobile') ? 'Android Phone' : 'Android Tablet'
  }
  else if (ua.includes('windows')) {
    deviceName = 'Windows PC'
  }
  else if (ua.includes('macintosh') || ua.includes('mac os')) {
    deviceName = 'Mac'
  }
  else if (ua.includes('linux')) {
    deviceName = 'Linux'
  }

  // Add browser info
  if (ua.includes('chrome'))
    deviceName += ' - Chrome'
  else if (ua.includes('firefox'))
    deviceName += ' - Firefox'
  else if (ua.includes('safari'))
    deviceName += ' - Safari'
  else if (ua.includes('edge'))
    deviceName += ' - Edge'
  else if (ua.includes('opera'))
    deviceName += ' - Opera'

  return deviceName
}
