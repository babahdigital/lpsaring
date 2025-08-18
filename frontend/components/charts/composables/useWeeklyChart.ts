/* -------------------------------------------------------------------------- */
/* IMPORT                                                                     */
/* -------------------------------------------------------------------------- */
import type { ApexOptions } from 'apexcharts'

import { hexToRgb } from '@layouts/utils'
import { watchDebounced } from '@vueuse/core'
import {
  computed,
  defineAsyncComponent,
  h,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue'
import { useDisplay, useTheme } from 'vuetify'

import type { User, WeeklyUsageResponse } from '~/types/user'

/* -------------------------------------------------------------------------- */
/* STATE & TIPE                                                               */
/* -------------------------------------------------------------------------- */
const chartComponentName = 'WeeklyUsageChart'

interface ChartProps {
  quotaData: User | null
  weeklyUsageData: WeeklyUsageResponse | null
  parentLoading: boolean
  parentError: any | null
  dashboardRenderKey: number
}
interface ChartEmits { (e: 'refresh'): void }

interface ChartSeries { name: string, data: number[] }

/* -------------------------------------------------------------------------- */
/* MAIN COMPOSABLE                                                            */
/* -------------------------------------------------------------------------- */
export function useWeeklyChart(props: ChartProps, emit: ChartEmits) {
  const { smAndDown, mobile } = useDisplay()
  const vuetifyTheme = useTheme()

  const VueApexCharts = defineAsyncComponent(() =>
    import('vue3-apexcharts')
      .then(m => m.default)
      .catch((err) => {
        console.warn(`${chartComponentName}: gagal memuat VueApexCharts – ${err.message}`)
        return { render: () => h('div', { class: 'text-caption text-error pa-4' }, 'Chart gagal dimuat') }
      }),
  )

  const chartContainerActualRef = ref<HTMLElement | null>(null)
  const weeklyChartRef = ref<any>(null)
  const isChartReadyToRender = ref(false)
  const chartContainerFailedOverall = ref(false)
  const devErrorMessage = ref<string | null>(null)
  const weeklyChartKey = ref(0)
  const weeklyDataProcessed = ref(false)
  const isLoadingInternalProcessing = ref(false)
  const chartNoDataTextFromLogic = ref('Belum ada penggunaan minggu ini.')

  /* Warna & utilitas */
  const primaryColor = computed(() => vuetifyTheme.current.value.colors.primary)
  const errorDisplayColor = computed(() => vuetifyTheme.current.value.colors.error)
  const infoDisplayColor = computed(() => vuetifyTheme.current.value.colors.info)
  const onSurfaceColorRgb = computed(() => hexToRgb(vuetifyTheme.current.value.colors['on-surface']))
  const disabledOpacity = computed(() => Number(vuetifyTheme.current.value.variables['disabled-opacity'] ?? 0.38))

  const chartHeight = computed(() => (mobile.value ? 130 : smAndDown.value ? 140 : 161))
  const chartHeightInPx = computed(() => `${chartHeight.value}px`)

  const EMPTY_7: number[] = Array.from({ length: 7 }, () => 0)

  function formatQuota(v?: number | null) {
    const n = v ?? 0
    return n >= 1024 ? `${(n / 1024).toFixed(2)} GB` : `${n.toFixed(0)} MB`
  }

  /* ---------------------------------------------------------------------- */
  /* SERIES & OPTIONS                                                       */
  /* ---------------------------------------------------------------------- */
  const quotaWeeklyBarSeries = ref<ChartSeries[]>([
    { name: 'Penggunaan Harian', data: [...EMPTY_7] },
  ])

  const quotaWeeklyBarOptions = computed<ApexOptions>(() => {
    const today = new Date()
    const categories = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(today)
      d.setDate(today.getDate() - (6 - i))
      return d.toLocaleDateString('id-ID', { weekday: 'long' })
    })

    const seriesData = quotaWeeklyBarSeries.value[0]?.data ?? []
    const allZero = seriesData.every(n => n === 0)
    const primaryRgb = hexToRgb(primaryColor.value) ?? '115,103,240'
    const inactive = `rgba(${primaryRgb}, ${disabledOpacity.value})`
    const axisColor = onSurfaceColorRgb.value != null ? `rgba(${onSurfaceColorRgb.value}, ${disabledOpacity.value})` : '#000'

    return {
      chart: {
        parentHeightOffset: 0,
        type: 'bar',
        height: chartHeight.value,
        toolbar: { show: false },
      },
      plotOptions: {
        bar: {
          columnWidth: smAndDown.value ? '45%' : '38%',
          borderRadius: 4,
          distributed: true,
        },
      },
      grid: { show: false, padding: { left: -10, right: -10 } },
      colors: seriesData.map((n, i) => (i === 6 && n > 0 && !allZero) ? primaryColor.value : inactive),
      dataLabels: { enabled: false },
      legend: { show: false },
      xaxis: {
        categories,
        labels: {
          formatter: v => (mobile.value ? v.slice(0, 2) : v.slice(0, 3)),
          style: { colors: axisColor, fontFamily: 'inherit' },
        },
        axisBorder: { show: false },
        axisTicks: { show: false },
      },
      yaxis: { labels: { show: false } },
      tooltip: {
        theme: vuetifyTheme.current.value.dark ? 'dark' : 'light',
        custom({ series, dataPointIndex, w }) {
          const day = w.globals.labels[dataPointIndex]
          const val = series[0][dataPointIndex]
          return `<div class="apexcharts-tooltip-custom"><span>${day}: <strong>${formatQuota(val)}</strong></span></div>`
        },
        style: { fontFamily: 'inherit' },
      },
      noData: {
        text: chartNoDataTextFromLogic.value,
        align: 'center',
        style: { color: axisColor },
      },
    }
  })

  /* ---------------------------------------------------------------------- */
  /* MUTASI DATA                                                            */
  /* ---------------------------------------------------------------------- */
  function updateChartData() {
    isLoadingInternalProcessing.value = true

    if (props.parentLoading) {
      weeklyDataProcessed.value = false
      if (quotaWeeklyBarSeries.value[0]) {
        quotaWeeklyBarSeries.value[0].data = [...EMPTY_7]
      }
      chartNoDataTextFromLogic.value = 'Memuat data...'
      isLoadingInternalProcessing.value = false
      return
    }

    const weeklyRaw = props.weeklyUsageData?.data

    if (Array.isArray(weeklyRaw)) {
      const sliced = weeklyRaw.slice(-7)
      while (sliced.length < 7) sliced.unshift(0)
      const cleanData: number[] = sliced.map(v => Number(v) || 0)

      quotaWeeklyBarSeries.value = [
        { name: 'Penggunaan Harian', data: cleanData },
      ]

      chartNoDataTextFromLogic.value = cleanData.every(d => d === 0)
        ? 'Belum ada penggunaan minggu ini.'
        : ''
    }
    else {
      if (quotaWeeklyBarSeries.value[0]) {
        quotaWeeklyBarSeries.value[0].data = [...EMPTY_7]
      }
      chartNoDataTextFromLogic.value = 'Data mingguan tidak tersedia.'
    }

    weeklyDataProcessed.value = true
    isLoadingInternalProcessing.value = false
  }

  /* ---------------------------------------------------------------------- */
  /* WATCHERS & LIFE-CYCLE                                                  */
  /* ---------------------------------------------------------------------- */
  watch(
    () => [props.parentLoading, props.weeklyUsageData, props.quotaData],
    updateChartData,
    { deep: true, immediate: true },
  )

  watchDebounced(
    [() => mobile.value, () => smAndDown.value],
    () => {
      weeklyChartRef.value?.updateOptions(quotaWeeklyBarOptions.value, false, true, true)
    },
    { debounce: 150, maxWait: 500 },
  )

  onMounted(() => { isChartReadyToRender.value = true })
  onUnmounted(() => { weeklyChartRef.value?.destroy() })

  return {
    smAndDown,
    mobile,
    vuetifyTheme,
    VueApexCharts,
    chartContainerActualRef,
    isChartReadyToRender,
    chartContainerFailedOverall,
    weeklyChartRef,
    weeklyDataProcessed,
    chartHeightInPx,
    chartHeight,
    weeklyChartKey,
    chartNoDataTextFromLogic,
    devErrorMessage,
    isLoadingInternalProcessing,
    quotaWeeklyBarSeries,
    quotaWeeklyBarOptions,
    errorDisplayColor,
    infoDisplayColor,
    retryChartInit: () => {},
    handleRefresh: () => emit('refresh'),
  }
}
