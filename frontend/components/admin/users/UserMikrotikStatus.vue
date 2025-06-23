// frontend/components/admin/users/UserMikrotikStatus.vue
<script lang="ts" setup>
import { useNuxtApp } from '#app'
import { ref } from 'vue'

const props = defineProps<{
  userId: string
}>()

const { $api } = useNuxtApp()

const loading = ref(false)
const statusData = ref<any>(null)
const errorMsg = ref<string | null>(null)

async function checkStatus() {
  loading.value = true
  statusData.value = null
  errorMsg.value = null
  try {
    const response = await $api<any>(`/admin/users/${props.userId}/mikrotik-status`)
    statusData.value = response
  }
  catch (error: any) {
    console.error('Gagal mengambil status Mikrotik:', error)
    errorMsg.value = error.statusMessage || error.data?.message || 'Gagal mengambil data dari server.'
  }
  finally {
    loading.value = false
  }
}

// Helper untuk format data
function formatBytes(bytes: number | string, decimals = 2) {
  if (typeof bytes === 'string')
    bytes = Number.parseInt(bytes, 10)
  if (bytes === 0 || !bytes)
    return '0 Bytes'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${Number.parseFloat((bytes / k ** i).toFixed(dm))} ${sizes[i]}`
}
</script>

<template>
  <div>
    <div class="d-flex align-center gap-4 mb-4">
      <h6 class="text-h6">
        Status Live Mikrotik
      </h6>
      <VBtn
        color="primary"
        variant="tonal"
        size="small"
        prepend-icon="tabler-refresh"
        :loading="loading"
        @click="checkStatus"
      >
        Cek Status
      </VBtn>
    </div>
    <VDivider />

    <VCard
      variant="tonal"
      class="mt-4"
    >
      <VCardText>
        <VAlert
          v-if="errorMsg"
          type="error"
          variant="tonal"
          class="mb-4"
        >
          {{ errorMsg }}
        </VAlert>

        <VAlert
          v-if="!loading && statusData && !statusData.exists_on_mikrotik"
          type="warning"
          variant="tonal"
          class="mb-4"
        >
          Pengguna ini tidak ditemukan di MikroTik.
        </VAlert> <div
          v-if="loading"
          class="text-center pa-4"
        >
          <VProgressCircular
            indeterminate
            color="primary"
          />
          <p class="mt-2 text-disabled">
            Menghubungi MikroTik...
          </p>
        </div>

        <VList v-if="!loading && statusData && statusData.exists_on_mikrotik">
          <VListItem
            prepend-icon="tabler-user-check"
            title="Nama Hotspot"
            :subtitle="statusData.details.name"
          />
          <VListItem
            prepend-icon="tabler-shield-check"
            title="Profil"
            :subtitle="statusData.details.profile"
          />
          <VListItem
            prepend-icon="tabler-server-2"
            title="Server"
            :subtitle="statusData.details.server"
          />
          <VListItem
            prepend-icon="tabler-arrow-down-circle"
            title="Total Kuota Masuk"
            :subtitle="formatBytes(statusData.details['bytes-in'])"
          />
          <VListItem
            prepend-icon="tabler-arrow-up-circle"
            title="Total Kuota Keluar"
            :subtitle="formatBytes(statusData.details['bytes-out'])"
          />
          <VListItem
            prepend-icon="tabler-clock"
            title="Limit Uptime"
            :subtitle="statusData.details['limit-uptime'] || 'Tidak diatur'"
          />
          <VListItem
            prepend-icon="tabler-database"
            title="Limit Kuota"
            :subtitle="statusData.details['limit-bytes-total'] ? formatBytes(statusData.details['limit-bytes-total']) : 'Tidak diatur'"
          />
        </VList>

        <div
          v-if="!loading && !statusData && !errorMsg"
          class="text-center text-disabled pa-4"
        >
          Klik tombol "Cek Status" untuk melihat data live dari MikroTik.
        </div>
      </VCardText>
    </VCard>
  </div>
</template>
