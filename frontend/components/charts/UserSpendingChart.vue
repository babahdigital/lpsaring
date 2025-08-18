<script setup lang="ts">
import type { ApexOptions } from 'apexcharts'

import { hexToRgb } from '@layouts/utils'
import { computed, ref, watch } from 'vue'
import VueApexCharts from 'vue3-apexcharts'
import { useDisplay, useTheme } from 'vuetify'

const props = withDefaults(
  defineProps<{
    seriesData?: Array<{ name?: string, data: number[] }>
    categories?: string[]
    title?: string
    height?: number
  }>(),
  {
    seriesData: () => [{ data: [] }],
    categories: () => [],
    title: 'Pengeluaran Mingguan',
    height: 180,
  },
)

const vuetifyTheme = useTheme()
const display = useDisplay()
const chartRef = ref<any>(null)

/* ------------------------------------------------------------------ */
/* ✅  strict-boolean — gunakan check eksplisit                       */
/* ------------------------------------------------------------------ */
const isLoading = computed(() => {
  const sd = props.seriesData
  const cat = props.categories

  const hasSeriesArray = Array.isArray(sd) && sd.length > 0
  const hasDataArray
    = hasSeriesArray && Array.isArray(sd?.[0]?.data) && (sd?.[0]?.data?.length ?? 0) > 0
  const hasCategoryArray = Array.isArray(cat) && cat.length > 0

  return !(hasSeriesArray && hasDataArray && hasCategoryArray)
})

/* Tema & warna — tak berubah */
const getThemeColors = computed(() => {
  const c = vuetifyTheme.current.value.colors
  const v = vuetifyTheme.current.value.variables
  const isDark = vuetifyTheme.global.current.value.dark

  const primary = c.primary ?? '#7367F0'
  const surface = c['on-surface'] ?? '#4A4A4A'
  const disOp = Number(v['disabled-opacity'] ?? 0.38)
  const primaryRgb = hexToRgb(primary)

  return {
    primary,
    labelPrimary: primaryRgb
      ? `rgba(${primaryRgb}, 0.2)`
      : 'rgba(115, 103, 240, 0.2)',
    label: `rgba(${hexToRgb(surface)}, ${disOp})`,
    isDark,
  }
})

const chartOptions = computed<ApexOptions>(() => {
  const { labelPrimary, label, primary, isDark } = getThemeColors.value
  const h = display.smAndDown.value ? 160 : props.height
  const fontSize = display.xs.value ? '9px' : '12px'
  const columnWidth = display.xs.value ? '55%' : '35%'

  const simplify = (val: number) => {
    if (val >= 1_000_000)
      return `${(val / 1_000_000).toFixed(1)}JT`
    if (val >= 1000)
      return `${Math.round(val / 1000)}K`
    return val.toLocaleString('id-ID')
  }

  const colors = (props.categories ?? []).map((_, i) => {
    const highlight = i === (props.categories?.length ?? 0) - 1
    return highlight ? primary : labelPrimary
  })

  return {
    chart: {
      height: h,
      type: 'bar',
      parentHeightOffset: 0,
      toolbar: { show: false },
      animations: { enabled: !display.smAndDown.value },
    },
    plotOptions: {
      bar: {
        barHeight: '75%',
        columnWidth,
        startingShape: 'rounded',
        endingShape: 'rounded',
        borderRadius: display.xs.value ? 4 : 5,
        distributed: true,
      },
    },
    tooltip: {
      enabled: true,
      theme: isDark ? 'dark' : 'light',
      custom({ series, seriesIndex, dataPointIndex, w }) {
        const day = w.config.xaxis.categories[dataPointIndex]
        const val = series[seriesIndex][dataPointIndex]
        return `<div class="simple-tooltip">${day}: ${val.toLocaleString(
          'id-ID',
          { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 },
        )}</div>`
      },
    },
    grid: { show: false, padding: { top: -20, bottom: -12, left: -10, right: 0 } },
    colors,
    dataLabels: { enabled: false },
    legend: { show: false },
    xaxis: {
      categories: props.categories,
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: {
        style: {
          colors: label,
          fontSize,
          fontFamily: 'Public sans, sans-serif',
        },
      },
    },
    yaxis: {
      labels: {
        show: !display.smAndDown.value,
        offsetX: -15,
        formatter: simplify,
        style: {
          colors: label,
          fontSize: '11px',
          fontFamily: 'Public sans, sans-serif',
        },
      },
    },
    states: {
      hover: { filter: { type: 'none' } },
      active: { filter: { type: 'darken', value: 0.85 } },
    },
    noData: {
      text: 'Menyiapkan data pengeluaran...',
      align: 'center',
      verticalAlign: 'middle',
      style: { color: label, fontSize: '14px' },
    },
  }
})

watch(
  () => [props.seriesData, props.categories, vuetifyTheme.current.value.dark],
  ([newSeries, newCategories]) => {
    if (!chartRef.value || isLoading.value)
      return
    chartRef.value.updateOptions(
      { xaxis: { categories: newCategories }, ...chartOptions.value },
      false,
      true,
      true,
    )
    chartRef.value.updateSeries(newSeries, true)
  },
  { deep: true },
)
</script>

<template>
  <div class="chart-container">
    <VueApexCharts
      ref="chartRef"
      type="bar"
      :options="chartOptions"
      :series="props.seriesData"
      :height="chartOptions.chart?.height"
    />
    <div
      v-if="isLoading"
      class="empty-chart d-flex align-center justify-center text-center pa-4"
      :style="{ height: `${chartOptions.chart?.height || 180}px` }"
    >
      <div>
        <VIcon icon="tabler-loader-2" size="32" class="mb-2 spinning" />
        <p class="text-caption mb-0">
          Memuat data pengeluaran…
        </p>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.chart-container { position: relative; width: 100%; overflow: hidden; }
:deep(.apexcharts-tooltip) .simple-tooltip { padding: 8px 12px; font-weight: 600; font-size: 13px; font-family: 'Public sans', sans-serif; }
.empty-chart { position: absolute; inset: 0; background: rgba(var(--v-theme-surface), 0.6); border-radius: 12px; color: rgba(var(--v-theme-on-surface), 0.6); z-index: 1; }
.spinning { animation: spin 1.5s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
