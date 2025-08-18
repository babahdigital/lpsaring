import type { ApexOptions } from 'apexcharts'

/* -------------------------------------------------------------------------- */
/* TYPES & PROPS                                                              */
/* -------------------------------------------------------------------------- */
import { hexToRgb } from '@layouts/utils'
import { watchDebounced } from '@vueuse/core'
import {
  computed,
  defineAsyncComponent,
  h,
  nextTick,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue'
import { useDisplay, useTheme } from 'vuetify'

import type { MonthlyUsageData as MonthlyUsageItem, MonthlyUsageResponse } from '~/types/user'

interface ChartProps {
  monthlyUsageData: MonthlyUsageResponse | null
  parentLoading: boolean
  parentError: any | null
  dashboardRenderKey: number
}
interface ChartEmits { (e: 'refresh'): void }

/* -------------------------------------------------------------------------- */
/* MAIN HOOK                                                                  */
/* -------------------------------------------------------------------------- */
export function useMonthlyChart(props: ChartProps, emit: ChartEmits) {
  const { smAndDown, mobile } = useDisplay()
  const vuetifyTheme = useTheme()

  const VueApexCharts = defineAsyncComponent(() =>
    import('vue3-apexcharts')
      .then(m => m.default)
      .catch((err) => {
        console.warn(`[MonthlyUsageChart] gagal memuat VueApexCharts – ${err.message}`)
        return { render: () => h('div', { class: 'text-caption text-error pa-4' }, 'Chart gagal dimuat') }
      }),
  )

  const chartContainerRef = ref<HTMLElement | null>(null)
  const chartRef = ref<any>(null)
  const isReady = ref(false)
  const failed = ref(false)
  const devMessage = ref<string | null>(null)
  const chartKey = ref(0)
  const dataProcessed = ref(false)

  const primary = computed(() => vuetifyTheme.current.value.colors.primary)
  const errorColor = computed(() => vuetifyTheme.current.value.colors.error)
  const onSurfaceRgb = computed(() =>
    hexToRgb(vuetifyTheme.current.value.colors['on-surface']),
  )
  const disabledOp = computed(() =>
    Number(vuetifyTheme.current.value.variables['disabled-opacity'] ?? 0.38),
  )
  const chartHeight = computed(() =>
    mobile.value ? 130 : smAndDown.value ? 150 : 180,
  )
  const heightPx = computed(() => `${chartHeight.value}px`)

  const series = ref<{ name: string, data: number[] }[]>([
    { name: 'Pemakaian Bulanan', data: Array.from({ length: 12 }, () => 0) },
  ])

  /* ---------------------------------------------------------------------- */
  /* OPTIONS                                                                 */
  /* ---------------------------------------------------------------------- */
  const options = computed<ApexOptions>(() => {
    const now = new Date()
    const categories: string[] = []
    for (let i = 11; i >= 0; i--) {
      const d = new Date(now)
      d.setMonth(now.getMonth() - i)
      categories.push(d.toLocaleDateString('id-ID', { month: 'short', year: '2-digit' }))
    }

    const allZero = series.value[0]?.data.every(n => n === 0) ?? true
    const primaryRgb = hexToRgb(primary.value) ?? '115,103,240'
    const inactive = `rgba(${primaryRgb}, ${disabledOp.value})`
    const axisColor = `rgba(${onSurfaceRgb.value}, ${disabledOp.value})`

    return {
      chart: { type: 'bar', height: chartHeight.value, parentHeightOffset: 0, toolbar: { show: false } },
      plotOptions: { bar: { columnWidth: smAndDown.value ? '48%' : '36%', borderRadius: 4, distributed: true } },
      grid: { show: false, padding: { left: -8, right: -8 } },
      colors: (series.value[0]?.data ?? []).map((v, idx) => {
        const highlight = idx === 11 && v > 0 && !allZero
        return highlight ? primary.value : inactive
      }),
      dataLabels: { enabled: false },
      legend: { show: false },
      xaxis: {
        categories,
        labels: {
          formatter: (v: string) => (mobile.value ? v.slice(0, 3) : v),
          style: { colors: axisColor },
        },
        axisBorder: { show: false },
        axisTicks: { show: false },
      },
      yaxis: { labels: { show: false } },
      tooltip: {
        theme: vuetifyTheme.current.value.dark ? 'dark' : 'light',
        custom({ series, dataPointIndex, w }) {
          const label = w.globals.labels[dataPointIndex]
          const usage = series[0][dataPointIndex]
          return `<div class="apexcharts-tooltip-custom"><span>${label}: ${formatQuota(usage)}</span></div>`
        },
      },
      noData: {
        text: failed.value ? 'Chart gagal dimuat.' : 'Belum ada data.',
        align: 'center',
        style: { color: failed.value ? errorColor.value : axisColor },
      },
    }
  })

  /* ---------------------------------------------------------------------- */
  /* HELPERS                                                                 */
  /* ---------------------------------------------------------------------- */
  function formatQuota(v?: number | null) {
    const n = v ?? 0
    return n >= 1024 ? `${(n / 1024).toFixed(2)} GB` : `${n.toFixed(0)} MB`
  }

  /* ---------------------------------------------------------------------- */
  /* DATA MUTATION                                                           */
  /* ---------------------------------------------------------------------- */
  function updateData() {
    if (props.parentLoading) {
      dataProcessed.value = false
      if (series.value[0]) {
        series.value[0].data = Array.from({ length: 12 }, () => 0)
      }
      return
    }

    const apiArr = props.monthlyUsageData?.monthly_data ?? []
    const map = new Map<string, number>()
    apiArr.forEach((i: MonthlyUsageItem) =>
      map.set(i.month_year, Number(i.usage_mb ?? 0)),
    )

    const now = new Date()
    const dataVals: number[] = []
    for (let i = 11; i >= 0; i--) {
      const d = new Date(now)
      d.setMonth(now.getMonth() - i)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      dataVals.push(Number((map.get(key) ?? 0).toFixed(1)))
    }

    series.value = [
      {
        name: 'Pemakaian Bulanan',
        data: dataVals as number[],
      },
    ]
    dataProcessed.value = true
  }

  watch(() => [props.parentLoading, props.monthlyUsageData, props.parentError], updateData, { deep: true, immediate: true })

  watchDebounced(
    [() => smAndDown.value, () => mobile.value],
    () => { chartRef.value?.updateOptions(options.value, false, true, true) },
    { debounce: 150, maxWait: 500 },
  )

  onMounted(() => { nextTick(() => (isReady.value = true)) })
  onUnmounted(() => { chartRef.value?.destroy() })

  return {
    chartContainerRef,
    chartRef,
    isReady,
    failed,
    devMessage,
    chartKey,
    dataProcessed,
    options,
    series,
    chartHeight,
    heightPx,
    primary,
    errorColor,
    VueApexCharts,
    retry: () => { failed.value = false; isReady.value = false; nextTick(updateData) },
    refreshParent: () => emit('refresh'),
  }
}
