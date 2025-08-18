<script setup lang="ts">
import { defineAsyncComponent, h } from 'vue'

defineProps({
  options: {
    type: Object,
    required: true,
  },
  series: {
    type: Array as () => any[],
    required: true,
  },
})

const VueApexCharts = defineAsyncComponent(() =>
  import('vue3-apexcharts').then(mod => mod.default).catch(() => {
    return { render: () => h('div', { class: 'text-caption text-error text-center pa-4' }, 'Chart Gagal Dimuat.') }
  }),
)
</script>

<template>
  <VCard class="h-100">
    <VCardItem>
      <VCardTitle>Paket Terlaris</VCardTitle>
      <VCardSubtitle>Berdasarkan jumlah penjualan bulan ini</VCardSubtitle>
    </VCardItem>
    <VCardText style="padding-bottom: 30px; padding-top: 25px;">
      <VueApexCharts
        v-if="options.chart && series.length > 0 && series.some(s => s > 0)"
        type="donut"
        height="350"
        :options="options"
        :series="series"
      />
      <div
        v-else
        class="d-flex flex-column align-center justify-center text-center"
        style="height: 350px;"
      >
        <VIcon
          icon="tabler-chart-pie-off"
          size="50"
          class="text-disabled mb-2"
        />
        <p class="text-disabled">
          Belum ada data penjualan paket bulan ini.
        </p>
      </div>
    </VCardText>
  </VCard>
</template>
