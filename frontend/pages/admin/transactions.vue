<template>
  <div class="transaction-manager">
    <VCard title="Manajemen Transaksi" class="elevation-3">
      <VCardText class="pa-6">
        <VRow class="d-flex flex-wrap gap-y-4 align-center">
          <VCol cols="12" sm="6" md="3" lg="3">
            <VTextField
              id="start-date-activator"
              :model-value="formatDate(startDate)"
              label="Tanggal Mulai"
              placeholder="Pilih tanggal"
              prepend-inner-icon="tabler-calendar"
              readonly
              clearable
              @click:clear="clearStartDate"
              density="comfortable"
              variant="outlined"
              class="date-field"
              :class="{ 'active-field': startDate }"
              hide-details="auto"
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
                  v-model="startDate"
                  @update:model-value="isStartDateMenuOpen = false"
                  no-title
                  color="primary"
                  :max="new Date()"
                  show-adjacent-months
                />
              </client-only>
            </VMenu>
          </VCol>

          <VCol cols="12" sm="6" md="3" lg="3">
            <VTextField
              id="end-date-activator"
              :model-value="formatDate(endDate)"
              label="Tanggal Akhir"
              placeholder="Pilih tanggal"
              prepend-inner-icon="tabler-calendar"
              readonly
              clearable
              @click:clear="clearEndDate"
              :disabled="!startDate"
              density="comfortable"
              variant="outlined"
              class="date-field"
              :class="{ 'active-field': endDate }"
              hide-details="auto"
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
                  v-model="endDate"
                  @update:model-value="isEndDateMenuOpen = false"
                  no-title
                  color="primary"
                  :min="startDate"
                  :max="new Date()"
                  show-adjacent-months
                />
              </client-only>
            </VMenu>
          </VCol>
          
          <VCol cols="12" sm="6" md="3" lg="3">
            <VBtn
              block
              @click="openUserFilterDialog"
              prepend-icon="tabler-user-search"
              variant="outlined"
              color="primary"
              height="48"
              class="filter-btn"
            >
              <span class="text-truncate">Filter Pengguna</span>
            </VBtn>
          </VCol>

          <VCol cols="12" sm="6" md="3" lg="3" class="d-flex align-center gap-2 flex-wrap">
            <VBtn 
              @click="applyFilter"
              prepend-icon="tabler-filter"
              color="primary"
              height="48"
              class="action-btn flex-grow-1"
            >
              Terapkan
            </VBtn>
            <VBtn 
              @click="clearAllFilters"
              prepend-icon="tabler-filter-off"
              variant="tonal"
              height="48"
              class="action-btn flex-grow-1"
            >
              Reset
            </VBtn>
          </VCol>
        </VRow>

        <VRow v-if="hasActiveFilters" class="mt-4">
          <VCol cols="12" class="d-flex flex-wrap gap-2 align-center">
            <VChip
              v-if="selectedUser"
              color="primary"
              closable
              @click:close="clearUserFilter"
              prepend-icon="tabler-user"
              size="small"
              class="active-filter-chip"
            >
              Pengguna: {{ selectedUser.full_name }}
            </VChip>
            
            <VChip
              v-if="startDate || endDate"
              color="primary"
              closable
              @click:close="clearDateFilter"
              prepend-icon="tabler-calendar"
              size="small"
              class="active-filter-chip"
            >
              Periode: {{ formattedDateRangeForChip }}
            </VChip>
          </VCol>
        </VRow>
      </VCardText>
      <VDivider />

    <VCardText class="d-flex flex-column flex-sm-row py-4 gap-4 align-stretch align-sm-center px-6">
    <div>
        <VMenu offset-y>
        <template #activator="{ props }">
            <VBtn 
            color="primary" 
            v-bind="props"
            prepend-icon="tabler-download"
            variant="tonal"
            class="export-btn"
            :loading="exportLoading"
            >
            Unduh Laporan
            </VBtn>
        </template>
        <VList density="compact">
            <VListItem @click="exportReport('pdf')">
            <template #prepend>
                <VIcon icon="tabler-file-type-pdf" class="text-error" />
            </template>
            <VListItemTitle>PDF</VListItemTitle>
            </VListItem>
            <VListItem @click="exportReport('csv')">
            <template #prepend>
                <VIcon icon="tabler-file-type-csv" class="text-success" />
            </template>
            <VListItemTitle>CSV</VListItemTitle>
            </VListItem>
        </VList>
        </VMenu>
    </div>
    
    <VSpacer class="d-none d-sm-block" />
    
    <div class="search-container">
        <VTextField
        v-model="search"
        placeholder="Cari ID Invoice..."
        density="compact"
        variant="outlined"
        clearable
        prepend-inner-icon="tabler-search"
        single-line
        hide-details
        class="search-field"
        />
    </div>
    </VCardText>
      <div class="px-6 pb-6">
        <VDataTableServer
          v-model:items-per-page="options.itemsPerPage"
          v-model:page="options.page"
          v-model:sort-by="options.sortBy"
          :headers="headers"
          :items="transactions"
          :items-length="totalTransactions"
          :loading="loading"
          class="elevation-1 rounded data-table"
        >
          <template #item.user.full_name="{ item }">
            <span class="font-weight-medium user-name">{{ item.user.full_name }}</span>
          </template>
          
          <template #item.amount="{ item }">
            <span class="font-weight-bold amount-value">{{ formatCurrency(item.amount) }}</span>
          </template>
          
          <template #item.status="{ item }">
            <VChip 
              :color="statusColorMap[item.status]" 
              size="small"
              :variant="item.status === 'PENDING' ? 'outlined' : 'flat'"
              class="status-chip"
            >
              {{ formatStatus(item.status) }}
            </VChip>
          </template>
          
          <template #item.created_at="{ item }">
            <span class="text-sm date-time">{{ formatDateTime(item.created_at) }}</span>
          </template>
          
          <template #loading>
            <div class="loading-overlay">
              <VProgressCircular indeterminate size="48" color="primary" />
              <p class="mt-4 text-primary">Memuat data...</p>
            </div>
          </template>
          
          <template #no-data>
            <div class="py-8 text-center no-data">
                <VIcon size="64" color="grey-lighten-1" icon="tabler-database-off" />
                <p class="text-grey mt-4">Tidak ada data transaksi yang ditemukan</p>
                <VBtn color="primary" variant="tonal" @click="refresh" class="mt-4">
                <VIcon start icon="tabler-refresh" />
                Muat Ulang
                </VBtn>
            </div>
          </template>

        </VDataTableServer>
      </div>
      </VCard>

    <VDialog v-model="isUserFilterDialogOpen" max-width="600px" scrollable>
      <VCard class="user-dialog">
        <VCardTitle class="pa-4 bg-primary d-flex align-center">
          <span class="text-white font-weight-medium">Pilih Pengguna</span>
          <VSpacer />
          <VBtn icon variant="text" @click="isUserFilterDialogOpen = false">
            <VIcon color="white" icon="tabler-x" size="24" />
          </VBtn>
        </VCardTitle>
        <VDivider/>
        <VCardText class="pa-4">
          <VTextField
            v-model="userSearch"
            label="Cari pengguna..."
            prepend-inner-icon="tabler-search"
            variant="outlined"
            density="comfortable"
            autofocus
            clearable
            class="mb-4 user-search"
          />
          
          <div class="mt-2 user-list-container">
            <VList lines="two" density="comfortable">
              <template v-if="filteredUserList.length > 0">
                <VListItem
                  v-for="user in filteredUserList"
                  :key="user.id"
                  @click="selectUser(user)"
                  class="cursor-pointer user-item"
                  :class="{ 'bg-light-primary': tempSelectedUser?.id === user.id }"
                >
                  <template #prepend>
                    <VAvatar color="primary" size="40">
                      <span class="text-white">{{ getUserInitials(user.full_name) }}</span>
                    </VAvatar>
                  </template>
                  <VListItemTitle class="font-weight-medium">{{ user.full_name }}</VListItemTitle>
                  <VListItemSubtitle class="text-medium-emphasis">{{ formatPhoneNumberForDisplay(user.phone_number) }}</VListItemSubtitle>
                </VListItem>
              </template>
              <VListItem v-else class="text-center py-8 no-users">
                <VIcon size="48" color="grey" icon="tabler-user-off" />
                <VListItemTitle class="text-grey mt-4">Pengguna tidak ditemukan</VListItemTitle>
              </VListItem>
            </VList>
          </div>
        </VCardText>
        <VDivider/>
        <VCardActions class="pa-4">
          <VBtn variant="tonal" @click="isUserFilterDialogOpen = false">Batal</VBtn>
          <VBtn color="primary" @click="confirmUserSelection" :disabled="!tempSelectedUser">Pilih</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
    <VSnackbar 
      v-model="snackbar.visible" 
      :color="snackbar.color" 
      :timeout="3000" 
      location="top right"
      variant="tonal"
      elevation="0"
      class="snackbar"
    >
      <div class="d-flex align-center">
        <VIcon :icon="snackbar.icon" class="me-2" />
        <span class="snackbar-text">{{ snackbar.text }}</span>
      </div>
    </VSnackbar>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { VDataTableServer } from 'vuetify/components';
import { useAuthStore } from '@/store/auth';

// --- Tipe Data ---
interface Transaction {
  id: string;
  order_id: string;
  amount: number;
  status: 'PENDING' | 'SUCCESS' | 'FAILED' | 'EXPIRED' | 'CANCELLED' | 'UNKNOWN';
  created_at: string;
  user: { full_name: string; phone_number: string; };
  package_name: string;
}
interface UserSelectItem {
  id: string;
  full_name: string;
  phone_number: string;
  role: 'USER' | 'ADMIN' | 'SUPER_ADMIN'; // Menambahkan 'role'
}

// --- State Management ---
const { $api } = useNuxtApp();
const authStore = useAuthStore();

const options = ref<InstanceType<typeof VDataTableServer>['$props']['options']>({
  page: 1,
  itemsPerPage: 10,
  sortBy: [{ key: 'created_at', order: 'desc' }],
});

const exportLoading = ref(false);
const search = ref('');
const selectedUser = ref<UserSelectItem | null>(null);
const tempSelectedUser = ref<UserSelectItem | null>(null);

const startDate = ref<Date | null>(null);
const endDate = ref<Date | null>(null);
const isStartDateMenuOpen = ref(false);
const isEndDateMenuOpen = ref(false);

const isUserFilterDialogOpen = ref(false);
const userList = ref<UserSelectItem[]>([]);
const userSearch = ref('');

const snackbar = ref({
  visible: false,
  text: '',
  color: 'success',
  icon: 'tabler-check'
});

// --- Data Fetching Reaktif dengan useAsyncData ---
const queryParams = computed(() => ({
  page: options.value.page,
  itemsPerPage: options.value.itemsPerPage,
  sortBy: options.value.sortBy[0]?.key ?? 'created_at',
  sortOrder: options.value.sortBy[0]?.order ?? 'desc',
  search: search.value, 
  user_id: selectedUser.value?.id,
  start_date: startDate.value ? startDate.value.toISOString().split('T')[0] : undefined,
  end_date: endDate.value ? endDate.value.toISOString().split('T')[0] : undefined,
}));

const { data: transactionData, pending: loading, error, refresh } = useAsyncData(
  'fetch-transactions',
  () => $api<{ items: Transaction[], totalItems: number }>('/admin/transactions', {
    params: queryParams.value,
  }),
  {
    watch: [queryParams],
  }
);

const transactions = computed(() => transactionData.value?.items || []);
const totalTransactions = computed(() => transactionData.value?.totalItems || 0);

watch(error, (newError) => {
  if (newError) {
    showSnackbar(newError.data?.message || 'Gagal memuat data transaksi', 'error');
  }
});

// --- Konfigurasi & Format ---
const headers = [
  { title: 'NAMA PENGGUNA', key: 'user.full_name', sortable: false, width: '200px' },
  { title: 'ID INVOICE', key: 'order_id', sortable: true, width: '200px' },
  { title: 'PAKET', key: 'package_name', sortable: false, width: '180px' },
  { title: 'JUMLAH', key: 'amount', sortable: true, align: 'end', width: '160px' },
  { title: 'STATUS', key: 'status', sortable: true, width: '140px' },
  { title: 'TANGGAL', key: 'created_at', sortable: true, width: '200px' },
];

const statusColorMap: Record<Transaction['status'], string> = {
  SUCCESS: 'success', PENDING: 'warning', FAILED: 'error', EXPIRED: 'grey', CANCELLED: 'info', UNKNOWN: 'secondary',
};

const formatStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    SUCCESS: 'Sukses', PENDING: 'Menunggu', FAILED: 'Gagal', EXPIRED: 'Kadaluarsa', CANCELLED: 'Dibatalkan', UNKNOWN: 'Tidak Diketahui'
  };
  return statusMap[status] || status;
};

// Fungsi baru untuk format nomor telepon
const formatPhoneNumberForDisplay = (phoneNumber: string | null) => {
  if (!phoneNumber) return '';
  if (phoneNumber.startsWith('+62')) {
    return '0' + phoneNumber.substring(3);
  }
  return phoneNumber;
};

const formatCurrency = (value: number) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(value);
const formatDateTime = (dateString: string) => new Date(dateString).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const formatDate = (date: Date | null) => date ? new Date(date).toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' }) : '';

const hasActiveFilters = computed(() => !!selectedUser.value || !!startDate.value || !!endDate.value);
const formattedDateRangeForChip = computed(() => {
    if (!startDate.value && !endDate.value) return '';
    const start = startDate.value ? formatDate(startDate.value) : '...';
    const end = endDate.value ? formatDate(endDate.value) : '...';
    return `${start} - ${end}`;
});

const getPhoneNumberVariationsJS = (query: string): string[] => {
    const cleaned = query.replace(/\D/g, '');
    if (!cleaned) return [];
    const variations = new Set<string>();
    if (cleaned.startsWith('08')) {
        variations.add('+62' + cleaned.substring(1));
    }
    if (cleaned.startsWith('628')) {
        variations.add('+' + cleaned);
    }
    if (cleaned.startsWith('628')) {
        variations.add('+62' + cleaned.substring(2));
    }
    variations.add(cleaned);
    return Array.from(variations);
};

const filteredUserList = computed(() => {
  if (!userSearch.value) return userList.value;
  const queryLower = userSearch.value.toLowerCase();
  
  const phoneVariations = getPhoneNumberVariationsJS(userSearch.value);

  return userList.value.filter(user => {
    if (user.full_name.toLowerCase().includes(queryLower)) {
        return true;
    }
    if (phoneVariations.length > 0) {
        return phoneVariations.some(variation => user.phone_number.includes(variation));
    }
    return user.phone_number.includes(queryLower);
  });
});


// --- Logika & Fungsi ---
const showSnackbar = (text: string, type: 'success' | 'error' | 'warning' = 'success') => {
  const config = { success: { color: 'success', icon: 'tabler-check' }, error: { color: 'error', icon: 'tabler-alert-circle' }, warning: { color: 'warning', icon: 'tabler-alert-triangle' } }[type];
  snackbar.value = { text, color: config.color, icon: config.icon, visible: true };
};

const applyFilter = () => refresh();
const clearAllFilters = () => {
  search.value = '';
  startDate.value = null;
  endDate.value = null;
  selectedUser.value = null;
  tempSelectedUser.value = null;
};
const clearUserFilter = () => {
  selectedUser.value = null;
  tempSelectedUser.value = null;
};
const clearDateFilter = () => {
  startDate.value = null;
  endDate.value = null;
};
const clearStartDate = () => {
  startDate.value = null;
  endDate.value = null;
};
const clearEndDate = () => { endDate.value = null; };

const openUserFilterDialog = async () => {
  isUserFilterDialogOpen.value = true;
  tempSelectedUser.value = selectedUser.value;
  if (userList.value.length > 0) return;
  try {
    const responseData = await $api<{ items: UserSelectItem[] }>('/admin/users?all=true');
    if (responseData && Array.isArray(responseData.items)) {
      // Filter hanya untuk peran 'USER'
      userList.value = responseData.items.filter(user => user.role === 'USER');
    } else {
      userList.value = [];
    }
  } catch (e: any) {
    showSnackbar(e.data?.message || 'Gagal memuat daftar pengguna.', 'error');
    userList.value = [];
  }
};

const getUserInitials = (name: string) => name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
const selectUser = (user: UserSelectItem) => { tempSelectedUser.value = user; };

const confirmUserSelection = () => {
  selectedUser.value = tempSelectedUser.value;
  isUserFilterDialogOpen.value = false;
  userSearch.value = '';
};

const exportReport = async (format: 'pdf' | 'csv') => {
  if (!startDate.value) {
    showSnackbar('Pilih tanggal mulai terlebih dahulu', 'warning');
    return;
  }
  exportLoading.value = true;
  try {
    const start = startDate.value.toISOString().split('T')[0];
    const end = (endDate.value || startDate.value).toISOString().split('T')[0];
    const params = new URLSearchParams({ format, start_date: start, end_date: end });
    if (selectedUser.value) params.append('user_id', selectedUser.value.id);
    const data = await $api(`/admin/transactions/export?${params.toString()}`, { responseType: 'blob' });
    if (!data) throw new Error('Tidak ada data laporan yang diterima');
    const url = window.URL.createObjectURL(data);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `laporan-transaksi-${start}-to-${end}.${format}`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
    showSnackbar('Laporan berhasil diunduh', 'success');
  } catch (err: any) {
    showSnackbar(`Gagal mengunduh laporan: ${err.data?.message || err.message}`, 'error');
  } finally {
    exportLoading.value = false;
  }
};

useHead({ title: 'Laporan Penjualan' })
</script>

<style scoped>
.transaction-manager {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
.v-card {
  border-radius: 12px;
  overflow: hidden;
}
.date-field :deep(.v-field) {
  cursor: pointer;
}
.date-field.active-field {
  font-weight: 500;
  color: rgba(var(--v-theme-primary));
}
.filter-btn, .action-btn {
  font-weight: 500;
  letter-spacing: 0.25px;
  border-radius: 8px;
}
.active-filter-chip {
  font-weight: 500;
  border-radius: 16px;
}
.data-table :deep(th) {
  font-weight: 600 !important;
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  font-size: 13px;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.data-table :deep(td) {
  vertical-align: middle;
}
.user-name, .amount-value {
  font-weight: 500;
}
.date-time {
  color: rgba(var(--v-theme-on-surface), 0.7);
  min-height: 50px;
}
.loading-overlay, .no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
}
.user-dialog .v-card-title {
  font-size: 18px;
}
.user-list-container {
  max-height: 400px;
  overflow-y: auto;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.user-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.05);
}
.snackbar {
  font-size: 14px;
  border-radius: 8px;
}
.snackbar-text {
  font-weight: 500;
}
.search-container {
  flex: 1;
  max-width: 400px;
}
.search-field {
  width: 100%;
}

/* Perbaikan utama untuk alignment kalender */
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

/* Perbaikan tambahan untuk layout responsif */
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