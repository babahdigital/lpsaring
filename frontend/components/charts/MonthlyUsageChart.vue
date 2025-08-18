<script setup lang="ts">
import type { ApexOptions } from 'apexcharts'

import { computed, defineAsyncComponent, nextTick, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'

import type { MonthlyUsageResponse } from '~/types/user'

// Menggunakan composable yang sudah di-refactor dan diperbaiki
import { useChartContainerReady } from './composables/useChartContainerReady'
import { processMonthlyDataForChart } from './composables/useMonthlyDataProcessing'
import { useMonthlyTheme } from './composables/useMonthlyTheme'
import {
  formatQuotaForDisplay,
  getRefactoredMonthlyOptions,
} from './composables/utils/chartUtils'

const props = defineProps<{
  monthlyData: MonthlyUsageResponse | null
  parentLoading: boolean
  parentError: any | null
  dashboardRenderKey: number
}>()

// Composable untuk logika tema
const {
  vuetifyTheme,
  chartPrimaryColor,
  legendColor,
  themeBorderColor,
  themeLabelColor,
  errorDisplayColor,
} = useMonthlyTheme()

// Composable untuk inisialisasi dan penanganan error
const {
  chartContainerRef,
  isChartReadyToRender,
  chartContainerFailedOverall,
  monthlyChartKey,
  devErrorMessage,
  attemptSetReady,
  retryChartInit,
} = useChartContainerReady()

const { mobile } = useDisplay()
const chartRef = ref<any>(null)
const chartNoDataTextFromLogic = ref('Belum ada riwayat penggunaan.')
const monthlyUsageChartOptions = ref<ApexOptions>({})
const monthlyUsageChartSeries = ref<{ name: string, data: number[], meta?: any }[]>([])
const dataProcessed = ref(false)
const hasValidProcessedData = ref(false)
const totalUsageMb = ref(0)

// Komponen chart dimuat secara asynchronous
const VueApexCharts = defineAsyncComponent(() =>
  import('vue3-apexcharts').then(m => m.default),
)

// Menghitung total penggunaan dari data yang sudah diproses untuk efisiensi
const totalMonthlyUsageFormatted = computed(() => {
  if (hasValidProcessedData.value) {
    const { useGigaByteScale } = processMonthlyDataForChart(props.monthlyData?.monthly_data)
    const value = useGigaByteScale ? totalUsageMb.value / 1024 : totalUsageMb.value
    return formatQuotaForDisplay(value, useGigaByteScale)
  }
  return formatQuotaForDisplay(0, false)
})

// Watcher utama yang mengatur state dan memperbarui chart
watch(
  () => [
    props.monthlyData,
    props.parentLoading,
    props.parentError,
    vuetifyTheme.current.value.dark,
    isChartReadyToRender.value,
    chartContainerFailedOverall.value,
  ],
  () => {
    dataProcessed.value = !props.parentLoading
    const isDark = vuetifyTheme.current.value.dark
    let currentNoDataText = 'Belum ada riwayat penggunaan.'

    // Menentukan teks 'no data' berdasarkan state saat ini
    if (chartContainerFailedOverall.value) {
      currentNoDataText = 'Area chart tidak dapat disiapkan.'
    }
    else if (props.parentLoading) {
      currentNoDataText = 'Memuat data chart...'
    }
    else if (!isChartReadyToRender.value) {
      currentNoDataText = 'Menyiapkan area chart...'
    }
    else if (props.parentError) {
      currentNoDataText = 'Gagal memuat data riwayat bulanan.'
    }

    // Memproses data dari API
    const processed = processMonthlyDataForChart(props.monthlyData?.monthly_data)
    hasValidProcessedData.value = processed.isValid && !processed.allZero
    totalUsageMb.value = processed.totalUsageMb // Simpan total penggunaan

    if (!props.parentLoading && !props.parentError && !chartContainerFailedOverall.value) {
      if (!processed.isValid)
        currentNoDataText = 'Format data tidak valid.'
      else if (processed.allZero)
        currentNoDataText = 'Belum ada riwayat penggunaan.'
      else
        currentNoDataText = '' // Kosongkan jika ada data
    }
    chartNoDataTextFromLogic.value = currentNoDataText

    // Menyiapkan series untuk ApexCharts
    monthlyUsageChartSeries.value = [{
      name: processed.yAxisTitle,
      data: processed.seriesData,
      meta: {
        useGbScale: processed.useGigaByteScale,
        originalMonthYears: processed.originalMonthYear,
      },
    }]

    // Menyiapkan options untuk ApexCharts
    const baseOpts = getRefactoredMonthlyOptions(
      currentNoDataText,
      isDark,
      chartPrimaryColor.value,
      themeBorderColor.value,
      themeLabelColor.value,
      legendColor.value,
      mobile.value,
    )

    monthlyUsageChartOptions.value = {
      ...baseOpts,
      xaxis: { ...baseOpts.xaxis, categories: processed.categories },
      yaxis: { ...baseOpts.yaxis, max: processed.displayMax },
      tooltip: {
        ...baseOpts.tooltip,
        custom({ series, seriesIndex, dataPointIndex, w }: {
          series: number[][]
          seriesIndex: number
          dataPointIndex: number
          w: any
        }) {
          const meta = w.globals.initialSeries[seriesIndex]?.meta
          const originalMY = meta?.originalMonthYears?.[dataPointIndex] || ''
          let displayCategory = w.globals.labels[dataPointIndex] || ''

          if (originalMY) {
            try {
              const [year, month] = originalMY.split('-').map(Number)
              displayCategory = new Date(year, month - 1).toLocaleString('id-ID', { month: 'long', year: 'numeric' })
            }
            catch { /* Biarkan displayCategory default */ }
          }

          const value = series?.[seriesIndex]?.[dataPointIndex] ?? 0
          const formattedValue = formatQuotaForDisplay(value, meta?.useGbScale || false)

          return `<div class="apexcharts-tooltip-custom vuexy-tooltip custom-tooltip"><span>${displayCategory}: <strong>${formattedValue}</strong></span></div>`
        },
      },
      dataLabels: {
        ...baseOpts.dataLabels,
        formatter: (val: number, opts: any) => {
          const useGb = opts.w.config.series[opts.seriesIndex]?.meta?.useGbScale || false
          return formatQuotaForDisplay(val as number, useGb, true)
        },
      },
      noData: {
        ...baseOpts.noData,
        style: { ...baseOpts.noData?.style, color: chartContainerFailedOverall.value || props.parentError ? errorDisplayColor.value : themeLabelColor.value },
      },
    }

    // Memperbarui chart jika sudah siap
    if (chartRef.value && isChartReadyToRender.value && !props.parentLoading && !chartContainerFailedOverall.value) {
      nextTick(() => {
        chartRef.value?.updateOptions(monthlyUsageChartOptions.value, false, true, true)
        chartRef.value?.updateSeries(monthlyUsageChartSeries.value, true)
      })
    }
  },
  { deep: true, immediate: true },
)

// Trigger inisialisasi chart saat komponen di-render ulang oleh parent
watch(() => props.dashboardRenderKey, attemptSetReady, { immediate: true })

const showLoadingOverlay = computed(() => props.parentLoading || (!isChartReadyToRender.value && !chartContainerFailedOverall.value && !props.parentError))
</script>

<template>
  <div class="chart-error-boundary">
    <template v-if="!chartContainerFailedOverall">
      <VCard class="vuexy-card" min-height="460" height="100%" :class="{ 'vuexy-card-shadow': vuetifyTheme.current.value.dark }">
        <VCardItem class="vuexy-card-header pt-5 pb-2">
          <VCardTitle class="text-h6 vuexy-card-title mb-1">
            <VIcon icon="tabler-chart-bar" class="me-2" />Penggunaan Kuota Bulanan
          </VCardTitle>
          <div v-if="!parentLoading && !parentError && hasValidProcessedData" class="text-h5 font-weight-semibold">
            {{ totalMonthlyUsageFormatted }}
          </div>
          <div v-else-if="!parentLoading && !parentError && !hasValidProcessedData && dataProcessed" class="text-body-2 text-medium-emphasis">
            {{ chartNoDataTextFromLogic }}
          </div>
          <div v-else class="text-body-2" style="min-height: 28px;">
            &nbsp;
          </div>
        </VCardItem>

        <VCardText ref="chartContainerRef" class="pt-0 chartbulan d-flex flex-column chart-container">
          <div v-if="showLoadingOverlay" class="vuexy-loading-overlay">
            <VProgressCircular indeterminate :size="48" :width="4" color="primary" class="vuexy-spinner" />
            <div class="loading-text text-primary mt-3">
              {{ parentLoading ? 'Memuat Data...' : 'Menyiapkan Chart...' }}
            </div>
          </div>

          <div class="flex-grow-1">
            <VueApexCharts
              v-if="VueApexCharts && isChartReadyToRender && !chartContainerFailedOverall && !showLoadingOverlay"
              ref="chartRef"
              :key="monthlyChartKey"
              :options="monthlyUsageChartOptions"
              :series="monthlyUsageChartSeries"
              type="bar"
              height="310"
              class="mt-2"
            />
            <div v-else class="chart-fallback-container" :style="{ height: '310px' }">
              <VProgressCircular v-if="!parentLoading" indeterminate size="40" color="primary" />
              <p v-if="!parentLoading" class="text-caption mt-2 text-medium-emphasis">
                Memuat komponen chart...
              </p>
            </div>
          </div>

          <div class="text-caption text-medium-emphasis mt-3 px-1 halus">
            Penggunaan kuota dilacak dalam waktu UTC +8, yang mungkin berbeda dengan waktu perangkat Anda.
          </div>
        </VCardText>
      </VCard>
    </template>

    <VAlert
      v-else
      type="error"
      variant="tonal"
      prominent
      border="start"
      class="chart-error-fallback vuexy-card vuexy-alert"
    >
      <template #prepend>
        <VIcon size="28" class="me-2">
          tabler-alert-circle-filled
        </VIcon>
      </template>
      <div class="ms-1">
        <h6 class="text-h6 mb-1">
          Gagal Memuat Chart Bulanan
        </h6>
        <p class="text-body-2 mb-3">
          Terjadi masalah saat mencoba menyiapkan atau menampilkan chart.
        </p>
        <VBtn variant="tonal" :color="errorDisplayColor" class="mt-1" size="small" @click="retryChartInit">
          <VIcon start icon="tabler-refresh" /> Coba Lagi
        </VBtn>
        <div v-if="devErrorMessage" class="dev-error-overlay-message mt-3">
          <strong>Pesan Error (Mode Pengembangan):</strong><br />{{ devErrorMessage }}
        </div>
      </div>
    </VAlert>
  </div>
</template>

<style scoped>
/* Semua style dari file asli dipertahankan, tidak perlu diubah */
.vuexy-card {
  border-radius: 0.75rem;
  transition: box-shadow 0.25s ease;
  display: flex;
  flex-direction: column;
}
.vuexy-card:hover {
  box-shadow: 0 4px 25px 0 rgba(var(--v-shadow-key-umbra-color), 0.15);
}
.vuexy-card-shadow {
  box-shadow: 0 4px 18px 0 rgba(var(--v-shadow-key-umbra-color), 0.12);
}
.vuexy-card-header {
  background: rgba(var(--v-theme-primary), 0.05);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 0.75rem 0.75rem 0 0;
}
.vuexy-card-title {
  color: rgba(var(--v-theme-primary), 1);
  font-weight: 600;
  letter-spacing: 0.15px;
  display: flex;
  align-items: center;
}
.chart-container {
  position: relative;
  z-index: 1;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}
.vuexy-loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(var(--v-theme-surface), 0.85);
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: inherit;
  backdrop-filter: blur(2px);
}
.vuexy-spinner {
  filter: drop-shadow(0 2px 8px rgba(var(--v-theme-primary), 0.2));
}
.loading-text {
  font-weight: 600;
  letter-spacing: 0.5px;
  animation: pulse 1.5s infinite ease-in-out;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}
.halus { margin: 0.5rem 1rem 1.5rem 1rem; line-height: 1.4; text-align: center; font-size: 0.8125rem; }
.chartbulan { padding: 0rem 0.5rem; margin-top: 0rem; display: flex; flex-direction: column; flex-grow: 1; }
.vue-apexcharts { max-width: 100%; direction: ltr; padding-top: 20px; }
.chart-fallback-container { display: flex; flex-direction: column; justify-content: center; align-items: center; width: 100%; flex-grow: 1; padding: 1rem; text-align: center; }
.dev-error-overlay-message {
  background-color: rgba(var(--v-theme-error), 0.1);
  color: rgba(var(--v-theme-error), 1);
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 100px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-theme-error), 0.3);
  text-align: left;
  width: 100%;
  box-sizing: border-box;
}
.vuexy-alert {
  border-radius: 0.75rem;
}
.chart-error-fallback.vuexy-card {
    padding: 1.5rem;
    text-align: center;
    background: rgba(var(--v-theme-error), 0.05);
    border: 1px solid rgba(var(--v-theme-error), 0.2);
    color: rgba(var(--v-theme-on-error-container));
}
.chart-error-fallback .v-icon { color: rgba(var(--v-theme-error)) !important; }
.chart-error-fallback .text-h6 { color: rgba(var(--v-theme-error)); font-weight: 600; }
.chart-error-fallback .text-body-2 { color: rgba(var(--v-theme-on-error-container), 0.8);}

@media (max-width: 599.98px) {
  .halus { margin-top: 0.5rem; font-size: 0.75rem; margin-bottom: 0.75rem; }
  .v-card-item .v-card-title { font-size: 1rem; }
  .v-card-item .text-h5 { font-size: 1.25rem !important; }
  .chartbulan { padding: 0 0.25rem; }
}
</style>

<style>
.chart-error-boundary {
  position: relative;
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.apexcharts-tooltip-custom.vuexy-tooltip.custom-tooltip {
  background-color: rgb(var(--v-theme-surface-light, var(--v-theme-surface))) !important;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important;
  border-radius: 6px !important;
  padding: 0.5rem 0.75rem !important;
  font-size: 0.8125rem !important;
  box-shadow: 0px 4px 8px -4px rgba(var(--v-shadow-key-umbra-color), 0.2), 0px 8px 16px -4px rgba(var(--v-shadow-key-penumbra-color), 0.14), 0px 6px 6px -6px rgba(var(--v-shadow-key-ambient-color), 0.12) !important;
  max-width: 250px;
  text-align: center;
}
</style>
