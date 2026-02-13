<script setup lang="ts">
import { hexToRgb } from '@layouts/utils'
import { computed } from 'vue'
import { useDisplay, useTheme } from 'vuetify'

const props = defineProps({
  seriesData: {
    type: Array as () => Array<{ name?: string, data: Array<number> }>,
    default: () => [{ data: [] }],
  },
  categories: {
    type: Array as () => Array<string>,
    default: () => [],
  },
  title: {
    type: String,
    default: 'Pengeluaran Mingguan',
  },
  height: {
    type: Number,
    default: 180,
  },
})

const vuetifyTheme = useTheme()
const display = useDisplay()

const chartSeries = computed(() => props.seriesData)

// Fungsi untuk mendapatkan warna tema dengan caching
const getThemeColors = computed(() => {
  const currentTheme = vuetifyTheme.current.value.colors
  const variableTheme = vuetifyTheme.current.value.variables
  const isDark = vuetifyTheme.global.current.value.dark

  const primaryColor = currentTheme.primary || '#7367F0'
  const surfaceColor = currentTheme['on-surface'] || '#4A4A4A'
  const disabledOpacity = variableTheme['disabled-opacity'] || 0.38

  try {
    return {
      primaryColor,
      labelPrimaryColor: `rgba(${hexToRgb(primaryColor)},0.2)`,
      labelColor: `rgba(${hexToRgb(surfaceColor)},${disabledOpacity})`,
      isDark,
    }
  }
  catch {
    return {
      primaryColor,
      labelPrimaryColor: `rgba(115, 103, 240, 0.2)`,
      labelColor: `rgba(74, 74, 74, ${disabledOpacity})`,
      isDark,
    }
  }
})

const chartOptions = computed(() => {
  const { labelPrimaryColor, labelColor, primaryColor, isDark } = getThemeColors.value

  // Menentukan tinggi berdasarkan breakpoint
  const dynamicHeight = display.smAndDown.value
    ? Math.min(props.height, 150)
    : props.height

  // Menentukan ukuran font label berdasarkan breakpoint
  const labelFontSize = display.xs.value
    ? '9px'
    : display.sm.value
      ? '10px'
      : '12px'

  // Menentukan lebar kolom berdasarkan breakpoint
  const columnWidth = display.xs.value
    ? '55%'
    : display.sm.value
      ? '45%'
      : '35%'

  // Fungsi untuk menyederhanakan angka (9K, 100K, dll)
  const simplifyNumber = (val: number) => {
    if (val >= 1000000)
      return `${Math.round(val / 1000000)}JT`
    if (val >= 1000)
      return `${Math.round(val / 1000)}K`
    return val.toString()
  }

  return {
    chart: {
      height: dynamicHeight,
      type: 'bar',
      parentHeightOffset: 0,
      toolbar: { show: false },
      animations: { enabled: display.smAndUp.value },
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
      custom: ({ series, seriesIndex, dataPointIndex, w }: { series: number[][], seriesIndex: number, dataPointIndex: number, w: any }) => {
        const day = w.config.xaxis.categories[dataPointIndex]
        const value = series[seriesIndex][dataPointIndex]
        return `<div class="simple-tooltip">${day}: ${simplifyNumber(value)}</div>`
      },
      style: {
        fontSize: display.xs.value ? '11px' : '12px',
      },
    },
    grid: {
      show: false,
      padding: {
        top: display.smAndDown.value ? -5 : -20,
        bottom: display.smAndDown.value ? -2 : -12,
        left: -10,
        right: 0,
      },
    },
    colors: [
      labelPrimaryColor,
      labelPrimaryColor,
      labelPrimaryColor,
      labelPrimaryColor,
      primaryColor,
      labelPrimaryColor,
      labelPrimaryColor,
    ],
    dataLabels: { enabled: false },
    legend: { show: false },
    xaxis: {
      categories: props.categories,
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: {
        style: {
          colors: labelColor,
          fontSize: labelFontSize,
          fontFamily: 'Public sans, sans-serif',
        },
      },
    },
    yaxis: {
      labels: { show: false },
    },
    states: {
      hover: { filter: { type: 'none' } },
      active: { filter: { type: 'darken', value: 0.85 } },
    },
    responsive: [
      {
        breakpoint: 600,
        options: {
          plotOptions: {
            bar: {
              columnWidth: '50%',
              borderRadius: 4,
            },
          },
          chart: {
            height: Math.min(props.height, 160),
          },
          grid: {
            padding: {
              top: -5,
              bottom: -2,
            },
          },
        },
      },
    ],
  }
})
</script>

<template>
  <div class="chart-container">
    <VueApexCharts
      v-if="chartSeries && chartSeries.length > 0 && chartSeries[0].data.length > 0 && categories.length > 0"
      :options="chartOptions"
      :series="chartSeries"
      :height="chartOptions.chart?.height || 180"
    />

    <div
      v-else
      class="empty-chart d-flex align-center justify-center text-center pa-4"
      :style="{ height: `${chartOptions.chart?.height || 180}px` }"
    >
      <div>
        <VIcon icon="tabler-chart-bar" size="32" class="mb-2" />
        <p class="text-caption mb-0">
          Menyiapkan data pengeluaran...
        </p>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.chart-container {
  position: relative;
  width: 100%;
  overflow: hidden;

  :deep(.apexcharts-tooltip) {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    border-radius: 8px;
    padding: 8px 12px;
    font-weight: 600;

    &.dark {
      background: #2c2c2c;
      color: #fff;
      border: 1px solid #444;
    }

    .simple-tooltip {
      font-size: 13px;
      font-family: 'Public sans', sans-serif;
    }
  }

  .empty-chart {
    background-color: rgba(var(--v-theme-surface), 0.6);
    border-radius: 12px;
    color: rgba(var(--v-theme-on-surface), 0.6);
  }
}

// Mobile specific adjustments
@media (max-width: 599px) {
  .chart-container {
    margin-left: -4px;
    margin-right: -4px;
    width: calc(100% + 8px);

    :deep(.apexcharts-xaxis-label) {
      transform: none;
      white-space: nowrap;
    }
  }
}
</style>
