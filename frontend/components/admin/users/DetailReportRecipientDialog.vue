<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import type { AdminUserListItem, AdminUserListResponse } from '@/types/api/contracts'

interface InternalRecipientOption {
  id: string
  full_name: string
  role: 'ADMIN' | 'SUPER_ADMIN'
  phone_number: string
}

const props = defineProps<{
  modelValue: boolean
  userName?: string | null
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'submit', payload: { recipientIds: string[], recipients: InternalRecipientOption[] }): void
}>()

const { $api } = useNuxtApp()

const isLoading = ref(false)
const loadError = ref('')
const recipientItems = ref<InternalRecipientOption[]>([])
const selectedRecipientIds = ref<string[]>([])

const selectedRecipients = computed(() => {
  const selectedSet = new Set(selectedRecipientIds.value)
  return recipientItems.value.filter(recipient => selectedSet.has(recipient.id))
})

const selectedSummary = computed(() => {
  if (selectedRecipients.value.length === 0)
    return 'Belum ada admin dipilih.'
  return selectedRecipients.value.map(recipient => recipient.full_name).join(', ')
})

function closeDialog() {
  emit('update:modelValue', false)
}

function normalizeRecipient(user: AdminUserListItem): InternalRecipientOption | null {
  const phoneNumber = String(user.phone_number ?? '').trim()
  if (phoneNumber === '')
    return null
  if (user.role !== 'ADMIN' && user.role !== 'SUPER_ADMIN')
    return null
  return {
    id: user.id,
    full_name: user.full_name,
    role: user.role,
    phone_number: phoneNumber,
  }
}

async function fetchRecipientsByRole(role: 'ADMIN' | 'SUPER_ADMIN') {
  const query = new URLSearchParams({
    role,
    itemsPerPage: '100',
    sortBy: 'full_name',
    sortOrder: 'asc',
  })
  const response = await $api<AdminUserListResponse>(`/admin/users?${query.toString()}`)
  return Array.isArray(response.items) ? response.items : []
}

async function fetchRecipients() {
  isLoading.value = true
  loadError.value = ''
  try {
    const [adminItems, superAdminItems] = await Promise.all([
      fetchRecipientsByRole('ADMIN'),
      fetchRecipientsByRole('SUPER_ADMIN'),
    ])

    const recipientMap = new Map<string, InternalRecipientOption>()
    for (const user of [...adminItems, ...superAdminItems]) {
      const normalized = normalizeRecipient(user)
      if (!normalized)
        continue
      recipientMap.set(normalized.id, normalized)
    }

    recipientItems.value = Array.from(recipientMap.values()).sort((left, right) => {
      if (left.role !== right.role)
        return left.role === 'SUPER_ADMIN' ? -1 : 1
      return left.full_name.localeCompare(right.full_name, 'id-ID')
    })
    selectedRecipientIds.value = []
  }
  catch (error: any) {
    recipientItems.value = []
    selectedRecipientIds.value = []
    loadError.value = error?.data?.message || 'Daftar admin penerima belum bisa dimuat.'
  }
  finally {
    isLoading.value = false
  }
}

function toggleRecipient(recipientId: string) {
  const selectedSet = new Set(selectedRecipientIds.value)
  if (selectedSet.has(recipientId))
    selectedSet.delete(recipientId)
  else
    selectedSet.add(recipientId)
  selectedRecipientIds.value = recipientItems.value
    .map(recipient => recipient.id)
    .filter(recipientIdValue => selectedSet.has(recipientIdValue))
}

function submitSelection() {
  if (selectedRecipients.value.length === 0)
    return
  emit('submit', {
    recipientIds: [...selectedRecipientIds.value],
    recipients: [...selectedRecipients.value],
  })
  closeDialog()
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen)
      fetchRecipients()
    else {
      selectedRecipientIds.value = []
      loadError.value = ''
    }
  },
)
</script>

<template>
  <VDialog :model-value="props.modelValue" max-width="760" persistent @update:model-value="closeDialog">
    <VCard rounded="xl">
      <VCardTitle class="pa-5 pb-3">
        <div class="detail-report-recipient__title-row">
          <div>
            <div class="text-overline">
              Kirim ke Admin
            </div>
            <div class="text-h6 font-weight-bold">
              Pilih admin atau super admin penerima
            </div>
            <div class="text-body-2 text-medium-emphasis mt-1">
              Laporan untuk {{ props.userName || 'pengguna ini' }} hanya akan dikirim ke penerima yang Anda pilih di bawah.
            </div>
          </div>
          <VBtn icon="tabler-x" variant="text" size="small" @click="closeDialog" />
        </div>
      </VCardTitle>

      <VCardText class="pt-0 pb-3">
        <VAlert variant="tonal" color="info" icon="tabler-info-circle" class="mb-4">
          Sistem tidak akan broadcast ke semua admin. Pilihan di popup ini menjadi daftar final penerima WhatsApp.
        </VAlert>

        <VAlert v-if="loadError" variant="tonal" color="warning" icon="tabler-alert-circle" class="mb-4">
          {{ loadError }}
        </VAlert>

        <VSheet rounded="lg" border class="detail-report-recipient__summary pa-3 mb-4">
          <div class="text-caption text-disabled mb-1">
            Penerima terpilih
          </div>
          <div class="font-weight-medium">
            {{ selectedSummary }}
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            {{ selectedRecipients.length }} penerima siap diantrikan.
          </div>
        </VSheet>

        <VProgressLinear v-if="isLoading" indeterminate color="primary" class="mb-4" />

        <div v-if="!isLoading && recipientItems.length === 0" class="detail-report-recipient__empty text-medium-emphasis">
          Tidak ada admin dengan nomor WhatsApp aktif yang bisa dipilih saat ini.
        </div>

        <VList v-else lines="two" density="comfortable" class="detail-report-recipient__list">
          <VListItem
            v-for="recipient in recipientItems"
            :key="recipient.id"
            rounded="lg"
            class="detail-report-recipient__item"
            @click="toggleRecipient(recipient.id)"
          >
            <template #prepend>
              <VCheckboxBtn
                :model-value="selectedRecipientIds.includes(recipient.id)"
                color="primary"
                @update:model-value="toggleRecipient(recipient.id)"
                @click.stop
              />
            </template>

            <VListItemTitle class="font-weight-medium">
              {{ recipient.full_name }}
            </VListItemTitle>

            <VListItemSubtitle>
              <span>{{ recipient.phone_number }}</span>
              <span class="mx-2">•</span>
              <span>{{ recipient.role === 'SUPER_ADMIN' ? 'Super Admin' : 'Admin' }}</span>
            </VListItemSubtitle>
          </VListItem>
        </VList>
      </VCardText>

      <VCardActions class="pa-5 pt-0 justify-space-between">
        <VBtn variant="text" color="secondary" @click="closeDialog">
          Batal
        </VBtn>
        <VBtn color="success" prepend-icon="tabler-brand-whatsapp" :disabled="selectedRecipients.length === 0 || isLoading" @click="submitSelection">
          Kirim ke {{ selectedRecipients.length || 0 }} admin
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.detail-report-recipient__title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.detail-report-recipient__summary {
  background: rgb(var(--v-theme-surface));
}

.detail-report-recipient__list {
  max-height: 360px;
  overflow: auto;
}

.detail-report-recipient__item {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  margin-block-end: 10px;
}

.detail-report-recipient__empty {
  padding: 24px 4px 8px;
}
</style>