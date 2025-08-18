// services/api/auth.service.js

export default $axios => ({
  /**
   * Login with phone number and password
   * @param {string} phone - Phone number
   * @param {string} password - User password
   * @returns {Promise} - API response
   */
  login(phone, password) {
    return $axios.$post('/api/auth/login', {
      phone,
      password,
    })
  },

  /**
   * Register a new user
   * @param {object} userData - User registration data
   * @returns {Promise} - API response
   */
  register(userData) {
    return $axios.$post('/api/auth/register', userData)
  },

  /**
   * Get current user profile
   * @returns {Promise} - API response with user data
   */
  getProfile() {
    return $axios.$get('/api/auth/profile')
  },

  /**
   * Refresh the JWT token
   * @returns {Promise} - API response with new token
   */
  refreshToken() {
    return $axios.$post('/api/auth/refresh')
  },

  /**
   * Sync device IP and MAC address
   * @param {string} clientIp - Client IP address
   * @param {string} clientMac - Client MAC address
   * @returns {Promise} - API response
   */
  syncDevice(clientIp, clientMac) {
    return $axios.$post('/api/auth/sync-device', {
      client_ip: clientIp,
      client_mac: clientMac,
    })
  },

  /**
   * Explicitly authorize a device for the current user
   * @param {string} ip - Device IP address
   * @param {string} mac - Device MAC address
   * @param {string} deviceName - Optional device name
   * @returns {Promise} - API response
   */
  authorizeDevice(ip, mac, deviceName = null) {
    return $axios.$post('/api/auth/authorize-device', {
      ip,
      mac,
      device_name: deviceName,
    })
  },

  /**
   * Log out the current user
   * @returns {Promise} - API response
   */
  logout() {
    return $axios.$post('/api/auth/logout')
  },

  /**
   * Get list of user's authorized devices
   * @returns {Promise} - API response with list of devices
   */
  getUserDevices() {
    return $axios.$get('/api/auth/devices')
  },

  /**
   * Remove device authorization
   * @param {string} deviceId - ID of the device to remove
   * @returns {Promise} - API response
   */
  removeDevice(deviceId) {
    return $axios.$delete(`/api/auth/devices/${deviceId}`)
  },
})
