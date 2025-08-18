<script setup lang="ts">
import { computed, defineAsyncComponent, h } from 'vue'

defineProps({
  type: {
    type: String as () => 'kuota' | 'pendapatan',
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  subtitle: String,
  value: [String, Number],
  change: Number,
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

const currentMonth = computed(() => new Date().toLocaleString('id-ID', { month: 'long' }))
</script>

<template>
  <VCard class="h-100">
    <VCardItem :class="{ 'pb-sm-8': type === 'kuota' }">
      <VCardTitle>{{ title }}</VCardTitle>
      <VCardSubtitle v-if="subtitle">
        {{ subtitle }}
      </VCardSubtitle>
    </VCardItem>

    <VCardText
      v-if="type === 'kuota'"
      class="pt-sm-4"
    >
      <VRow>
        <VCol
          cols="12"
          sm="5"
          class="d-flex flex-column align-self-end"
        >
          <div class="d-flex align-center gap-2 mb-3 flex-wrap">
            <h4 class="text-h2">
              {{ value }}
            </h4>
            <VChip
              v-if="typeof change === 'number'"
              label
              size="small"
              :color="change >= 0 ? 'success' : 'error'"
            >
              {{ change >= 0 ? '+' : '' }}{{ change.toFixed(1) }}%
            </VChip>
          </div>
        </VCol>
        <VCol
          cols="12"
          sm="7"
          class="mt-auto"
        >
          <VueApexCharts
            v-if="options.chart && series && series.length > 0 && series[0]?.data?.length > 0"
            :options="options"
            :series="series"
            :height="150"
          />
          <div
            v-else
            class="d-flex align-center justify-center text-center"
            style="height: 150px;"
          >
            <p class="text-disabled">
              Memuat data chart...
            </p>
          </div>
        </VCol>
      </VRow>
    </VCardText>

    <template v-if="type === 'pendapatan'">
      <VCardText>
        <p class="mb-0">
          Total Penjualan Bulan {{ currentMonth }}
        </p>
        <h4 class="text-h4">
          {{ value }}
        </h4>
      </VCardText>
      <VueApexCharts
        v-if="options.chart && series && series.length > 0 && series[0]?.data?.length > 0"
        :options="options"
        :series="series"
        :height="122"
      />
      <div
        v-else
        class="d-flex align-center justify-center text-center pb-4"
        style="height: 122px;"
      >
        <p class="text-disabled">
          Memuat data chart...
        </p>
      </div>
    </template>
  </VCard>
</template>
