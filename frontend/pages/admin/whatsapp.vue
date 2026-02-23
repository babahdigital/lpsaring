<script setup lang="ts">
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { computed, onMounted, ref, watch } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'
import { useAuthStore } from '@/store/auth'

interface UserRow {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
  created_at: string
}

type Options = InstanceType<typeof VDataTableServer>['options']

const { $api } = useNuxtApp()
const authStore = useAuthStore()
const { add: showSnackbar } = useSnackbar()

definePageMeta({
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
})

useHead({ title: 'WhatsApp Pengguna' })

const users = ref<UserRow[]>([])
const totalUsers = ref(0)
const loading = ref(false)
const hasLoadedOnce = ref(false)
const showInitialSkeleton = computed(() => loading.value === true && hasLoadedOnce.value === false)
const showSilentRefreshing = computed(() => loading.value === true && hasLoadedOnce.value === true)
const sendingTest = ref(false)
const sendingBroadcast = ref(false)
const testPhoneNumber = ref('')
const testMessage = ref('Tes WhatsApp dari panel admin hotspot.')
const broadcastRole = ref<'USER' | 'KOMANDAN'>('KOMANDAN')
const broadcastMessage = ref('')
const search = ref('')
const roleFilter = ref<string>('')
const options = ref<Options>({ page: 1, itemsPerPage: 10, sortBy: [{ key: 'created_at', order: 'desc' }] })

const roleOptions = computed(() => {
  const base = [
    { text: 'Semua', value: '' },
    { text: 'User', value: 'USER' },
    { text: 'Komandan', value: 'KOMANDAN' },
  ]
  if (authStore.isAdmin === true || authStore.isSuperAdmin === true)
    base.push({ text: 'Admin', value: 'ADMIN' })

  if (authStore.isSuperAdmin === true)
    base.push({ text: 'Support', value: 'SUPER_ADMIN' })

  return base
})

const headers = [
  { title: 'NAMA', key: 'full_name', sortable: true },
  { title: 'PERAN', key: 'role', sortable: true },
  { title: 'NO. HP', key: 'phone_number', sortable: false },
  { title: 'WHATSAPP', key: 'whatsapp', sortable: false },
  { title: 'TGL DAFTAR', key: 'created_at', sortable: true },
]

const roleLabels: Record<UserRow['role'], string> = {
  USER: 'User',
  KOMANDAN: 'Komandan',
  ADMIN: 'Admin',
  SUPER_ADMIN: 'Support',
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
}

function normalizeWaNumber(phone: string): string {
  if (!phone)
    return ''

  const raw = phone.replace(/[^\d+]/g, '')
  if (raw.startsWith('+'))
    return raw.slice(1).replace(/[^\d]/g, '')
  const digits = raw.replace(/[^\d]/g, '')
  if (digits.startsWith('62'))
    return digits
  if (digits.startsWith('0'))
    return `62${digits.slice(1)}`
  // Jika user sudah memasukkan country code non-62 tanpa '+', biarkan.
  return digits
}

function buildWaLink(phone: string): string {
  const number = normalizeWaNumber(phone)
  if (!number)
    return '#'
  return `https://wa.me/${number}`
}

async function sendTestMessage() {
  const normalized = normalizeWaNumber(testPhoneNumber.value)
  if (!normalized) {
    showSnackbar({ type: 'warning', title: 'Nomor Tidak Valid', text: 'Masukkan nomor WhatsApp tujuan terlebih dulu.' })
    return
  }

  sendingTest.value = true
  try {
    await $api('/admin/whatsapp/test-send', {
      method: 'POST',
      body: {
        phone_number: testPhoneNumber.value,
        message: testMessage.value,
      },
    })
    showSnackbar({ type: 'success', title: 'Berhasil', text: 'Pesan WhatsApp uji coba berhasil dikirim.' })
  } catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal mengirim pesan WhatsApp uji coba.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  } finally {
    sendingTest.value = false
  }
}

async function sendBroadcastMessage() {
  const message = broadcastMessage.value.trim()
  if (!message) {
    showSnackbar({ type: 'warning', title: 'Pesan Kosong', text: 'Isi pesan broadcast terlebih dahulu.' })
    return
  }

  sendingBroadcast.value = true
  try {
    const response = await $api<{
      target_role: 'USER' | 'KOMANDAN'
      total_recipients: number
      sent_count: number
      failed_count: number
    }>('/admin/whatsapp/broadcast', {
      method: 'POST',
      body: {
        target_role: broadcastRole.value,
        message,
      },
    })

    showSnackbar({
      type: 'success',
      title: 'Broadcast Diproses',
      text: `Role ${response.target_role}: terkirim ${response.sent_count}/${response.total_recipients}, gagal ${response.failed_count}.`,
    })
  }
  catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal mengirim pesan WhatsApp massal.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  }
  finally {
    sendingBroadcast.value = false
  }
}

async function fetchUsers() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.append('page', String(options.value.page ?? 1))
    params.append('itemsPerPage', String(options.value.itemsPerPage ?? 10))

    const [sortItem] = options.value.sortBy ?? []
    if (sortItem?.key) {
      params.append('sortBy', sortItem.key)
      params.append('sortOrder', sortItem.order ?? 'desc')
    }

    if (search.value)
      params.append('search', search.value)

    if (roleFilter.value)
      params.append('role', roleFilter.value)

    const response = await $api<{ items: UserRow[], totalItems: number }>(`/admin/users?${params.toString()}`)
    users.value = response.items
    totalUsers.value = response.totalItems
  } catch (error: any) {
    const errorMessage = (typeof error.data?.message === 'string' && error.data.message !== '')
      ? error.data.message
      : 'Gagal mengambil data pengguna.'
    showSnackbar({ type: 'error', title: 'Terjadi Kesalahan', text: errorMessage })
  } finally {
    loading.value = false
  }
}

let searchTimeout: ReturnType<typeof setTimeout>
watch(search, () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    options.value.page = 1
    fetchUsers()
  }, 400)
})

watch([options, roleFilter], () => {
  options.value.page = 1
  fetchUsers()
}, { deep: true })

watch(loading, (val) => {
  if (val === false)
    hasLoadedOnce.value = true
}, { immediate: true })

onMounted(fetchUsers)
</script>

<template>
  <div>
    <VRow class="mb-4" align="stretch">
      <VCol cols="12" lg="6">
        <VCard class="h-100">
          <VCardItem>
            <VCardTitle>Kirim Informasi Massal</VCardTitle>
            <VCardSubtitle>Kirim pesan ke semua pengguna berdasarkan role: User atau Komandan.</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <VRow>
              <VCol cols="12">
                <VSelect
                  v-model="broadcastRole"
                  :items="[
                    { title: 'Semua User', value: 'USER' },
                    { title: 'Semua Komandan', value: 'KOMANDAN' },
                  ]"
                  label="Target Penerima"
                  item-title="title"
                  item-value="value"
                  density="comfortable"
                />
              </VCol>

              <VCol cols="12">
                <VTextarea
                  v-model="broadcastMessage"
                  label="Pesan Informasi"
                  rows="3"
                  max-rows="6"
                  auto-grow
                  counter="1000"
                  density="comfortable"
                />
              </VCol>

              <VCol cols="12">
                <VBtn
                  block
                  color="primary"
                  height="56"
                  :loading="sendingBroadcast"
                  :disabled="sendingBroadcast"
                  @click="sendBroadcastMessage"
                >
                  Kirim Massal
                </VBtn>
              </VCol>
            </VRow>
          </VCardText>
        </VCard>
      </VCol>

      <VCol cols="12" lg="6">
        <VCard class="h-100">
          <VCardItem>
            <VCardTitle>Tes Pengiriman WhatsApp</VCardTitle>
            <VCardSubtitle>Validasi konfigurasi Fonnte dari panel admin.</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <VRow>
              <VCol cols="12">
                <VTextField
                  v-model="testPhoneNumber"
                  label="Nomor Tujuan"
                  placeholder="08xxxxxxxxxx / 62xxxxxxxxxx"
                  density="comfortable"
                />
              </VCol>

              <VCol cols="12">
                <VTextarea
                  v-model="testMessage"
                  label="Pesan Uji"
                  rows="3"
                  max-rows="6"
                  auto-grow
                  counter="1000"
                  density="comfortable"
                />
              </VCol>

              <VCol cols="12">
                <VBtn
                  block
                  color="success"
                  height="56"
                  :loading="sendingTest"
                  @click="sendTestMessage"
                >
                  Kirim Tes
                </VBtn>
              </VCol>
            </VRow>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <VRow class="mb-4">
      <VCol cols="12" md="6">
        <AppSelect
          v-model="roleFilter"
          :items="roleOptions"
          label="Filter Peran"
          item-title="text"
          item-value="value"
          density="comfortable"
        />
      </VCol>
      <VCol cols="12" md="6" class="d-flex align-center justify-end">
        <div class="text-body-2 text-disabled">
          Total: {{ totalUsers }} pengguna
        </div>
      </VCol>
    </VRow>

    <VCard>
      <VProgressLinear v-if="showSilentRefreshing" indeterminate color="primary" height="2" />

      <VCardText class="py-4 px-6">
        <DataTableToolbar
          v-model:items-per-page="options.itemsPerPage"
          v-model:search="search"
          search-placeholder="Cari nama atau nomor..."
          @update:items-per-page="() => (options.page = 1)"
        />
      </VCardText>

      <VDataTableServer
        v-model:options="options"
        :headers="headers"
        :items="users"
        :items-length="totalUsers"
        :loading="showInitialSkeleton"
        class="text-no-wrap"
        hide-default-footer
      >
        <template #item.role="{ item }">
          <VChip label size="small" color="primary" variant="tonal">
            {{ roleLabels[item.role as keyof typeof roleLabels] ?? item.role }}
          </VChip>
        </template>

        <template #item.phone_number="{ item }">
          <span>{{ item.phone_number }}</span>
        </template>

        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>

        <template #item.whatsapp="{ item }">
          <VBtn
            v-if="normalizeWaNumber(item.phone_number)"
            :href="buildWaLink(item.phone_number)"
            target="_blank"
            rel="noopener"
            color="success"
            variant="tonal"
            size="small"
          >
            Chat
          </VBtn>
          <span v-else class="text-disabled">Tidak tersedia</span>
        </template>
      </VDataTableServer>

      <TablePagination
        v-if="totalUsers > 0"
        :page="options.page"
        :items-per-page="options.itemsPerPage"
        :total-items="totalUsers"
        @update:page="val => (options.page = val)"
      />
    </VCard>
  </div>
</template>
