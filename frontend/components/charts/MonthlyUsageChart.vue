<script setup lang="ts">
import type { ApexOptions } from 'apexcharts'
import type { MonthlyUsageData, MonthlyUsageResponse } from '~/types/user' // Asumsikan path ini benar
import { computed, defineAsyncComponent, h, onBeforeUnmount, ref, nextTick as vueNextTick, watch } from 'vue'
import { useDisplay, useTheme } from 'vuetify'

// Props dari parent komponen
const props = defineProps<{
  monthlyData: MonthlyUsageResponse | null
  parentLoading: boolean
  parentError: any | null
  dashboardRenderKey: number
}>()

// Placeholder for Sentry/error tracking integration
// In a real app, this would be initialized by the Sentry SDK
// The _context parameter is intentionally unused in this placeholder.
function captureException(err: Error, _context?: any) {
  // In a real application, this would send the error to Sentry or a similar service.
  // For this example, we'll use the err object by logging its message.
  console.warn(`[CaptureException Placeholder] Error reported: ${err.message}`)
  // In a production environment, the actual Sentry.captureException(err) would be called.
}

const chartComponentName = 'MonthlyChartRefinedOptimized'

// Helper untuk konversi hex ke rgb (digunakan oleh contoh Vuexy)
function hexToRgb(hex: string): string | null {
  if (typeof hex !== 'string' || hex.length === 0)
    return null
  const sanitizedHex = hex.startsWith('#') ? hex.slice(1) : hex
  if (!/^(?:[a-f\d]{3}){1,2}$/i.test(sanitizedHex))
    return null
  let fullHex = sanitizedHex
  if (sanitizedHex.length === 3) {
    fullHex = sanitizedHex.split('').map(char => char + char).join('')
  }
  const result = /^([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(fullHex)
  return result !== null
    ? `${Number.parseInt(result[1], 16)}, ${Number.parseInt(result[2], 16)}, ${Number.parseInt(result[3], 16)}`
    : null
}

// Tema Vuetify dan variabel warna
const vuetifyTheme = useTheme()
const { mobile } = useDisplay() // Integrasi useDisplay untuk responsif dinamis

const currentThemeColors = computed(() => vuetifyTheme.current.value.colors)
const currentThemeVariables = computed(() => vuetifyTheme.current.value.variables)

const chartPrimaryColor = computed(() => currentThemeColors.value.primary ?? '#A672FF')
const legendColor = computed(() => {
  const onBackgroundRgb = hexToRgb(currentThemeColors.value['on-background'] ?? (vuetifyTheme.current.value.dark ? '#FFFFFF' : '#000000'))
  const opacity = currentThemeVariables.value['high-emphasis-opacity'] ?? 0.87
  return onBackgroundRgb !== null ? `rgba(${onBackgroundRgb},${opacity})` : (vuetifyTheme.current.value.dark ? 'rgba(255,255,255,0.87)' : 'rgba(0,0,0,0.87)')
})
const themeBorderColor = computed(() => {
  const borderColorVar = currentThemeVariables.value['border-color']
  const borderOpacity = currentThemeVariables.value['border-opacity'] ?? 0.12
  if (borderColorVar != null && typeof borderColorVar === 'string' && borderColorVar.length > 0) {
    const rgb = hexToRgb(borderColorVar)
    if (rgb !== null)
      return `rgba(${rgb},${borderOpacity})`
  }
  const onSurfaceRgbVal = hexToRgb(currentThemeColors.value['on-surface'] ?? (vuetifyTheme.current.value.dark ? '#FFFFFF' : '#000000'))
  return onSurfaceRgbVal !== null ? `rgba(${onSurfaceRgbVal},${borderOpacity})` : 'rgba(0,0,0,0.12)'
})
const themeLabelColor = computed(() => {
  const onSurfaceRgbVal = hexToRgb(currentThemeColors.value['on-surface'] ?? (vuetifyTheme.current.value.dark ? '#FFFFFF' : '#000000'))
  const opacity = currentThemeVariables.value['disabled-opacity'] ?? 0.38
  return onSurfaceRgbVal !== null ? `rgba(${onSurfaceRgbVal},${opacity})` : (vuetifyTheme.current.value.dark ? 'rgba(255,255,255,0.38)' : 'rgba(0,0,0,0.38)')
})
const errorDisplayColor = computed(() => currentThemeColors.value.error ?? '#FF5252')

// Fungsi format kuota teroptimasi menggunakan Intl.NumberFormat
function formatQuotaForDisplay(value: number, useGbScale: boolean, forDataLabel = false): string {
  if (forDataLabel && Math.abs(value) < 0.1) { // Sembunyikan label data jika nilainya sangat kecil (misal < 0.1 GB atau < 0.1 MB)
    return ''
  }

  try {
    const formatter = new Intl.NumberFormat('id-ID', {
      maximumFractionDigits: useGbScale ? 1 : 0,
      style: 'unit',
      unit: useGbScale ? 'gigabyte' : 'megabyte',
      unitDisplay: 'narrow', // Menggunakan 'narrow' untuk singkatan unit (GB/MB)
    })
    return formatter.format(value)
  }
  catch (e) {
    // Fallback manual jika Intl.NumberFormat gagal (misalnya, lingkungan tidak mendukung)
    console.warn(`${chartComponentName}: Intl.NumberFormat failed for quota display, using fallback. Error: ${(e as Error).message}`)
    return useGbScale ? `${Number(value).toFixed(1)} GB` : `${Math.round(Number(value))} MB`
  }
}

// Fungsi helper untuk opsi chart yang direfaktor dengan responsif dinamis
function getRefactoredMonthlyOptions(
  noDataMessage: string = 'Memuat...',
  isDarkTheme: boolean,
  _chartPrimaryColor: string,
  _themeBorderColor: string,
  _themeLabelColor: string,
  _legendColor: string,
): ApexOptions {
  const responsiveOptions: ApexOptions['responsive'] = []

  if (mobile.value === false) { // Desktop/Tablet
    responsiveOptions.push(
      { breakpoint: 1441, options: { plotOptions: { bar: { columnWidth: '41%' } } } },
      { breakpoint: 960, options: { plotOptions: { bar: { columnWidth: '45%' } } } },
    )
  }
  else { // Mobile
    responsiveOptions.push(
      {
        breakpoint: 599, // sm (mobile)
        options: {
          plotOptions: { bar: { columnWidth: '55%' } },
          yaxis: { labels: { show: false } },
          grid: { padding: { right: 0, left: -15 } },
          dataLabels: { style: { fontSize: '10px' } },
        },
      },
      {
        breakpoint: 420, // xs (sangat kecil)
        options: {
          plotOptions: { bar: { columnWidth: '65%' } },
          dataLabels: { style: { fontSize: '9px' }, offsetY: -15 },
        },
      },
    )
  }

  return {
    chart: {
      id: 'monthly-usage-chart-refactored-optimized',
      parentHeightOffset: 0,
      type: 'bar',
      height: 310,
      toolbar: { show: false },
      animations: { enabled: true, easing: 'easeinout', speed: 600, dynamicAnimation: { enabled: true, speed: 350 } },
    },
    plotOptions: {
      bar: {
        columnWidth: '32%', // Default column width, akan di-override oleh responsive options
        borderRadiusApplication: 'end',
        borderRadius: 4,
        distributed: false, // Set ke false jika hanya satu warna utama
        dataLabels: { position: 'top' },
        states: { hover: { filter: { type: 'none' } } }, // Menghilangkan efek hover default pada bar
      },
    },
    colors: [_chartPrimaryColor],
    dataLabels: {
      enabled: true,
      formatter: (val: number, { seriesIndex, w }) => {
        const seriesInfo = w.globals.initialSeries[seriesIndex]
        const useGb = seriesInfo?.meta?.useGbScale ?? false
        return formatQuotaForDisplay(val, useGb, true) // true untuk forDataLabel
      },
      offsetY: -20,
      style: {
        fontSize: '12px',
        colors: [_legendColor],
        fontWeight: '600',
        fontFamily: 'Public Sans, sans-serif',
      },
    },
    grid: {
      show: false, // Grid utama disembunyikan
      padding: { top: 0, bottom: 0, left: -10, right: -10 }, // Padding disesuaikan
    },
    legend: { show: false },
    tooltip: {
      enabled: true,
      theme: isDarkTheme ? 'dark' : 'light',
      style: { fontSize: '12px', fontFamily: 'Public Sans, sans-serif' },
      marker: { show: false }, // Sembunyikan marker default di tooltip
      // Custom tooltip akan dihandle di watch, ini adalah fallback jika custom tidak terdefinisi
    },
    xaxis: {
      categories: [], // Akan diisi dari data
      axisBorder: { show: true, color: _themeBorderColor },
      axisTicks: { show: false },
      labels: {
        formatter: (value: string) => (value ? value.substring(0, 3) : ''), // Format label X-axis (misal: Jan, Feb)
        style: { colors: _themeLabelColor, fontSize: '13px', fontFamily: 'Public Sans, sans-serif' },
      },
    },
    yaxis: {
      min: 0,
      title: { text: undefined }, // Judul sumbu Y dihilangkan
      labels: {
        offsetX: -15,
        formatter: (val: number, opts?: any) => {
          // Mengambil useGbScale dari metadata series jika tersedia
          const useGb = Boolean(opts?.w?.globals?.series?.[0]?.meta?.useGbScale)
          return formatQuotaForDisplay(val, useGb)
        },
        style: { fontSize: '13px', colors: _themeLabelColor, fontFamily: 'Public Sans, sans-serif' },
      },
      axisBorder: { show: false }, // Sembunyikan garis sumbu Y
      axisTicks: { show: true, color: _themeBorderColor }, // Tampilkan ticks sumbu Y
    },
    noData: {
      text: noDataMessage,
      align: 'center',
      verticalAlign: 'middle',
      offsetX: 0,
      offsetY: -10,
      style: { color: _themeLabelColor, fontSize: '14px', fontFamily: 'Public Sans, sans-serif' },
    },
    responsive: responsiveOptions, // Opsi responsif dinamis
  }
}

const VueApexCharts = defineAsyncComponent(() =>
  import('vue3-apexcharts').then(mod => mod.default).catch((err) => {
    // console.error(`${chartComponentName}: Gagal memuat VueApexCharts`, err);
    handleChartError(err as Error, 'Gagal memuat komponen VueApexCharts')
    return { render: () => h('div', { class: 'text-caption text-error text-center pa-4' }, 'Komponen Chart Gagal Dimuat.') }
  }),
)

const chartContainerRef = ref<any>(null)
const isChartReadyToRender = ref(false)
const chartContainerFailedOverall = ref(false)
const chartRef = ref<any>(null)
const dataProcessed = ref(false)
const hasValidProcessedData = ref(false)
const monthlyChartKey = ref(0)
const chartNoDataTextFromLogic = ref('Belum ada riwayat penggunaan.')
const devErrorMessage = ref<string | null>(null)

const showLoadingOverlay = computed(() => {
  return props.parentLoading || (!isChartReadyToRender.value && !chartContainerFailedOverall.value && props.parentError == null && !dataProcessed.value)
})

const totalMonthlyUsageFormatted = computed(() => {
  if (props.monthlyData?.success === true && Array.isArray(props.monthlyData.monthly_data) && hasValidProcessedData.value) {
    const totalMb = props.monthlyData.monthly_data.reduce((sum, item) => sum + (item.usage_mb ?? 0), 0)
    // Menggunakan useGigaByteScale dari data yang sudah diproses untuk konsistensi
    const { useGigaByteScale } = processMonthlyDataForChart(props.monthlyData.monthly_data) // Re-proses untuk mendapatkan skala yang konsisten
    if (useGigaByteScale)
      return formatQuotaForDisplay(totalMb / 1024, true)
    return formatQuotaForDisplay(totalMb, false)
  }
  return formatQuotaForDisplay(0, false) // Default jika tidak ada data
})

function processMonthlyDataForChart(data: MonthlyUsageData[] | undefined | null) {
  const result = { categories: [] as string[], seriesData: [] as number[], yAxisTitle: 'Penggunaan (MB)', displayMax: 10, useGigaByteScale: false, allZero: true, isValid: false, originalMonthYear: [] as string[] }
  if (!Array.isArray(data) || data.length === 0) {
    return result
  }

  // PERBAIKAN FORMAT TANGGAL: Pastikan regex konsisten untuk sorting
  const originalMonthlyData = [...data].sort((a, b) => {
    const dateA = new Date(a.month_year.replace(/(\d{4})-(\d{2})/, '$1/$2/01'))
    const dateB = new Date(b.month_year.replace(/(\d{4})-(\d{2})/, '$1/$2/01')) // Regex disamakan
    return dateA.getTime() - dateB.getTime()
  })

  const processedApiSeriesDataMb = originalMonthlyData.map(item => item.usage_mb ?? 0)
  result.originalMonthYear = originalMonthlyData.map(d => d.month_year)

  const processedCategories = originalMonthlyData.map((d) => {
    if (d.month_year != null && typeof d.month_year === 'string' && d.month_year.includes('-')) {
      const parts = d.month_year.split('-')
      if (parts.length === 2) {
        const yearNum = Number.parseInt(parts[0])
        const monthNum = Number.parseInt(parts[1])
        if (!Number.isNaN(yearNum) && !Number.isNaN(monthNum) && monthNum >= 1 && monthNum <= 12 && yearNum > 1900 && yearNum < 3000) {
          const date = new Date(yearNum, monthNum - 1)
          if (!Number.isNaN(date.getTime())) {
            return date.toLocaleString('id-ID', { month: 'short' })
          }
        }
      }
    }
    return 'N/A'
  })

  const validDataPoints = processedCategories.map((cat, index) => ({ category: cat, value: processedApiSeriesDataMb[index], originalMY: result.originalMonthYear[index] })).filter(point => point.category !== 'N/A')
  result.categories = validDataPoints.map(point => point.category)
  result.originalMonthYear = validDataPoints.map(point => point.originalMY)
  const finalApiSeriesDataMb = validDataPoints.map(point => point.value)

  result.isValid = finalApiSeriesDataMb.length > 0 && result.categories.length > 0 && finalApiSeriesDataMb.length === result.categories.length
  result.allZero = result.isValid === false || finalApiSeriesDataMb.every(item => item === 0)

  if (result.isValid) {
    const maxUsageMb = Math.max(...finalApiSeriesDataMb, 0)
    const maxGb = maxUsageMb / 1024
    result.useGigaByteScale = maxGb >= 1.0

    // Kalkulasi awal displayMax berdasarkan skala
    if (result.useGigaByteScale) {
      result.displayMax = Math.ceil(maxGb * 1.15) // Headroom
      result.displayMax = result.displayMax < 0.1 ? 0.1 : result.displayMax // Min 0.1 GB
      result.yAxisTitle = 'Penggunaan (GB)'
      result.seriesData = finalApiSeriesDataMb.map(mb => Number.parseFloat((mb / 1024).toFixed(1)))
    }
    else {
      result.displayMax = Math.ceil(maxUsageMb * 1.15) // Headroom
      // Kalkulasi rounding factor awal (sebelum optimasi) untuk MB scale jika diperlukan
      const initialMbRounding = result.displayMax <= 10 ? 1 : 10 ** Math.floor(Math.log10(result.displayMax))
      result.displayMax = Math.ceil(result.displayMax / initialMbRounding) * initialMbRounding
      result.displayMax = Math.max(10, result.displayMax) // Min 10 MB
      result.yAxisTitle = 'Penggunaan (MB)'
      result.seriesData = finalApiSeriesDataMb.map(mb => Number.parseFloat(mb.toFixed(0)))
    }

    // OPTIMASI: Hitung rounding factor secara matematis untuk menyempurnakan displayMax
    const valueForFactorLog = result.useGigaByteScale ? Math.max(0.01, result.displayMax) : Math.max(1, result.displayMax)
    const roundingFactor = 10 ** Math.max(0, Math.floor(Math.log10(valueForFactorLog)) - 1)
    result.displayMax = Math.ceil(result.displayMax / roundingFactor) * roundingFactor

    // Penyesuaian akhir displayMax setelah optimasi rounding factor
    if (result.useGigaByteScale) {
      result.displayMax = Math.max(0.1, result.displayMax) // Pastikan minimal 0.1 GB
      // Penyesuaian tambahan untuk skala GB agar pembagiannya bagus
      if (result.displayMax > 1 && result.displayMax <= 10) {
        result.displayMax = Math.ceil(result.displayMax)
      }
      else if (result.displayMax > 10) {
        result.displayMax = Math.ceil(result.displayMax / 2.5) * 2.5
      }
      else { // <= 1 GB
        result.displayMax = Math.max(0.1, Math.ceil(result.displayMax * 10) / 10) // Bulatkan ke 0.1 terdekat
      }
      // Handle jika displayMax menjadi 0 padahal ada data
      if (result.displayMax < 0.1 && maxGb > 0)
        result.displayMax = Math.max(0.1, Math.ceil(maxGb * 10) / 10)
      else if (result.displayMax < 0.1)
        result.displayMax = 0.1
    }
    else { // MB Scale
      result.displayMax = Math.max(10, result.displayMax) // Pastikan minimal 10 MB
    }
  }
  else {
    result.yAxisTitle = 'Penggunaan Bulanan'
    result.displayMax = 10
    result.useGigaByteScale = false
    result.seriesData = []
    result.categories = []
    result.originalMonthYear = []
  }
  return result
}

const monthlyUsageChartOptions = ref<ApexOptions>(getRefactoredMonthlyOptions(
  chartNoDataTextFromLogic.value,
  vuetifyTheme.current.value.dark,
  chartPrimaryColor.value,
  themeBorderColor.value,
  themeLabelColor.value,
  legendColor.value,
))
const monthlyUsageChartSeries = ref<{ name: string, data: number[], meta?: { useGbScale: boolean, originalMonthYears: string[] } }[]>([{ name: 'Penggunaan Bulanan', data: [] }])

const observer = ref<ResizeObserver | null>(null)
let fallbackTimeoutId: ReturnType<typeof setTimeout> | null = null

// ERROR HANDLING TEROPTIMASI
function handleChartError(err: Error, contextMessage: string = 'Chart error') {
  // console.error(`[${chartComponentName}] ${contextMessage}:`, err); // Log dasar tetap ada

  if (import.meta.env.DEV) {
    // console.error(`[${chartComponentName}] Dev Context - ${contextMessage}:`, err);
    devErrorMessage.value = `[DEV] ${contextMessage}: ${err.message}${err.stack ? `\nStack: ${err.stack}` : ''}`
  }
  else {
    captureException(err, { extra: { context: chartComponentName, message: contextMessage } }) // Integrasi dengan error tracking
    devErrorMessage.value = 'Terjadi kesalahan teknis saat memuat chart.' // Pesan generik untuk production
  }

  chartContainerFailedOverall.value = true
  isChartReadyToRender.value = false
  monthlyChartKey.value++ // Re-render chart component
}

async function attemptSetReady() {
  devErrorMessage.value = null // Reset pesan error dev setiap percobaan
  if (chartContainerFailedOverall.value === true && props.parentLoading === false) {
    return // Jika sudah gagal secara keseluruhan dan tidak loading, jangan coba lagi
  }

  await vueNextTick()
  const rawContainer = chartContainerRef.value
  const containerElement = (rawContainer?.$el ?? rawContainer) as Element | null

  if (containerElement === null) {
    handleChartError(new Error('Referensi kontainer chart (VCardText) tidak tersedia.'), 'Inisiasi ResizeObserver')
    return
  }
  if (!(containerElement instanceof Element)) {
    handleChartError(new Error(`Referensi kontainer chart yang didapat bukan Element DOM yang valid. Tipe: ${typeof containerElement}`), 'Validasi DOM ResizeObserver')
    return
  }

  if (observer.value !== null) {
    observer.value.disconnect()
    observer.value = null
  }
  if (fallbackTimeoutId !== null) {
    clearTimeout(fallbackTimeoutId)
    fallbackTimeoutId = null
  }

  isChartReadyToRender.value = false // Set false dulu sebelum observer memastikan
  try {
    observer.value = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 50 && height > 50) { // Pastikan kontainer memiliki dimensi yang cukup
          if (isChartReadyToRender.value === false) {
            isChartReadyToRender.value = true
            chartContainerFailedOverall.value = false // Reset status gagal jika berhasil
            monthlyChartKey.value++ // Trigger re-render chart jika perlu
          }
          observer.value?.unobserve(entry.target) // Hentikan observasi setelah berhasil
          observer.value?.disconnect()
          observer.value = null
          if (fallbackTimeoutId !== null) {
            clearTimeout(fallbackTimeoutId)
            fallbackTimeoutId = null
          }
          return // Keluar setelah berhasil
        }
      }
    })
    observer.value.observe(containerElement)

    // Fallback jika ResizeObserver tidak trigger dalam waktu tertentu
    fallbackTimeoutId = setTimeout(() => {
      if (isChartReadyToRender.value === false) {
        handleChartError(new Error('Timeout ResizeObserver (3s) menunggu kontainer chart siap.'), 'Fallback Timeout ResizeObserver')
        if (observer.value !== null && containerElement instanceof Element)
          observer.value.unobserve(containerElement)
        if (observer.value !== null) {
          observer.value.disconnect()
          observer.value = null
        }
      }
    }, 3000)
  }
  catch (err) {
    handleChartError(err as Error, 'Eksepsi saat inisiasi ResizeObserver')
  }
}

function retryChartInit() {
  chartContainerFailedOverall.value = false
  isChartReadyToRender.value = false // Set false untuk memulai ulang proses pengecekan
  devErrorMessage.value = null
  monthlyChartKey.value++ // Untuk me-reset komponen chart jika perlu
  vueNextTick(() => {
    attemptSetReady() // Coba lagi inisiasi
  })
}

onBeforeUnmount(() => {
  if (fallbackTimeoutId !== null)
    clearTimeout(fallbackTimeoutId)
  if (observer.value !== null) {
    observer.value.disconnect()
    observer.value = null
  }
})

watch(() => props.dashboardRenderKey, async (newKey, oldKey) => {
  const isInitialCallOrChange = oldKey === undefined || newKey !== oldKey
  if (isInitialCallOrChange) {
    await vueNextTick()
    chartContainerFailedOverall.value = false // Reset status gagal
    isChartReadyToRender.value = false // Set false untuk memulai ulang proses pengecekan
    attemptSetReady()
  }
}, { immediate: true })

watch(
  () => [
    props.monthlyData,
    props.parentLoading,
    props.parentError,
    vuetifyTheme.current.value.dark,
    isChartReadyToRender.value,
    chartContainerFailedOverall.value, // Tambahkan ini agar watch bereaksi pada kegagalan kontainer
    chartPrimaryColor.value, // Warna juga bisa berubah
    themeBorderColor.value,
    themeLabelColor.value,
    legendColor.value,
    mobile.value, // Tambahkan mobile.value agar opsi chart di-update saat viewport berubah
  ],
  (newValues) => {
    const [
      newData,
      newParentLoading,
      newParentError,
      isDark,
      chartReady,
      containerFailed, // Ambil nilai dari watcher
      _chartPrimaryColor,
      _themeBorderColor,
      _themeLabelColor,
      _legendColor,
      // isMobile, // Tidak perlu digunakan langsung di sini, getRefactoredMonthlyOptions sudah memakainya
    ] = newValues as [MonthlyUsageResponse | null, boolean, any | null, boolean, boolean, boolean, string, string, string, string, boolean]

    dataProcessed.value = !newParentLoading // Data dianggap sudah diproses jika tidak loading lagi
    let currentNoDataText = 'Belum ada riwayat penggunaan.'
    let processedDataResult: ReturnType<typeof processMonthlyDataForChart>

    if (containerFailed) {
      currentNoDataText = 'Area chart tidak dapat disiapkan.'
      hasValidProcessedData.value = false
      processedDataResult = processMonthlyDataForChart(null) // Set default untuk opsi chart
    }
    else if (newParentLoading) {
      currentNoDataText = 'Memuat data chart...'
      hasValidProcessedData.value = false
      processedDataResult = processMonthlyDataForChart(null)
    }
    else if (!chartReady) {
      currentNoDataText = 'Menyiapkan area chart...'
      hasValidProcessedData.value = false
      processedDataResult = processMonthlyDataForChart(null)
    }
    else if (newParentError != null) {
      currentNoDataText = 'Gagal memuat data riwayat bulanan.'
      hasValidProcessedData.value = false
      processedDataResult = processMonthlyDataForChart(null)
    }
    else if (newData?.success === true && Array.isArray(newData.monthly_data)) {
      processedDataResult = processMonthlyDataForChart(newData.monthly_data)
      hasValidProcessedData.value = processedDataResult.isValid && !processedDataResult.allZero
      if (processedDataResult.isValid === false)
        currentNoDataText = 'Format data tidak sesuai atau data tidak valid.'
      else if (processedDataResult.allZero)
        currentNoDataText = 'Belum ada riwayat penggunaan bulan ini.'
      else currentNoDataText = '' // Tidak ada teks jika data valid dan tidak semua nol
    }
    else { // Termasuk jika newData.success false atau monthly_data bukan array
      currentNoDataText = 'Data riwayat bulanan tidak tersedia.'
      hasValidProcessedData.value = false
      processedDataResult = processMonthlyDataForChart(null)
    }

    chartNoDataTextFromLogic.value = currentNoDataText

    monthlyUsageChartSeries.value = [{
      name: processedDataResult?.yAxisTitle ?? 'Penggunaan Bulanan', // Nama series dari hasil proses
      data: processedDataResult?.seriesData ?? [],
      meta: {
        useGbScale: processedDataResult?.useGigaByteScale ?? false,
        originalMonthYears: processedDataResult?.originalMonthYear ?? [],
      },
    }]

    const baseOpts = getRefactoredMonthlyOptions(currentNoDataText, isDark, _chartPrimaryColor, _themeBorderColor, _themeLabelColor, _legendColor)
    monthlyUsageChartOptions.value = {
      ...baseOpts,
      colors: [_chartPrimaryColor], // Pastikan warna utama diterapkan
      xaxis: {
        ...baseOpts.xaxis,
        categories: processedDataResult?.categories ?? [],
        labels: { ...baseOpts.xaxis?.labels, style: { ...baseOpts.xaxis?.labels?.style, colors: _themeLabelColor } },
      },
      yaxis: {
        ...baseOpts.yaxis,
        max: processedDataResult?.displayMax ?? 10,
        title: { text: undefined }, // Eksplisit hilangkan judul Y-axis
        labels: {
          ...baseOpts.yaxis?.labels,
          style: { ...baseOpts.yaxis?.labels?.style, colors: _themeLabelColor },
          formatter: (value: number) => formatQuotaForDisplay(value, processedDataResult?.useGigaByteScale ?? false),
        },
        axisBorder: { ...baseOpts.yaxis?.axisBorder, color: _themeBorderColor },
        axisTicks: { ...baseOpts.yaxis?.axisTicks, color: _themeBorderColor },
      },
      grid: { ...baseOpts.grid, borderColor: _themeBorderColor }, // Pastikan borderColor grid juga diupdate
      tooltip: {
        ...baseOpts.tooltip,
        theme: isDark ? 'dark' : 'light',
        custom({ series, seriesIndex, dataPointIndex, w }) {
          const originalMY = w.globals.initialSeries[seriesIndex]?.meta?.originalMonthYears?.[dataPointIndex] ?? ''
          let displayCategory = w.globals.labels[dataPointIndex] ?? originalMY // Fallback ke label jika originalMY kosong

          if (originalMY.length > 0 && originalMY.includes('-')) {
            const parts = originalMY.split('-')
            if (parts.length === 2) {
              const yearNum = Number.parseInt(parts[0])
              const monthNum = Number.parseInt(parts[1])
              if (!Number.isNaN(yearNum) && !Number.isNaN(monthNum)) {
                const date = new Date(yearNum, monthNum - 1)
                if (!Number.isNaN(date.getTime())) {
                  displayCategory = date.toLocaleString('id-ID', { month: 'long', year: 'numeric' })
                }
              }
            }
          }

          const value = series[seriesIndex][dataPointIndex]
          const useGb = w.globals.initialSeries[seriesIndex]?.meta?.useGbScale ?? false
          const formattedValue = formatQuotaForDisplay(value, useGb) // Tidak forDataLabel

          return `<div class="apexcharts-tooltip-custom vuexy-tooltip custom-tooltip">
                    <span>${displayCategory}: ${formattedValue}</span>
                  </div>`
        },
      },
      dataLabels: {
        ...baseOpts.dataLabels,
        formatter: (val: number, opts) => {
          const useGb = opts.w.config.series[opts.seriesIndex]?.meta?.useGbScale ?? false
          return formatQuotaForDisplay(val, useGb, true) // true untuk forDataLabel
        },
        style: { ...baseOpts.dataLabels?.style, colors: [_legendColor] },
      },
      noData: {
        ...baseOpts.noData,
        text: currentNoDataText, // Teks noData dari logika
        style: { ...baseOpts.noData?.style, color: containerFailed || newParentError != null ? errorDisplayColor.value : _themeLabelColor },
      },
    }

    // Update chart hanya jika siap, tidak loading, dan tidak gagal
    if (chartRef.value != null && chartReady && !newParentLoading && !containerFailed) {
      vueNextTick(() => { // Pastikan DOM sudah siap untuk update
        if (typeof chartRef.value?.updateOptions === 'function')
          chartRef.value.updateOptions(monthlyUsageChartOptions.value, false, true, true)
        if (typeof chartRef.value?.updateSeries === 'function') // Update series juga jika datanya berubah
          chartRef.value.updateSeries(monthlyUsageChartSeries.value, true) // true untuk animasi
      })
    }
  },
  { deep: true, immediate: true },
)
</script>

<template>
  <div class="chart-error-boundary">
    <template v-if="!chartContainerFailedOverall">
      <VCard class="vuexy-card" min-height="460" height="100%" :class="{ 'vuexy-card-shadow': vuetifyTheme.current.value.dark }">
        <VCardItem class="vuexy-card-header pt-5 pb-2">
          <VCardTitle class="text-h6 vuexy-card-title mb-1">
            <VIcon icon="tabler-chart-bar" class="me-2" />Penggunaan Kuota Bulanan
          </VCardTitle>
          <div
            v-if="!parentLoading && parentError == null && hasValidProcessedData"
            class="text-h5 font-weight-semibold"
          >
            {{ totalMonthlyUsageFormatted }}
          </div>
          <div v-else-if="!parentLoading && parentError == null && !hasValidProcessedData && dataProcessed" class="text-body-2 text-medium-emphasis">
            {{ chartNoDataTextFromLogic || 'Belum ada riwayat penggunaan.' }}
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

          <ClientOnly class="flex-grow-1">
            <VueApexCharts
              v-if="isChartReadyToRender && !chartContainerFailedOverall && !showLoadingOverlay && hasValidProcessedData"
              ref="chartRef"
              :key="monthlyChartKey"
              :options="monthlyUsageChartOptions"
              :series="monthlyUsageChartSeries"
              type="bar"
              height="310"
              class="mt-2"
            />
            <div v-else-if="!showLoadingOverlay" class="chart-fallback-container" :style="{ height: '310px' }">
              <template v-if="isChartReadyToRender && !parentLoading && (parentError != null || !hasValidProcessedData)">
                <VIcon
                  size="40"
                  :color="parentError != null ? errorDisplayColor : 'grey-lighten-1'"
                  class="mb-2"
                >
                  {{ parentError != null ? 'tabler-alert-triangle' : 'tabler-chart-bar-off' }}
                </VIcon>
                <p :class="parentError != null ? 'text-error' : 'text-medium-emphasis'" class="text-caption">
                  {{ chartNoDataTextFromLogic || (parentError != null ? 'Gagal memuat data chart.' : 'Tidak ada data untuk ditampilkan.') }}
                </p>
              </template>
              <template v-else-if="!isChartReadyToRender && !parentLoading && parentError == null">
                <VIcon size="40" color="grey-lighten-1" class="mb-2">
                  tabler-loader-2
                </VIcon>
                <p class="text-caption text-medium-emphasis">
                  {{ chartNoDataTextFromLogic || 'Menyiapkan area chart...' }}
                </p>
              </template>
            </div>

            <template #fallback>
              <div class="chart-fallback-container" :style="{ height: '310px' }">
                <VProgressCircular indeterminate size="40" color="primary" />
                <p class="text-caption mt-2 text-medium-emphasis">
                  Memuat komponen chart...
                </p>
              </div>
            </template>
          </ClientOnly>

          <div class="text-caption text-medium-emphasis mt-3 px-1 halus">
            Penggunaan kuota dilacak dalam waktu UTC +8, yang mungkin berbeda dengan waktu perangkat Anda.
            Sinkronisasi akan dilakukan berkala.
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
          Terjadi masalah saat mencoba menyiapkan atau menampilkan chart. Silakan coba lagi.
        </p>
        <VBtn variant="tonal" :color="errorDisplayColor" class="mt-1" size="small" @click="retryChartInit">
          <VIcon start icon="tabler-refresh" /> Coba Lagi Inisiasi
        </VBtn>
        <div v-if="devErrorMessage != null" class="dev-error-overlay-message mt-3">
          <strong>Pesan Error (Mode Pengembangan):</strong><br>{{ devErrorMessage }}
        </div>
      </div>
    </VAlert>
  </div>
</template>

<style scoped>
/* Vuexy Card Styling */
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
  border-radius: 0.75rem 0.75rem 0 0; /* Pastikan radius sesuai */
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
  z-index: 1; /* Untuk memastikan overlay loading di atas chart */
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

/* Vuexy Loading Overlay */
.vuexy-loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(var(--v-theme-surface), 0.85); /* Opacity disesuaikan */
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: inherit; /* Mengikuti radius parent card */
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

.halus { position: relative; top: 0px; margin: 0.5rem 1rem 2rem 1rem; line-height: 1.4; text-align: center; font-size: 0.8125rem; } /* Penyesuaian margin bottom */
.chartbulan { padding: 0rem 0.5rem; margin-top: 0rem; display: flex; flex-direction: column; flex-grow: 1; }
.vue-apexcharts { max-width: 100%; direction: ltr; padding-top: 20px; } /* Arah LTR untuk chart */
.chart-fallback-container { display: flex; flex-direction: column; justify-content: center; align-items: center; width: 100%; flex-grow: 1; padding: 1rem; text-align: center; }

@media (max-width: 599.98px) {
  .halus { margin-top: 0.5rem; font-size: 0.75rem; margin-bottom: 0.75rem; }
  .v-card-item .v-card-title { font-size: 1rem; }
  .v-card-item .text-h5 { font-size: 1.25rem !important; }
  .chartbulan { padding: 0 0.25rem; }
}

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
  text-align: left; /* Pesan error dev rata kiri */
  width: 100%; /* Lebar penuh dalam konteksnya */
  box-sizing: border-box;
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

.vuexy-alert {
  border-radius: 0.75rem; /* Sesuai standar Vuexy */
}
.chart-error-fallback.vuexy-card { /* Styling untuk fallback error utama */
    padding: 1.5rem;
    text-align: center;
    background: rgba(var(--v-theme-error), 0.05); /* Latar error yang lebih halus */
    border: 1px solid rgba(var(--v-theme-error), 0.2);
    color: rgba(var(--v-theme-on-error-container)); /* Kontras teks yang baik */
}
.chart-error-fallback .v-icon { position: relative; top: 0; color: rgba(var(--v-theme-error)) !important; }
.chart-error-fallback .text-h6 { color: rgba(var(--v-theme-error)); font-weight: 600; }
.chart-error-fallback .text-body-2 { color: rgba(var(--v-theme-on-error-container), 0.8);}
</style>

<style>
  /* Style global untuk error boundary (jika belum ada di file global) */
.chart-error-boundary {
  position: relative;
  height: 100%;
  width: 100%;
  display: flex; /* Memastikan boundary mengisi ruang */
  flex-direction: column;
}

/* Styling default untuk tooltip bawaan ApexCharts (jika custom tidak digunakan) */
/* Ini penting untuk konsistensi jika custom tooltip gagal atau tidak diimplementasikan */
:root {
  --v-shadow-key-umbra-color: var(--v-theme-shadow-key-umbra-opacity, var(--v-shadow-key-umbra-color, initial));
  --v-shadow-key-penumbra-color: var(--v-theme-shadow-key-penumbra-opacity, var(--v-shadow-key-penumbra-color, initial));
  --v-shadow-key-ambient-color: var(--v-theme-shadow-key-ambient-opacity, var(--v-shadow-key-ambient-color, initial));
}

.apexcharts-tooltip {
  background: rgb(var(--v-theme-surface-light, var(--v-theme-surface))) !important;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important;
  box-shadow: 0px 4px 8px -4px rgba(var(--v-shadow-key-umbra-color), 0.2), 0px 8px 16px -4px rgba(var(--v-shadow-key-penumbra-color), 0.14), 0px 6px 6px -6px rgba(var(--v-shadow-key-ambient-color), 0.12) !important;
  border-radius: 6px !important;
  padding: 0.5rem 0.75rem !important;
  transition: opacity 0.2s ease-in-out;
}

.apexcharts-tooltip-title {
  background: transparent !important;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important;
  padding-bottom: 0.3rem !important;
  margin-bottom: 0.3rem !important;
  font-weight: 600;
}

.apexcharts-tooltip-series-group {
  background: transparent !important;
  padding: 0.3rem 0 !important;
}

.apexcharts-tooltip-text-y-label,
.apexcharts-tooltip-text-y-value {
  display: inline-block; /* Memastikan label dan value konsisten */
}

.apexcharts-tooltip-marker {
  margin-right: 5px;
}
</style>