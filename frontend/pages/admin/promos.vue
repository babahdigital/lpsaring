<script setup lang="ts">
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { ref, watch } from 'vue'

// Tentukan tipe data untuk event promo agar sesuai dengan backend
interface PromoEvent {
  id: string
  name: string
  description?: string
  event_type: 'BONUS_REGISTRATION' | 'GENERAL_ANNOUNCEMENT'
  status: 'DRAFT' | 'ACTIVE' | 'SCHEDULED' | 'EXPIRED' | 'ARCHIVED'
  start_date: string
  end_date?: string
  bonus_value_mb?: number
  bonus_duration_days?: number // <-- KOLOM BARU DITAMBAHKAN
  created_by?: {
    id: string
    full_name: string
  }
}

// Tipe untuk opsi VDataTableServer
type DatatableOptions = VDataTableServer['$props']['options']

// === State Management ===
const { $api } = useNuxtApp()
const snackbar = useSnackbar()

const promoList = ref<PromoEvent[]>([])
const totalPromos = ref(0)
const loading = ref(true)
const options = ref<DatatableOptions>({
  page: 1,
  itemsPerPage: 10,
  sortBy: [{ key: 'created_at', order: 'desc' }],
  groupBy: [],
  search: undefined,
})

const isEditorDialogVisible = ref(false)
const isDeleteDialogVisible = ref(false)
const editedItem = ref<Partial<PromoEvent>>({})
const editedIndex = ref(-1)

// --- State untuk Form & Date Picker ---
const form = ref<any>(null) // Ref untuk VForm
const isStartDateMenuOpen = ref(false)
const isEndDateMenuOpen = ref(false)
const startDateModel = ref<Date | null>(null)
const endDateModel = ref<Date | null>(null)

// === Data Fetching ===
const { error, refresh: refreshPromos } = await useAsyncData(
  'promo-events-admin',
  async () => {
    loading.value = true
    try {
      const response = await $api<{ items: PromoEvent[]; totalItems: number }>('/admin/promos', {
        params: {
          page: options.value.page,
          itemsPerPage: options.value.itemsPerPage,
          sortBy: options.value.sortBy[0]?.key ?? 'created_at',
          sortOrder: options.value.sortBy[0]?.order ?? 'desc',
        },
      })
      promoList.value = response.items
      totalPromos.value = response.totalItems
    }
    catch (e: any) {
      snackbar.add({
        type: 'error',
        text: e.message || 'Gagal mengambil data event.',
      })
    }
    finally {
      loading.value = false
    }
  },
  {
    watch: [options],
    deep: true,
    server: false,
  },
)

// === Headers untuk Data Table ===
const headers = [
  { title: 'Nama Event', key: 'name' },
  { title: 'Status', key: 'status', align: 'center' },
  { title: 'Tipe', key: 'event_type', align: 'center' },
  { title: 'Tanggal Mulai', key: 'start_date' },
  { title: 'Tanggal Selesai', key: 'end_date' },
  { title: 'Aksi', key: 'actions', sortable: false, align: 'center', width: '150px' },
]

// === Konfigurasi untuk VSelect ===
const statusOptions = [
  { title: 'Draft', value: 'DRAFT' },
  { title: 'Aktif', value: 'ACTIVE' },
  { title: 'Terjadwal', value: 'SCHEDULED' },
  { title: 'Kedaluwarsa', value: 'EXPIRED' },
  { title: 'Diarsipkan', value: 'ARCHIVED' },
]
const typeOptions = [
  { title: 'Pengumuman Umum', value: 'GENERAL_ANNOUNCEMENT' },
  { title: 'Bonus Registrasi', value: 'BONUS_REGISTRATION' },
]

// === Aturan Validasi ===
const requiredRule = [(v: string) => !!v || 'Field ini wajib diisi']
const numberRule = [(v: number) => v > 0 || 'Nilai harus lebih dari 0']


// === Computed Properties ===
const formTitle = computed(() => (editedIndex.value === -1 ? 'Tambah Event Baru' : 'Edit Event'))

// === Helper Functions ===
const formatDateForTable = (dateString?: string) => {
  if (!dateString)
    return 'N/A'
  return new Date(dateString).toLocaleString('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

const formatDateForField = (date: Date | null) => {
  if (!date)
    return ''
  return new Date(date).toLocaleDateString('id-ID', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  })
}

const statusColor = (status: PromoEvent['status']) => {
  const colors = {
    ACTIVE: 'success',
    SCHEDULED: 'info',
    EXPIRED: 'warning',
    ARCHIVED: 'secondary',
    DRAFT: 'default',
  }

  return colors[status] || 'default'
}

// === CRUD Functions ===
function openNew() {
  editedIndex.value = -1
  const now = new Date()

  startDateModel.value = now
  endDateModel.value = null

  editedItem.value = {
    name: '',
    description: '',
    status: 'DRAFT',
    event_type: 'GENERAL_ANNOUNCEMENT',
    start_date: now.toISOString(),
    end_date: undefined,
    bonus_value_mb: 0,
    bonus_duration_days: 30, // <-- Inisialisasi default 30 hari
  }
  isEditorDialogVisible.value = true
}

function openEdit(item: PromoEvent) {
  editedIndex.value = promoList.value.indexOf(item)
  editedItem.value = { 
    ...item,
    // Pastikan ada nilai default jika data lama tidak punya durasi
    bonus_duration_days: item.bonus_duration_days || 30 
  }

  startDateModel.value = item.start_date ? new Date(item.start_date) : null
  endDateModel.value = item.end_date ? new Date(item.end_date) : null

  isEditorDialogVisible.value = true
}

function openDelete(item: PromoEvent) {
  editedIndex.value = promoList.value.indexOf(item)
  editedItem.value = { ...item }
  isDeleteDialogVisible.value = true
}

function closeEditorDialog() {
  isEditorDialogVisible.value = false
  editedItem.value = {}
  editedIndex.value = -1
}

function closeDeleteDialog() {
  isDeleteDialogVisible.value = false
  editedItem.value = {}
  editedIndex.value = -1
}

async function saveEvent() {
  // Jalankan validasi form
  const { valid } = await form.value.validate()
  if (!valid) {
    snackbar.add({ type: 'warning', text: 'Mohon isi semua field yang wajib diisi.' })
    return // Hentikan fungsi jika form tidak valid
  }

  try {
    if (editedIndex.value > -1) {
      await $api(`/admin/promos/${editedItem.value.id}`, {
        method: 'PUT',
        body: editedItem.value,
      })
      snackbar.add({ type: 'success', text: 'Event berhasil diperbarui.' })
    }
    else {
      await $api('/admin/promos', {
        method: 'POST',
        body: editedItem.value,
      })
      snackbar.add({ type: 'success', text: 'Event berhasil ditambahkan.' })
    }
    closeEditorDialog()
    await refreshPromos()
  }
  catch (e: any) {
    const errorData = e.data?.errors?.[0]
    const errorMessage = errorData ? `${errorData.loc.join('.')} - ${errorData.msg}` : (e.message || 'Gagal menyimpan data.')
    snackbar.add({ type: 'error', text: errorMessage })
  }
}

async function deleteItemConfirm() {
  try {
    await $api(`/admin/promos/${editedItem.value.id}`, {
      method: 'DELETE',
    })
    snackbar.add({ type: 'success', text: 'Event berhasil dihapus.' })
    closeDeleteDialog()
    await refreshPromos()
  }
  catch (e: any) {
    snackbar.add({ type: 'error', text: e.message || 'Gagal menghapus event.' })
  }
}

// === Sinkronisasi Model Date Picker ke `editedItem` ===
watch(startDateModel, (newDate) => {
  if (editedItem.value)
    editedItem.value.start_date = newDate ? newDate.toISOString() : undefined

  if (newDate && endDateModel.value && newDate > endDateModel.value)
    endDateModel.value = null
})

watch(endDateModel, (newDate) => {
  if (editedItem.value)
    editedItem.value.end_date = newDate ? newDate.toISOString() : undefined
})

useHead({ title: 'Event & Promo' })
</script>

<template>
  <VRow>
    <VCol cols="12">
      <VCard>
        <VCardTitle class="d-flex align-center">
          Event & Promo
          <VSpacer />
          <VBtn color="primary" @click="openNew">
            <VIcon icon="tabler-plus" class="me-2" />
            Tambah Event
          </VBtn>
        </VCardTitle>
        <VCardText>
          <VDataTableServer
            v-model:items-per-page="options.itemsPerPage"
            v-model:page="options.page"
            v-model:sort-by="options.sortBy"
            :headers="headers"
            :items="promoList"
            :items-length="totalPromos"
            :loading="loading"
            class="elevation-1"
            @update:options="options = $event"
          >
            <!-- Slot untuk nama event -->
            <template #item.name="{ item }">
              <div class="d-flex flex-column">
                <span class="font-weight-medium">{{ item.name }}</span>
                <small class="text-disabled">{{ item.description }}</small>
              </div>
            </template>
            <!-- Slot untuk status -->
            <template #item.status="{ item }">
              <VChip :color="statusColor(item.status)" size="small">
                {{ item.status }}
              </VChip>
            </template>

            <!-- Slot untuk tipe event -->
            <template #item.event_type="{ item }">
              <VChip color="info" variant="tonal" size="small">
                {{ item.event_type === 'GENERAL_ANNOUNCEMENT' ? 'Pengumuman' : 'Bonus' }}
              </VChip>
            </template>

            <!-- Slot untuk format tanggal -->
            <template #item.start_date="{ item }">
              {{ formatDateForTable(item.start_date) }}
            </template>
            <template #item.end_date="{ item }">
              {{ formatDateForTable(item.end_date) }}
            </template>

            <!-- Slot untuk actions -->
            <template #item.actions="{ item }">
              <div class="d-flex gap-1 justify-center">
                <VBtn icon variant="text" color="primary" size="small" @click="openEdit(item)">
                  <VIcon icon="tabler-pencil" />
                  <VTooltip activator="parent">
                    Edit Event
                  </VTooltip>
                </VBtn>
                <VBtn icon variant="text" color="error" size="small" @click="openDelete(item)">
                  <VIcon icon="tabler-trash" />
                  <VTooltip activator="parent">
                    Hapus Event
                  </VTooltip>
                </VBtn>
              </div>
            </template>
          </VDataTableServer>
        </VCardText>
      </VCard>
    </VCol>
  </VRow>

  <!-- Dialog untuk Create/Edit Event -->
  <VDialog v-model="isEditorDialogVisible" max-width="600px" persistent>
    <VCard>
      <VForm ref="form" @submit.prevent="saveEvent">
        <VCardTitle>
          <span class="headline">{{ formTitle }}</span>
        </VCardTitle>
        <VCardText>
          <VContainer>
            <VRow>
              <VCol cols="12">
                <VTextField
                  v-model="editedItem.name"
                  label="Nama Event"
                  prepend-inner-icon="tabler-heading"
                  :rules="requiredRule"
                  persistent-placeholder
                />
              </VCol>
              <VCol cols="12">
                <VTextarea
                  v-model="editedItem.description"
                  label="Deskripsi"
                  rows="3"
                  prepend-inner-icon="tabler-message-2"
                  :rules="requiredRule"
                  persistent-placeholder
                />
              </VCol>
              <VCol cols="12" md="6">
                <VSelect
                  v-model="editedItem.status"
                  :items="statusOptions"
                  label="Status Event"
                  prepend-inner-icon="tabler-traffic-lights"
                  :rules="requiredRule"
                />
              </VCol>
              <VCol cols="12" md="6">
                <VSelect
                  v-model="editedItem.event_type"
                  :items="typeOptions"
                  label="Tipe Event"
                  prepend-inner-icon="tabler-category"
                  :rules="requiredRule"
                />
              </VCol>

              <VCol cols="12" md="6">
                <VTextField
                  id="start-date-activator"
                  :model-value="formatDateForField(startDateModel)"
                  label="Tanggal Mulai"
                  placeholder="Pilih tanggal"
                  prepend-inner-icon="tabler-calendar-event"
                  readonly
                  :rules="requiredRule"
                />
                <VMenu
                  v-model="isStartDateMenuOpen"
                  activator="#start-date-activator"
                  :close-on-content-click="false"
                  location="bottom start"
                  offset="10"
                >
                  <client-only>
                    <VDatePicker
                      v-model="startDateModel"
                      @update:model-value="isStartDateMenuOpen = false"
                      no-title
                      color="primary"
                      show-adjacent-months
                    />
                  </client-only>
                </VMenu>
              </VCol>

              <VCol cols="12" md="6">
                <VTextField
                  id="end-date-activator"
                  :model-value="formatDateForField(endDateModel)"
                  label="Tanggal Selesai (Opsional)"
                  placeholder="Pilih tanggal"
                  prepend-inner-icon="tabler-calendar-off"
                  readonly
                  clearable
                  :disabled="!startDateModel"
                  @click:clear="endDateModel = null"
                />
                <VMenu
                  v-model="isEndDateMenuOpen"
                  activator="#end-date-activator"
                  :close-on-content-click="false"
                  location="bottom start"
                  offset="10"
                >
                  <client-only>
                    <VDatePicker
                      v-model="endDateModel"
                      @update:model-value="isEndDateMenuOpen = false"
                      no-title
                      color="primary"
                      :min="startDateModel"
                      show-adjacent-months
                    />
                  </client-only>
                </VMenu>
              </VCol>

              <!-- === BLOK KONDISIONAL UNTUK BONUS === -->
              <template v-if="editedItem.event_type === 'BONUS_REGISTRATION'">
                <VCol cols="12" md="6">
                  <VTextField
                    v-model.number="editedItem.bonus_value_mb"
                    label="Bonus Kuota (MB)"
                    type="number"
                    prepend-inner-icon="tabler-database"
                    :rules="[...requiredRule, ...numberRule]"
                  />
                </VCol>
                <VCol cols="12" md="6">
                   <VTextField
                    v-model.number="editedItem.bonus_duration_days"
                    label="Durasi Bonus (Hari)"
                    type="number"
                    prepend-inner-icon="tabler-clock"
                    :rules="[...requiredRule, ...numberRule]"
                  />
                </VCol>
              </template>
            </VRow>
          </VContainer>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn color="secondary" @click="closeEditorDialog">
            Batal
          </VBtn>
          <VBtn color="primary" type="submit">
            Simpan
          </VBtn>
        </VCardActions>
      </VForm>
    </VCard>
  </VDialog>

  <!-- Dialog untuk Konfirmasi Hapus -->
  <VDialog v-model="isDeleteDialogVisible" max-width="500px">
    <VCard>
      <VCardTitle class="headline">
        Apakah Anda yakin?
      </VCardTitle>
      <VCardText>
        Anda akan menghapus event <strong>"{{ editedItem.name }}"</strong>. Tindakan ini tidak dapat dibatalkan.
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn color="secondary" @click="closeDeleteDialog">
          Batal
        </VBtn>
        <VBtn color="error" @click="deleteItemConfirm">
          Ya, Hapus
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<!-- CSS Presisi untuk VDatePicker dari referensi Anda -->
<style scoped lang="scss">
:deep(.v-date-picker-month) {
  padding: 0 !important;
  width: 100% !important;
}

:deep(.v-date-picker-month__weeks) {
  display: grid !important;
  grid-template-columns: repeat(7, 1fr) !important;
  justify-items: center !important;
  width: 100% !important;
  column-gap: 0 !important;
}

:deep(.v-date-picker-month__weekday) {
  padding: 0 !important;
  margin: 0 !important;
  width: 100% !important;
  text-align: center !important;
  font-size: 0.875rem !important;
  height: 40px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}

:deep(.v-date-picker-month__days) {
  display: grid !important;
  grid-template-columns: repeat(7, 1fr) !important;
  justify-items: center !important;
  width: 100% !important;
  column-gap: 0 !important;
}

:deep(.v-date-picker-month__day) {
  margin: 0 !important;
  padding: 0 !important;
  width: 100% !important;
  height: 40px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}

:deep(.v-date-picker-month__day-btn) {
  width: 36px !important;
  height: 36px !important;
  margin: 0 !important;
}

:deep(.v-date-picker-month__day--adjacent) {
  opacity: 0.5 !important;
}

.v-menu :deep(.v-overlay__content) {
  width: 320px !important;
  min-width: 320px !important;
  max-width: 320px !important;
}

:deep(.v-date-picker-controls) {
  padding: 4px 8px !important;
}

:deep(.v-date-picker-header) {
  padding: 10px 20px !important;
}
</style>