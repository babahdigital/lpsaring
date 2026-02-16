<script lang="ts" setup>
import type { VForm } from 'vuetify/components'
import AppSelect from '@core/components/app-form-elements/AppSelect.vue'
import AppTextField from '@core/components/app-form-elements/AppTextField.vue'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useAuthStore } from '@/store/auth'
// [PERBAIKAN] Impor ini sekarang akan berhasil karena kita sudah membuat filenya.
import { normalize_to_e164 } from '~/utils/formatters'

interface FormData {
  full_name: string
  phone_number: string // Menyimpan format 08xx selama di form
  role: 'USER' | 'KOMANDAN' | 'ADMIN' | 'SUPER_ADMIN'
  blok: string | null
  kamar: string | null
  is_tamping: boolean
  tamping_type: string | null
  add_gb: number
  add_days: number
}

const props = defineProps<{
  modelValue: boolean
  loading: boolean
  availableBloks: string[]
  availableKamars: string[]
  isAlamatLoading: boolean
}>()

const emit = defineEmits(['update:modelValue', 'save'])
const authStore = useAuthStore()
const formRef = ref<InstanceType<typeof VForm> | null>(null)

function getInitialFormData(): FormData {
  return {
    full_name: '',
    phone_number: '',
    role: 'USER',
    blok: null,
    kamar: null,
    is_tamping: false,
    tamping_type: null,
    add_gb: 1,
    add_days: 30,
  }
}

const formData = reactive<FormData>(getInitialFormData())

watch(() => props.modelValue, (isOpen) => {
  if (isOpen) {
    Object.assign(formData, getInitialFormData())
    nextTick(() => {
      formRef.value?.resetValidation()
    })
  }
})

// PERBAIKAN: Memisahkan setiap pernyataan ke baris baru
watch(() => formData.role, (newRole) => {
  if (newRole === 'KOMANDAN') {
    formData.add_gb = 5
    formData.add_days = 30
    formData.blok = null
    formData.kamar = null
    formData.is_tamping = false
    formData.tamping_type = null
  }
  else if (newRole === 'USER') {
    formData.add_gb = 1
    formData.add_days = 30
  }
  else {
    formData.add_gb = 0
    formData.add_days = 0
    formData.blok = null
    formData.kamar = null
    formData.is_tamping = false
    formData.tamping_type = null
  }
}, { immediate: true })

// PERBAIKAN: Memisahkan pernyataan if ke dalam blok
const availableRoles = computed(() => {
  const roles = [{ title: 'User Biasa', value: 'USER' }, { title: 'Komandan', value: 'KOMANDAN' }]
  if (authStore.isSuperAdmin) {
    roles.push({ title: 'Admin', value: 'ADMIN' })
  }

  return roles
})

const showAlamatSection = computed(() => formData.role === 'USER' && formData.is_tamping !== true)
const showTampingSection = computed(() => formData.role === 'USER' && formData.is_tamping === true)
const showQuotaFields = computed(() => formData.role === 'USER' || formData.role === 'KOMANDAN')

const tampingOptions = [
  'Tamping luar',
  'Tamping AO',
  'Tamping Pembinaan',
  'Tamping kunjungan',
  'Tamping kamtib',
  'Tamping klinik',
  'Tamping dapur',
  'Tamping mesjid',
  'Tamping p2u',
  'Tamping BLK',
  'Tamping kebersihan',
  'Tamping Humas',
  'Tamping kebun',
].map(item => ({ title: item, value: item }))

async function onSave() {
  if (!formRef.value)
    return

  const { valid } = await formRef.value.validate()

  if (valid) {
    const payload = { ...formData }

    try {
      // [PERBAIKAN] Menggunakan fungsi formatter untuk memastikan konsistensi dengan backend
      payload.phone_number = normalize_to_e164(payload.phone_number)
      emit('save', payload)
    }
    catch (e: any) {
      // Menampilkan error jika format nomor telepon tidak valid
      // Anda bisa menggunakan snackbar atau alert di sini
      console.error('Format nomor telepon tidak valid:', e.message)
      // Contoh: authStore.setError(e.message)
    }
  }
}

const onClose = () => emit('update:modelValue', false)

// Aturan validasi
const requiredRule = (v: any) => !!v || 'Wajib diisi.'
const tampingRequiredRule = (v: any) => !!v || 'Jenis tamping wajib dipilih.'
function phoneRule(v: string) {
  if (!v)
    return true

  try {
    normalize_to_e164(v)
    return true
  }
  catch (error: any) {
    return error instanceof Error && error.message !== ''
      ? error.message
      : 'Format nomor tidak valid.'
  }
}
function quotaRule(v: any) {
  if (!showQuotaFields.value)
    return true

  const num = Number(v)
  // PERBAIKAN: Menggunakan Number.isNaN dan menambahkan kurung untuk kejelasan operasi
  return (!Number.isNaN(num) && num > 0) || 'Harus berupa angka lebih dari 0.'
}

watch(() => formData.is_tamping, (isTamping) => {
  if (isTamping) {
    formData.blok = null
    formData.kamar = null
  }
  else {
    formData.tamping_type = null
  }
})
</script>

<template>
  <VDialog
    :model-value="props.modelValue"
    max-width="700px"
    persistent
    scrollable
    @update:model-value="onClose"
  >
    <VCard>
      <VForm
        ref="formRef"
        @submit.prevent="onSave"
      >
        <VCardTitle class="pa-4 d-flex align-center bg-primary rounded-t-lg">
          <VIcon
            icon="tabler-user-plus"
            start
          />
          <span class="headline text-white">Tambah Pengguna Baru</span>
          <VSpacer />
          <VBtn
            icon="tabler-x"
            variant="text"
            class="text-white"
            @click="onClose"
          />
        </VCardTitle>
        <VDivider />
        <VCardText
          class="pa-5"
          style="max-height: 70vh;"
        >
          <VRow>
            <VCol cols="12">
              <AppTextField
                v-model="formData.full_name"
                label="Nama Lengkap"
                :rules="[requiredRule]"
                prepend-inner-icon="tabler-user"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <AppTextField
                v-model="formData.phone_number"
                label="Nomor Telepon (08xx)"
                :rules="[requiredRule, phoneRule]"
                prepend-inner-icon="tabler-phone"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <AppSelect
                v-model="formData.role"
                :items="availableRoles"
                label="Peran"
                :rules="[requiredRule]"
                prepend-inner-icon="tabler-shield-check"
              />
            </VCol>

            <VCol v-if="formData.role === 'USER'" cols="12">
              <VSwitch v-model="formData.is_tamping" label="Tamping" color="primary" inset />
              <div class="text-caption text-medium-emphasis mt-1">
                Aktifkan jika pengguna termasuk tamping. Jika tamping aktif, blok/kamar akan dinonaktifkan.
              </div>
            </VCol>

            <template v-if="showTampingSection">
              <VCol cols="12">
                <AppSelect
                  v-model="formData.tamping_type"
                  :items="tampingOptions"
                  label="Jenis Tamping"
                  placeholder="Pilih Jenis Tamping"
                  :rules="[tampingRequiredRule]"
                  prepend-inner-icon="tabler-building-bank"
                />
              </VCol>
            </template>

            <template v-if="showAlamatSection">
              <VCol
                cols="12"
                md="6"
              >
                <AppSelect
                  v-model="formData.blok"
                  :items="props.availableBloks"
                  label="Blok"
                  placeholder="Pilih Blok"
                  :rules="[requiredRule]"
                  :loading="props.isAlamatLoading"
                  prepend-inner-icon="tabler-building"
                />
              </VCol>
              <VCol
                cols="12"
                md="6"
              >
                <AppSelect
                  v-model="formData.kamar"
                  :items="props.availableKamars"
                  label="Kamar"
                  placeholder="Pilih Kamar"
                  :rules="[requiredRule]"
                  :loading="props.isAlamatLoading"
                  prepend-inner-icon="tabler-door"
                />
              </VCol>
            </template>

            <VCol
              v-if="showQuotaFields"
              cols="12"
            >
              <VDivider class="my-2" />
            </VCol>

            <template v-if="showQuotaFields">
              <VCol
                cols="12"
                md="6"
              >
                <AppTextField
                  v-model.number="formData.add_gb"
                  label="Kuota Awal (GB)"
                  type="number"
                  step="0.5"
                  min="0"
                  :rules="[quotaRule]"
                  prepend-inner-icon="tabler-database-plus"
                />
              </VCol>
              <VCol
                cols="12"
                md="6"
              >
                <AppTextField
                  v-model.number="formData.add_days"
                  label="Masa Aktif Awal (Hari)"
                  type="number"
                  min="0"
                  :rules="[quotaRule]"
                  prepend-inner-icon="tabler-calendar-plus"
                />
              </VCol>
            </template>
          </VRow>
        </VCardText>
        <VDivider />
        <VCardActions class="pa-4 d-flex justify-end">
          <VBtn
            variant="tonal"
            color="secondary"
            @click="onClose"
          >
            Batal
          </VBtn>
          <VBtn
            type="submit"
            color="primary"
            :loading="props.loading"
          >
            Buat Pengguna
          </VBtn>
        </VCardActions>
      </VForm>
    </VCard>
  </VDialog>
</template>
