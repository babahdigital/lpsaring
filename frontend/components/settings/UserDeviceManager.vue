<!-- components/settings/UserDeviceManager.vue -->
<script>
export default {
  name: 'UserDeviceManager',

  data() {
    return {
      devices: [],
      loading: false,
      error: null,
      headers: [
        { text: 'Perangkat', value: 'device_name', sortable: true },
        { text: 'Alamat MAC', value: 'mac_address', sortable: false },
        { text: 'IP Terakhir', value: 'last_ip', sortable: false },
        { text: 'Terakhir Digunakan', value: 'last_used_at', sortable: true },
        { text: 'Status', value: 'is_authorized', sortable: true },
        { text: 'Tindakan', value: 'actions', sortable: false },
      ],
      showConfirmDialog: false,
      selectedDevice: null,
      removingDevice: false,
      removingId: null,
    }
  },

  mounted() {
    this.loadDevices()
  },

  methods: {
    async loadDevices() {
      this.loading = true
      this.error = null

      try {
        const response = await this.$api.auth.getUserDevices()

        if (response.status === 'SUCCESS') {
          this.devices = response.devices
        }
        else {
          this.error = 'Gagal memuat data perangkat'
        }
      }
      catch (error) {
        console.error('Failed to load devices:', error)
        this.error = `Gagal memuat data perangkat: ${error.message || 'Terjadi kesalahan'}`
      }
      finally {
        this.loading = false
      }
    },

    getDeviceIcon(deviceName) {
      if (!deviceName)
        return 'mdi-devices'

      const name = deviceName.toLowerCase()

      if (name.includes('iphone') || name.includes('ipad'))
        return 'mdi-apple'
      if (name.includes('android')) {
        if (name.includes('phone'))
          return 'mdi-cellphone'
        if (name.includes('tablet'))
          return 'mdi-tablet'
        return 'mdi-android'
      }
      if (name.includes('windows'))
        return 'mdi-microsoft-windows'
      if (name.includes('mac'))
        return 'mdi-laptop-mac'
      if (name.includes('linux'))
        return 'mdi-linux'

      return 'mdi-devices'
    },

    formatDate(dateStr) {
      if (!dateStr)
        return '—'

      const date = new Date(dateStr)

      // Format as DD/MM/YYYY HH:MM
      const day = String(date.getDate()).padStart(2, '0')
      const month = String(date.getMonth() + 1).padStart(2, '0')
      const year = date.getFullYear()
      const hours = String(date.getHours()).padStart(2, '0')
      const minutes = String(date.getMinutes()).padStart(2, '0')

      return `${day}/${month}/${year} ${hours}:${minutes}`
    },

    confirmRemove(device) {
      this.selectedDevice = device
      this.showConfirmDialog = true
    },

    async removeDevice() {
      if (!this.selectedDevice)
        return

      this.removingDevice = true
      this.removingId = this.selectedDevice.id

      try {
        const response = await this.$api.auth.removeDevice(this.selectedDevice.id)

        if (response.status === 'SUCCESS') {
          // Remove from local list
          this.devices = this.devices.filter(d => d.id !== this.selectedDevice.id)
          this.$toast.success('Perangkat berhasil dihapus')
        }
        else {
          this.$toast.error('Gagal menghapus perangkat')
        }
      }
      catch (error) {
        console.error('Failed to remove device:', error)
        this.$toast.error(`Gagal menghapus perangkat: ${error.message || 'Terjadi kesalahan'}`)
      }
      finally {
        this.removingDevice = false
        this.showConfirmDialog = false
        this.selectedDevice = null
        this.removingId = null
      }
    },
  },
}
</script>

<template>
  <v-card>
    <v-card-title>
      <v-icon left>mdi-devices</v-icon>
      Perangkat Terdaftar
    </v-card-title>
    <v-card-subtitle>
      Kelola perangkat yang diizinkan mengakses akun Anda
    </v-card-subtitle>

    <v-card-text>
      <v-alert v-if="error" type="error" dismissible>
        {{ error }}
      </v-alert>

      <v-alert v-if="devices.length === 0" type="info" outlined>
        Anda belum memiliki perangkat terdaftar
      </v-alert>

      <v-data-table
        v-else
        :headers="headers"
        :items="devices"
        :loading="loading"
        item-key="id"
        class="elevation-1"
        dense
      >
        <!-- Device Name -->
        <template #item.device_name="{ item }">
          <div class="d-flex align-center">
            <v-icon left>
              {{ getDeviceIcon(item.device_name) }}
            </v-icon>
            {{ item.device_name }}
          </div>
        </template>

        <!-- Last Used -->
        <template #item.last_used_at="{ item }">
          {{ formatDate(item.last_used_at) }}
        </template>

        <!-- Status -->
        <template #item.is_authorized="{ item }">
          <v-chip
            :color="item.is_authorized ? 'success' : 'warning'"
            small
            text-color="white"
          >
            {{ item.is_authorized ? 'Diizinkan' : 'Ditangguhkan' }}
          </v-chip>
        </template>

        <!-- Actions -->
        <template #item.actions="{ item }">
          <v-btn
            color="error"
            icon
            small
            :disabled="loading || removingId === item.id"
            @click="confirmRemove(item)"
          >
            <v-icon small>
              mdi-delete
            </v-icon>
          </v-btn>
        </template>
      </v-data-table>
    </v-card-text>

    <!-- Confirmation Dialog -->
    <v-dialog v-model="showConfirmDialog" max-width="400px">
      <v-card>
        <v-card-title>Hapus Perangkat?</v-card-title>
        <v-card-text>
          <p>Anda akan menghapus akses untuk perangkat:</p>
          <p><strong>{{ selectedDevice?.device_name }}</strong></p>
          <p>Tindakan ini akan mencabut izin perangkat. Jika Anda ingin menggunakan perangkat ini lagi, Anda harus mengotorisasinya kembali.</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="showConfirmDialog = false">
            Batal
          </v-btn>
          <v-btn
            color="error"
            :loading="removingDevice"
            @click="removeDevice"
          >
            Hapus
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>
