<script setup lang="ts">
import type { VDataTableServer } from 'vuetify/labs/VDataTable'
import { ref, watch, computed } from 'vue'
import { useDisplay } from 'vuetify'

// Menggunakan hook useDisplay untuk deteksi mobile
const { mobile } = useDisplay()

// Tipe Data
interface PromoEvent {
  id: string
  name: string
  description?: string
  event_type: 'BONUS_REGISTRATION' | 'GENERAL_ANNOUNCEMENT'
  status: 'DRAFT' | 'ACTIVE' | 'SCHEDULED' | 'EXPIRED' | 'ARCHIVED'
  start_date: string
  end_date?: string
  bonus_value_mb?: number
  bonus_duration_days?: number
  created_at: string
}

type DatatableOptions = VDataTableServer['$props']['options']

const { $api } = useNuxtApp()
const snackbar = useSnackbar()

// State untuk tabel dan dialog
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

// State untuk form dan date picker
const form = ref<any>(null)
const isStartDateMenuOpen = ref(false)
const isEndDateMenuOpen = ref(false)

// [PERBAIKAN] Mengisi handler yang sebelumnya kosong pada useAsyncData
const { error, refresh: refreshPromos } = useAsyncData(
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


// Computed properties
const startDateModel = computed({
  get: () => editedItem.value.start_date ? new Date(editedItem.value.start_date) : null,
  set: (val) => {
    if (editedItem.value) editedItem.value.start_date = val?.toISOString()
  }
})
const endDateModel = computed({
  get: () => editedItem.value.end_date ? new Date(editedItem.value.end_date) : null,
  set: (val) => {
    if (editedItem.value) editedItem.value.end_date = val?.toISOString()
  }
})

const headers = computed(() => {
  if (mobile.value) {
    return [
      { title: 'Event', key: 'name', sortable: false },
      { title: 'Aksi', key: 'actions', sortable: false, align: 'end' },
    ]
  }
  return [
    { title: 'Detail Event', key: 'name', sortable: true, width: '35%' },
    { title: 'Tipe', key: 'event_type', align: 'center', sortable: true },
    { title: 'Status', key: 'status', align: 'center', sortable: true },
    { title: 'Periode Aktif', key: 'start_date', sortable: true },
    { title: 'Aksi', key: 'actions', sortable: false, align: 'center', width: '120px' },
  ]
})

const formTitle = computed(() => (editedIndex.value === -1 ? 'Tambah Event Baru' : 'Edit Event'))

const bonusValueGb = computed({
  get: () => editedItem.value.bonus_value_mb ? editedItem.value.bonus_value_mb / 1024 : 0,
  set: (newValue) => {
    if (editedItem.value) editedItem.value.bonus_value_mb = newValue * 1024;
  }
})

// Opsi untuk VSelect
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

// Aturan validasi
const requiredRule = [(v: any) => !!v || 'Field ini wajib diisi']
const numberRule = [(v: number) => (v && v > 0) || 'Nilai harus lebih dari 0']

// Fungsi Helper
const formatDate = (date: Date | null | undefined) => {
  if (!date) return ''
  return new Date(date).toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' })
}
const formatTableDate = (dateString?: string) => {
  if (!dateString) return 'N/A'
  return new Date(dateString).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' })
}

const statusProps = (status: PromoEvent['status']) => {
  const map: Record<PromoEvent['status'], { color: string; icon: string }> = {
    ACTIVE: { color: 'success', icon: 'tabler-circle-check' },
    SCHEDULED: { color: 'info', icon: 'tabler-alarm' },
    EXPIRED: { color: 'warning', icon: 'tabler-clock-off' },
    ARCHIVED: { color: 'secondary', icon: 'tabler-archive' },
    DRAFT: { color: 'default', icon: 'tabler-edit-circle' },
  }
  return map[status] || map.DRAFT
}

// Fungsi CRUD
function openNew() {
  editedIndex.value = -1
  const now = new Date()
  editedItem.value = {
    name: '',
    description: '',
    status: 'DRAFT',
    event_type: 'GENERAL_ANNOUNCEMENT',
    start_date: now.toISOString(),
    end_date: undefined,
    bonus_value_mb: 0,
    bonus_duration_days: 30,
  }
  isEditorDialogVisible.value = true
}

function openEdit(item: PromoEvent) {
  editedIndex.value = promoList.value.findIndex(p => p.id === item.id)
  editedItem.value = JSON.parse(JSON.stringify(item))
  isEditorDialogVisible.value = true
}

function openDelete(item: PromoEvent) {
  editedIndex.value = promoList.value.findIndex(p => p.id === item.id)
  editedItem.value = { ...item }
  isDeleteDialogVisible.value = true
}

function closeEditorDialog() {
  isEditorDialogVisible.value = false
  setTimeout(() => {
    editedItem.value = {}
    editedIndex.value = -1
  }, 300)
}

function closeDeleteDialog() {
  isDeleteDialogVisible.value = false
  setTimeout(() => {
    editedItem.value = {}
    editedIndex.value = -1
  }, 300)
}

async function saveEvent() {
  const { valid } = await form.value.validate()
  if (!valid) {
    snackbar.add({ type: 'warning', text: 'Mohon periksa kembali form, ada data yang belum valid.' })
    return
  }
  try {
    if (editedIndex.value > -1) {
      await $api(`/admin/promos/${editedItem.value.id}`, { method: 'PUT', body: editedItem.value })
      snackbar.add({ type: 'success', text: 'Event berhasil diperbarui.' })
    }
    else {
      await $api('/admin/promos', { method: 'POST', body: editedItem.value })
      snackbar.add({ type: 'success', text: 'Event berhasil ditambahkan.' })
    }
    closeEditorDialog()
    await refreshPromos()
  }
  catch (e: any) {
    const errorMessage = e.data?.message || e.data?.errors?.[0]?.msg || 'Gagal menyimpan data.'
    snackbar.add({ type: 'error', text: errorMessage })
  }
}

async function deleteItemConfirm() {
  try {
    await $api(`/admin/promos/${editedItem.value.id}`, { method: 'DELETE' })
    snackbar.add({ type: 'success', text: 'Event berhasil dihapus.' })
    closeDeleteDialog()
    await refreshPromos()
  }
  catch (e: any) {
    snackbar.add({ type: 'error', text: e.message || 'Gagal menghapus event.' })
  }
}

useHead({ title: 'Manajemen Event & Promo' })
</script>

<template>
  <VCard>
    <VCardTitle class="d-flex align-center pa-4">
      <h2 class="text-h5">Manajemen Event & Promo</h2>
      <VSpacer />
      <VBtn color="primary" @click="openNew" prepend-icon="tabler-plus">
        Tambah Event
      </VBtn>
    </VCardTitle>

    <VDataTableServer
        v-model:items-per-page="options.itemsPerPage"
        v-model:page="options.page"
        v-model:sort-by="options.sortBy"
        :headers="headers"
        :items="promoList"
        :items-length="totalPromos"
        :loading="loading"
        @update:options="options = $event"
        class="text-no-wrap"
        :item-value="item => item.id"
      >
      <template #item.name="{ item }">
        <div class="d-flex flex-column py-2">
          <span class="font-weight-medium text-wrap">{{ item.name }}</span>
          <small class="text-disabled text-wrap" style="max-width: 300px;">{{ item.description }}</small>
          <div v-if="mobile" class="mt-2 d-flex flex-column gap-1">
             <VChip :color="statusProps(item.status).color" size="x-small" label>
                {{ item.status }}
             </VChip>
             <VChip size="x-small" label>
                {{ item.event_type === 'BONUS_REGISTRATION' ? 'Bonus' : 'Pengumuman' }}
             </VChip>
          </div>
        </div>
      </template>

      <template #item.event_type="{ item }">
         <VChip size="small" :color="item.event_type === 'BONUS_REGISTRATION' ? 'secondary' : 'primary'" variant="tonal">
            {{ item.event_type === 'BONUS_REGISTRATION' ? 'Bonus' : 'Pengumuman' }}
         </VChip>
      </template>

      <template #item.status="{ item }">
        <VChip :color="statusProps(item.status).color" size="small" label>
          {{ item.status }}
        </VChip>
      </template>

      <template #item.start_date="{ item }">
        <div class="d-flex flex-column py-2">
            <span>{{ formatTableDate(item.start_date) }}</span>
            <small v-if="item.end_date" class="text-disabled">s/d {{ formatTableDate(item.end_date) }}</small>
            <small v-else class="text-disabled">Tanpa batas akhir</small>
        </div>
      </template>

      <template #item.actions="{ item }">
        <div class="d-flex gap-1 justify-end">
          <VBtn icon="tabler-pencil" size="small" variant="text" @click="openEdit(item)" />
          <VBtn icon="tabler-trash" size="small" variant="text" color="error" @click="openDelete(item)" />
        </div>
      </template>
    </VDataTableServer>
  </VCard>

  <VDialog v-model="isEditorDialogVisible" max-width="800px" persistent scrollable>
    <VCard>
      <VForm ref="form" @submit.prevent="saveEvent">
        <VCardTitle class="pa-4">
          <span class="text-h5">{{ formTitle }}</span>
        </VCardTitle>
        <VDivider/>

        <VCardText style="max-height: 70vh;">
          <VContainer>
            <VRow>
              <VCol cols="12">
                <VTextField v-model="editedItem.name" label="Nama Event" :rules="requiredRule" />
              </VCol>
               <VCol cols="12">
                <VTextarea
                  v-model="editedItem.description"
                  label="Deskripsi Singkat"
                  rows="3"
                  :rules="requiredRule"
                  placeholder="Jelaskan promo ini secara singkat"
                />
              </VCol>

              <VCol cols="12" sm="6" md="4">
                <VSelect
                  v-model="editedItem.status"
                  :items="statusOptions"
                  label="Status"
                  :rules="requiredRule"
                />
              </VCol>

              <VCol cols="12" sm="6" md="8">
                <VSelect
                  v-model="editedItem.event_type"
                  :items="typeOptions"
                  label="Tipe Event"
                  :rules="requiredRule"
                />
              </VCol>

              <VCol cols="12" sm="6">
                <VMenu v-model="isStartDateMenuOpen" :close-on-content-click="false">
                  <template #activator="{ props }">
                    <VTextField
                      :model-value="formatDate(startDateModel)"
                      label="Tanggal Mulai"
                      readonly
                      v-bind="props"
                      :rules="requiredRule"
                      prepend-inner-icon="tabler-calendar"
                      density="comfortable"
                      variant="outlined"
                    />
                  </template>
                  <VDatePicker v-model="startDateModel" @update:model-value="isStartDateMenuOpen = false" color="primary" />
                </VMenu>
              </VCol>

              <VCol cols="12" sm="6">
                <VMenu v-model="isEndDateMenuOpen" :close-on-content-click="false">
                  <template #activator="{ props }">
                    <VTextField
                      :model-value="formatDate(endDateModel)"
                      label="Tanggal Selesai (Opsional)"
                      readonly
                      clearable
                      @click:clear="endDateModel = null"
                      v-bind="props"
                      :disabled="!startDateModel"
                      prepend-inner-icon="tabler-calendar-off"
                      density="comfortable"
                      variant="outlined"
                    />
                  </template>
                  <VDatePicker v-model="endDateModel" @update:model-value="isEndDateMenuOpen = false" color="primary" :min="startDateModel?.toISOString()" />
                </VMenu>
              </VCol>
              
              <VCol cols="12" v-if="editedItem.event_type === 'BONUS_REGISTRATION'">
                <VAlert
                  icon="tabler-gift"
                  color="secondary"
                  variant="tonal"
                  class="mb-4"
                >
                  Isi detail bonus yang akan diterima pengguna baru.
                </VAlert>
                <VRow>
                    <VCol cols="12" sm="6">
                        <VTextField
                            v-model.number="bonusValueGb"
                            label="Bonus Kuota (GB)"
                            type="number"
                            :rules="numberRule"
                            min="0"
                            step="0.5"
                        />
                    </VCol>
                     <VCol cols="12" sm="6">
                        <VTextField
                            v-model.number="editedItem.bonus_duration_days"
                            label="Durasi Bonus (Hari)"
                            type="number"
                            :rules="numberRule"
                            min="1"
                        />
                    </VCol>
                </VRow>
              </VCol>

            </VRow>
          </VContainer>
        </VCardText>
        <VDivider/>
        
        <VCardActions class="pa-4">
          <VSpacer />
          <VBtn color="secondary" variant="text" @click="closeEditorDialog">Batal</VBtn>
          <VBtn color="primary" variant="flat" type="submit">Simpan</VBtn>
        </VCardActions>
      </VForm>
    </VCard>
  </VDialog>
  
  <VDialog v-model="isDeleteDialogVisible" max-width="500px" persistent>
    <VCard>
      <VCardTitle class="text-h5"> Konfirmasi Hapus </VCardTitle>
      <VCardText>
        Apakah Anda yakin ingin menghapus event <strong>"{{ editedItem.name }}"</strong>? Aksi ini tidak dapat dibatalkan.
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn color="secondary" variant="text" @click="closeDeleteDialog"> Batal </VBtn>
        <VBtn color="error" variant="flat" @click="deleteItemConfirm"> Ya, Hapus </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
:deep(.v-date-picker-month) { padding: 0 !important; width: 100% !important; }
:deep(.v-date-picker-month__weeks) { display: grid !important; grid-template-columns: repeat(7, 1fr) !important; justify-items: center !important; width: 100% !important; column-gap: 0 !important; }
:deep(.v-date-picker-month__weekday) { padding: 0 !important; margin: 0 !important; width: 100% !important; text-align: center !important; font-size: 0.875rem !important; height: 40px !important; display: flex !important; align-items: center !important; justify-content: center !important; }
:deep(.v-date-picker-month__days) { display: grid !important; grid-template-columns: repeat(7, 1fr) !important; justify-items: center !important; width: 100% !important; column-gap: 0 !important; }
:deep(.v-date-picker-month__day) { margin: 0 !important; padding: 0 !important; width: 100% !important; height: 40px !important; display: flex !important; align-items: center !important; justify-content: center !important; }
:deep(.v-date-picker-month__day-btn) { width: 36px !important; height: 36px !important; margin: 0 !important; }
:deep(.v-date-picker-month__day--adjacent) { opacity: 0.5 !important; }
.v-menu :deep(.v-overlay__content) { width: 320px !important; min-width: 320px !important; max-width: 320px !important; }
:deep(.v-date-picker-controls) { padding: 4px 8px !important; }
:deep(.v-date-picker-header) { padding: 10px 20px !important; }
</style>