<script lang="ts" setup>
import { computed, ref, watch } from 'vue'

// --- Tipe Data & Props ---
interface UserSelectItem {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'ADMIN' | 'SUPER_ADMIN' | 'KOMANDAN'
}

const props = defineProps<{
  modelValue: boolean
  mode: 'admin' | 'target'
  // [BARU] Prop untuk memfilter berdasarkan peran
  roleFilter?: ('USER' | 'ADMIN' | 'SUPER_ADMIN' | 'KOMANDAN')[]
}>()

const emit = defineEmits(['update:modelValue', 'select'])

// --- State Management ---
const { $api } = useNuxtApp()
const allUsers = ref<UserSelectItem[]>([]) // Ganti nama dari userList untuk kejelasan
const loading = ref(false)
const userSearch = ref('')
const tempSelectedUser = ref<UserSelectItem | null>(null)

const dialogVisible = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const dialogTitle = computed(() => {
  return props.mode === 'admin' ? 'Filter Admin Pelaku' : 'Filter Target Pengguna'
})

// --- Logika Fetch & Filter ---
async function fetchUsers() {
  if (allUsers.value.length > 0)
    return

  loading.value = true
  try {
    const responseData = await $api<{ items: UserSelectItem[] }>('/admin/users?all=true')
    allUsers.value = responseData.items || []
  }
  catch (e) {
    console.error('Gagal memuat daftar pengguna:', e)
  }
  finally {
    loading.value = false
  }
}

// [PERBAIKAN] Computed property sekarang memfilter berdasarkan prop roleFilter
const userList = computed(() => {
  if (!props.roleFilter || props.roleFilter.length === 0) {
    return allUsers.value // Kembalikan semua jika tidak ada filter
  }
  return allUsers.value.filter(user => props.roleFilter?.includes(user.role))
})

const filteredUserList = computed(() => {
  if (!userSearch.value)
    return userList.value // Gunakan userList yang sudah difilter
  const queryLower = userSearch.value.toLowerCase()

  return userList.value.filter(user =>
    user.full_name.toLowerCase().includes(queryLower)
    || user.phone_number.includes(queryLower),
  )
})

// ... sisa dari script setup tidak berubah ...
function selectUser(user: UserSelectItem) {
  tempSelectedUser.value = user
}

function confirmSelection() {
  if (tempSelectedUser.value) {
    emit('select', tempSelectedUser.value)
    closeDialog()
  }
}

function closeDialog() {
  dialogVisible.value = false
}

const getUserInitials = (name: string) => name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()
const formatPhoneNumberForDisplay = (phone: string) => phone.startsWith('+62') ? `0${phone.substring(3)}` : phone

watch(dialogVisible, (isOpening) => {
  if (isOpening) {
    fetchUsers()
  }
})
</script>

<template>
  <VDialog
    v-model="dialogVisible"
    max-width="600px"
    scrollable
    persistent
  >
    <VCard>
      <VCardTitle class="pa-4 bg-primary">
        <div class="dialog-titlebar">
          <div class="dialog-titlebar__title">
            <VIcon
              :icon="mode === 'admin' ? 'tabler-user-shield' : 'tabler-user-search'"
              color="white"
              size="22"
            />
            <span class="text-white font-weight-medium">{{ dialogTitle }}</span>
          </div>
          <div class="dialog-titlebar__actions">
            <VBtn
              icon
              variant="text"
              @click="closeDialog"
            >
              <VIcon
                color="white"
                icon="tabler-x"
                size="24"
              />
            </VBtn>
          </div>
        </div>
      </VCardTitle>
      <VDivider />

      <VCardText class="pa-4">
        <VTextField
          v-model="userSearch"
          label="Cari nama atau nomor telepon..."
          prepend-inner-icon="tabler-search"
          variant="outlined"
          density="comfortable"
          autofocus
          clearable
          class="mb-4"
        />

        <VSheet
          class="user-list-container"
          border
          rounded
          min-height="300px"
        >
          <div
            v-if="loading"
            class="d-flex justify-center align-center fill-height"
          >
            <VProgressCircular
              indeterminate
              color="primary"
            />
          </div>
          <AppPerfectScrollbar v-else class="user-list-scroll">
            <VList
              lines="two"
              density="comfortable"
            >
              <template v-if="filteredUserList.length > 0">
                <VListItem
                  v-for="user in filteredUserList"
                  :key="user.id"
                  class="user-item"
                  :class="{ 'bg-light-primary': tempSelectedUser?.id === user.id }"
                  @click="selectUser(user)"
                >
                  <template #prepend>
                    <VAvatar
                      color="primary"
                      size="40"
                    >
                      <span class="text-white">{{ getUserInitials(user.full_name) }}</span>
                    </VAvatar>
                  </template>
                  <VListItemTitle class="font-weight-medium">
                    {{ user.full_name }}
                  </VListItemTitle>
                  <VListItemSubtitle class="text-medium-emphasis">
                    {{ formatPhoneNumberForDisplay(user.phone_number) }} ({{ user.role }})
                  </VListItemSubtitle>
                </VListItem>
              </template>
              <VListItem
                v-else
                class="text-center py-8"
              >
                <VIcon
                  size="48"
                  color="grey"
                  icon="tabler-user-off"
                />
                <VListItemTitle class="text-grey mt-4">
                  Pengguna tidak ditemukan
                </VListItemTitle>
              </VListItem>
            </VList>
          </AppPerfectScrollbar>
        </VSheet>
      </VCardText>
      <VDivider />

      <VCardActions class="pa-4">
        <VBtn
          variant="tonal"
          @click="closeDialog"
        >
          Batal
        </VBtn>
        <VSpacer />
        <VBtn
          color="primary"
          :disabled="!tempSelectedUser"
          @click="confirmSelection"
        >
          Pilih Pengguna
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.user-list-container {
  max-height: 400px;
}
.user-list-scroll {
  max-height: 400px;
}
.user-item {
  cursor: pointer;
  transition: background-color 0.2s ease-in-out;
}
.user-item:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.04);
}
</style>
