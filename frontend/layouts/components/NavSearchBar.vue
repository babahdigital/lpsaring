<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

import { useConfigStore } from '@core/stores/config'
import Shepherd from 'shepherd.js'
import { withQuery } from 'ufo'

interface SearchResults {
  id: string
  title: string
  url?: string
  icon?: string
  category?: string
}

interface SearchItem extends SearchResults {
  children?: SearchResults[]
}

interface Suggestion {
  icon: string
  title: string
  url: RouteLocationRaw
}

defineOptions({
  inheritAttrs: false,
})

const configStore = useConfigStore()

interface SuggestionGroup {
  title: string
  content: Suggestion[]
}

// 👉 Is App Search Bar Visible
const isAppSearchBarVisible = ref(false)
const isLoading = ref(false)

// 👉 Default suggestions

const suggestionGroups: SuggestionGroup[] = [
  {
    title: 'Halaman Utama',
    content: [
      { icon: 'tabler-dashboard', title: 'Dashboard', url: { name: 'dashboard' } },
      { icon: 'tabler-shopping-cart', title: 'Beli Paket', url: { name: 'beli' } },
      { icon: 'tabler-history', title: 'Riwayat', url: { name: 'riwayat' } },
      { icon: 'tabler-file-text', title: 'Permintaan', url: { name: 'requests' } },
    ],
  },
  {
    title: 'Akun',
    content: [
      { icon: 'tabler-user', title: 'Profile', url: { name: 'akun-profile' } },
      { icon: 'tabler-device-desktop', title: 'Perangkat', url: { name: 'akun-perangkat' } },
      { icon: 'tabler-ban', title: 'Akun Blokir', url: { name: 'akun-blokir' } },
      { icon: 'tabler-alert-triangle', title: 'Kuota Habis', url: { name: 'akun-habis' } },
    ],
  },
  {
    title: 'Admin',
    content: [
      { icon: 'tabler-chart-bar', title: 'Admin Dashboard', url: { name: 'admin-dashboard' } },
      { icon: 'tabler-users', title: 'Kelola User', url: { name: 'admin-users' } },
      { icon: 'tabler-package', title: 'Kelola Paket', url: { name: 'admin-packages' } },
      { icon: 'tabler-receipt', title: 'Transaksi', url: { name: 'admin-transactions' } },
    ],
  },
  {
    title: 'Captive Portal',
    content: [
      { icon: 'tabler-wifi', title: 'Captive Portal', url: { name: 'captive' } },
      { icon: 'tabler-check', title: 'Terhubung', url: { name: 'captive-terhubung' } },
      { icon: 'tabler-device-mobile', title: 'Otorisasi Perangkat', url: { name: 'captive-otorisasi-perangkat' } },
    ],
  },
]

// 👉 No Data suggestion
const noDataSuggestions: Suggestion[] = [
  {
    title: 'Dashboard',
    icon: 'tabler-dashboard',
    url: { name: 'dashboard' },
  },
  {
    title: 'Beli Paket',
    icon: 'tabler-shopping-cart',
    url: { name: 'beli' },
  },
  {
    title: 'Riwayat',
    icon: 'tabler-history',
    url: { name: 'riwayat' },
  },
]

const searchQuery = ref('')

const router = useRouter()
const searchResult = ref<SearchResults[]>([])

async function fetchResults() {
  isLoading.value = true

  const { data } = await useApi<any>(withQuery('/app-bar/search', { q: searchQuery.value }))

  searchResult.value = data.value

  // ℹ️ simulate loading: we have used setTimeout for better user experience your can remove it
  setTimeout(() => {
    isLoading.value = false
  }, 500)
}

watch(searchQuery, fetchResults)

function closeSearchBar() {
  isAppSearchBarVisible.value = false
  searchQuery.value = ''
}

// 👉 redirect the selected page
function redirectToSuggestedPage(selected: Suggestion) {
  router.push(selected.url as string)
  closeSearchBar()
}

const LazyAppBarSearch = defineAsyncComponent(() => import('@core/components/AppBarSearch.vue'))
</script>

<template>
  <div
    class="d-flex align-center cursor-pointer"
    v-bind="$attrs"
    style="user-select: none;"
    @click="isAppSearchBarVisible = !isAppSearchBarVisible"
  >
    <!-- 👉 Search Trigger button -->
    <!-- close active tour while opening search bar using icon -->
    <IconBtn @click="Shepherd.activeTour?.cancel()">
      <VIcon icon="tabler-search" />
    </IconBtn>

    <span
      v-if="configStore.appContentLayoutNav === 'vertical'"
      class="d-none d-md-flex align-center text-disabled ms-2"
      @click="Shepherd.activeTour?.cancel()"
    >
      <span class="me-2">Search</span>
      <span class="meta-key">&#8984;K</span>
    </span>
  </div>

  <!-- 👉 App Bar Search -->
  <LazyAppBarSearch
    v-model:is-dialog-visible="isAppSearchBarVisible"
    :search-results="searchResult"
    :is-loading="isLoading"
    @search="searchQuery = $event"
  >
    <!-- suggestion -->
    <template #suggestions>
      <VCardText class="app-bar-search-suggestions pa-12">
        <VRow v-if="suggestionGroups">
          <VCol
            v-for="suggestion in suggestionGroups"
            :key="suggestion.title"
            cols="12"
            sm="6"
          >
            <p
              class="custom-letter-spacing text-disabled text-uppercase py-2 px-4 mb-0"
              style="font-size: 0.75rem; line-height: 0.875rem;"
            >
              {{ suggestion.title }}
            </p>
            <VList class="card-list">
              <VListItem
                v-for="item in suggestion.content"
                :key="item.title"
                class="app-bar-search-suggestion mx-4 mt-2"
                @click="redirectToSuggestedPage(item)"
              >
                <VListItemTitle>{{ item.title }}</VListItemTitle>
                <template #prepend>
                  <VIcon
                    :icon="item.icon"
                    size="20"
                    class="me-n1"
                  />
                </template>
              </VListItem>
            </VList>
          </VCol>
        </VRow>
      </VCardText>
    </template>

    <!-- no data suggestion -->
    <template #noDataSuggestion>
      <div class="mt-9">
        <span class="d-flex justify-center text-disabled mb-2">Try searching for</span>
        <h6
          v-for="suggestion in noDataSuggestions"
          :key="suggestion.title"
          class="app-bar-search-suggestion text-h6 font-weight-regular cursor-pointer py-2 px-4"
          @click="redirectToSuggestedPage(suggestion)"
        >
          <VIcon
            size="20"
            :icon="suggestion.icon"
            class="me-2"
          />
          <span>{{ suggestion.title }}</span>
        </h6>
      </div>
    </template>

    <!-- search result -->
    <template #searchResult="{ item }: { item: SearchItem }">
      <VListSubheader class="text-disabled custom-letter-spacing font-weight-regular ps-4">
        {{ item.title }}
      </VListSubheader>
      <VListItem
        v-for="list in item.children"
        :key="list.title"
        :to="list.url"
        @click="closeSearchBar"
      >
        <template #prepend>
          <VIcon
            size="20"
            :icon="list.icon"
            class="me-n1"
          />
        </template>
        <template #append>
          <VIcon
            size="20"
            icon="tabler-corner-down-left"
            class="enter-icon flip-in-rtl"
          />
        </template>
        <VListItemTitle>
          {{ list.title }}
        </VListItemTitle>
      </VListItem>
    </template>
  </LazyAppBarSearch>
</template>

<style lang="scss">
@use "@styles/variables/vuetify.scss";

.meta-key {
  border: thin solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
  block-size: 1.5625rem;
  font-size: 0.8125rem;
  line-height: 1.3125rem;
  padding-block: 0.125rem;
  padding-inline: 0.25rem;
}

.app-bar-search-dialog {
  .custom-letter-spacing {
    letter-spacing: 0.8px;
  }

  .card-list {
    --v-card-list-gap: 8px;
  }
}
</style>
