<template>
  <div v-if="isAlertVisible && promo" class="promo-announcement-container d-print-none">
    <VAlert
      v-model="isAlertVisible"
      color="primary"
      variant="tonal"
      closable
      border="start"
      class="promo-alert"
      @update:model-value="handleClose"
    >
      <template #prepend>
        <VIcon icon="tabler-info-circle" />
      </template>

      <VAlertTitle class="font-weight-bold">
        {{ promo.name }}
      </VAlertTitle>

      <div>{{ promo.description }}</div>
    </VAlert>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useCookie } from '#app';

interface Promo {
  id: string;
  name: string;
  description: string;
  event_type: string;
}

const { $api } = useNuxtApp();
const promo = ref<Promo | null>(null);
const isAlertVisible = ref(false);

const closedAlertId = useCookie<string | null>('closed_promo_alert_id', { maxAge: 60 * 60 * 24 * 7 });

const fetchAnnouncement = async () => {
  try {
    const activePromos = await $api<Promo[]>('/public/promos/active');
    
    const announcement = activePromos.find(p => p.event_type === 'GENERAL_ANNOUNCEMENT');

    if (announcement && announcement.id !== closedAlertId.value) {
      promo.value = announcement;
      isAlertVisible.value = true;
    }
  } catch (error) {
    console.error("Gagal mengambil pengumuman promo:", error);
  }
};

function handleClose() {
  if (promo.value) {
    closedAlertId.value = promo.value.id;
  }
  isAlertVisible.value = false;
}

onMounted(fetchAnnouncement);
</script>

<style scoped>
.promo-announcement-container {
  /* Beri margin agar tidak terlalu menempel dengan konten lain */
  margin: 1rem 1.5rem;
}
.promo-alert {
  border-radius: 8px;
}
</style>