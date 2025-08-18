<script lang="ts" setup>
import { computed, ref, watch } from 'vue'

/* ──────  TIPE & PROPS  ────── */
interface UserSelectItem {
  id: string
  full_name: string
  phone_number: string
  role: 'USER' | 'ADMIN' | 'SUPER_ADMIN' | 'KOMANDAN'
}

const props = defineProps<{
  modelValue: boolean
  mode: 'admin' | 'target'
  roleFilter?: ('USER' | 'ADMIN' | 'SUPER_ADMIN' | 'KOMANDAN')[]
}>()

const emit = defineEmits(['update:modelValue', 'select'])

/* ──────  STATE  ────── */
const { $api } = useNuxtApp()
const allUsers = ref<UserSelectItem[]>([])
const loading = ref(false)
const userSearch = ref('')
const tempUser = ref<UserSelectItem | null>(null)

const dialogVisible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v),
})

const dialogTitle = computed(() =>
  props.mode === 'admin' ? 'Filter Admin Pelaku' : 'Filter Target Pengguna',
)

/* ──────  FETCH & FILTER  ────── */
async function fetchUsers() {
  if (allUsers.value.length)
    return
  loading.value = true
  try {
    const { items } = await $api<{ items: UserSelectItem[] }>('/admin/users?all=true')
    allUsers.value = items ?? []
  }
  catch (e) {
    console.error('Gagal memuat daftar pengguna:', e)
  }
  finally {
    loading.value = false
  }
}

/* ① filter peran */
const userList = computed(() => {
  if (!props.roleFilter?.length)
    return allUsers.value
  return allUsers.value.filter(u => props.roleFilter!.includes(u.role))
})

/* ② filter pencarian */
const filteredUserList = computed(() => {
  if (!userSearch.value)
    return userList.value
  const q = userSearch.value.toLowerCase()
  return userList.value.filter(u =>
    u.full_name.toLowerCase().includes(q)
    || u.phone_number.includes(q),
  )
})

/* ──────  EVENT  ────── */
function selectUser(u: UserSelectItem) { tempUser.value = u }
function confirmSelection() { if (tempUser.value) { emit('select', tempUser.value); closeDialog() } }
function closeDialog() { dialogVisible.value = false }

/* ──────  HELPER DISPLAY  ────── */
function getUserInitials(name: string) {
  return name
    .split(' ')
    .map(p => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}
function formatPhoneNumberForDisplay(phone: string) {
  return phone.startsWith('+62') ? `0${phone.slice(3)}` : phone
}

/* buka dialog → fetch */
watch(dialogVisible, (v) => {
  if (v)
    fetchUsers()
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
      <!-- title -->
      <VCardTitle class="pa-4 bg-primary d-flex align-center">
        <VIcon
          start
          :icon="mode === 'admin' ? 'tabler-user-shield' : 'tabler-user-search'"
        />
        <span class="text-white font-weight-medium">{{ dialogTitle }}</span>
        <VSpacer />
        <VBtn icon variant="text" @click="closeDialog">
          <VIcon icon="tabler-x" color="white" size="24" />
        </VBtn>
      </VCardTitle>
      <VDivider />

      <!-- search & list -->
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

        <VSheet class="user-list-container" border rounded min-height="300px">
          <div v-if="loading" class="d-flex justify-center align-center fill-height">
            <VProgressCircular indeterminate color="primary" />
          </div>

          <VList v-else lines="two" density="comfortable">
            <template v-if="filteredUserList.length">
              <VListItem
                v-for="user in filteredUserList"
                :key="user.id"
                class="user-item"
                :class="{ 'bg-light-primary': tempUser?.id === user.id }"
                @click="selectUser(user)"
              >
                <template #prepend>
                  <VAvatar color="primary" size="40">
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

            <VListItem v-else class="text-center py-8">
              <VIcon size="48" color="grey" icon="tabler-user-off" />
              <VListItemTitle class="text-grey mt-4">
                Pengguna tidak ditemukan
              </VListItemTitle>
            </VListItem>
          </VList>
        </VSheet>
      </VCardText>
      <VDivider />

      <!-- actions -->
      <VCardActions class="pa-4">
        <VBtn variant="tonal" @click="closeDialog">
          Batal
        </VBtn>
        <VSpacer />
        <VBtn color="primary" :disabled="!tempUser" @click="confirmSelection">
          Pilih Pengguna
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.user-list-container {
  max-height: 400px;
  overflow-y: auto;
}
.user-item {
  cursor: pointer;
  transition: background-color 0.2s ease-in-out;
}
.user-item:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.04);
}
</style>
