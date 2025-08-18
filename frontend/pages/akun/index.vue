<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const accountTabs = [
  { title: 'Profil', icon: 'tabler-user-circle', to: '/akun/profil' },
  { title: 'Perangkat Saya', icon: 'tabler-devices-2', to: '/akun/perangkat' },
  // Tambahkan tab lain di sini di masa depan jika perlu
]
</script>

<template>
  <div>
    <VTabs
      :model-value="route.path"
      class="mb-6"
    >
      <VTab
        v-for="tab in accountTabs"
        :key="tab.to"
        :value="tab.to"
        :to="tab.to"
        :prepend-icon="tab.icon"
      >
        {{ tab.title }}
      </VTab>
    </VTabs>

    <NuxtPage />
  </div>
</template>
