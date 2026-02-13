<script setup lang="ts">
import type { ApexOptions } from 'apexcharts'
import type { WeeklyUsageResponse } from '~/types/user' // Hapus UserQuotaResponse karena tidak diperlukan
import { hexToRgb } from '@layouts/utils'
import { watchDebounced } from '@vueuse/core'
import { computed, defineAsyncComponent, h, ref, unref, nextTick as vueNextTick, watch } from 'vue'
import { useDisplay, useTheme } from 'vuetify'

const props = defineProps<{
  // Tidak lagi memerlukan quotaData untuk chart unlimited
  weeklyUsageData: WeeklyUsageResponse | null
  parentLoading: boolean
  parentError: any | null
  dashboardRenderKey: number
}>()

const emit = defineEmits<{
  refresh: []
}>()

const { smAndDown, mobile } = useDisplay()
const chartComponentName = 'WeeklyUsageChartUnlimited' // Nama komponen diperbarui

const VueApexCharts = defineAsyncComponent(() =>
  import('vue3-apexcharts').then(mod => mod.default).catch((err) => {
    console.warn(`${chartComponentName}: Gagal memuat VueApexCharts. Error: ${err.message}`)
    return { render: () => h('div', { class: 'text-caption text-error text-center pa-4' }, 'Komponen Chart Gagal Dimuat.') }
  }),
)

const chartContainerActualRef = ref<HTMLElement | null>(null)
const isChartReadyToRender = ref(false)
const chartContainerFailedOverall = ref(false)
const vuetifyTheme = useTheme()
const weeklyChartRef = ref<any>(null)
const weeklyDataProcessed = ref(!props.parentLoading)

const chartHeight = computed(() => {
  if (mobile.value)
    return 130
  if (smAndDown.value)
    return 140
  return 161
})
const chartHeightInPx = computed(() => `${chartHeight.value}px`)

const weeklyChartKey = ref(0)
const chartNoDataTextFromLogic = ref('Belum ada penggunaan minggu ini.')
const devErrorMessage = ref<string | null>(null)
const lastParentLoading = ref(props.parentLoading)

let attemptSetReadyRetries = 0
const MAX_ATTEMPT_RETRIES = 10
const RETRY_DELAY_MS = 350

const currentThemeColors = computed(() => vuetifyTheme.current.value.colors ?? {})
const currentThemeVariables = computed(() => vuetifyTheme.current.value.variables ?? {})
const primaryColor = computed(() => currentThemeColors.value.primary ?? (vuetifyTheme.current.value.dark ? '#A672FF' : '#6200EE'))
const errorDisplayColor = computed(() => currentThemeColors.value.error ?? '#FF5252')
const infoDisplayColor = computed(() => currentThemeColors.value.info ?? '#2196F3')

const onSurfaceColor = computed(() => currentThemeColors.value['on-surface'] ?? (vuetifyTheme.current.value.dark ? '#FFFFFF' : '#000000'))
const primaryColorRgb = computed(() => hexToRgb(primaryColor.value))
const onSurfaceColorRgb = computed(() => hexToRgb(onSurfaceColor.value))
const draggedOpacity = computed(() => {
  const opacityValue = currentThemeVariables.value['dragged-opacity']
  return Number.parseFloat(opacityValue?.toString() || (vuetifyTheme.current.value.dark ? '0.3' : '0.4'))
})
const disabledOpacity = computed(() => {
  const opacityValue = currentThemeVariables.value['disabled-opacity']
  return Number.parseFloat(opacityValue?.toString() || (vuetifyTheme.current.value.dark ? '0.5' : '0.38'))
})

const isLoadingInternalProcessing = computed(() => !weeklyDataProcessed.value && !props.parentLoading)
const canInitChart = computed(() => !props.parentLoading && props.parentError == null)
const hasNoWeeklyData = computed(() => {
  const data = props.weeklyUsageData
  if (!data)
    return true

  return Array.isArray(data.weekly_data) ? data.weekly_data.every(d => d === 0) : true
})

const lastWeeklyUsage = computed(() => {
  const data = props.weeklyUsageData?.weekly_data ?? []
  return data.length > 0 ? data[data.length - 1] : null
})

function formatQuota(value: number | null | undefined): string {
  const numericValue = value ?? 0
  if (numericValue >= 1024)
    return `${(numericValue / 1024).toFixed(2)} GB`
  const mbDigits = numericValue % 1 === 0 ? 0 : 2
  return `${numericValue.toFixed(mbDigits)} MB`
}

// Fungsi ini tidak lagi diperlukan karena tidak ada "usage chip" untuk unlimited
// function getUsageChipColor(used: number | null | undefined, purchased: number | null | undefined): string {
//   const numUsed = used ?? 0
//   const numPurchased = purchased ?? 0
//   if (numPurchased <= 0)
//     return 'grey'
//   const percentageUsed = (numUsed / numPurchased) * 100
//   if (percentageUsed >= 80)
//     return 'error'
//   if (percentageUsed >= 50)
//     return 'warning'
//   return 'success'
// }

// Fungsi ini tidak lagi diperlukan karena tidak ada persentase kuota untuk unlimited
// function calculatePercentage(value: number | null | undefined, total: number | null | undefined): number {
//   const numValue = value ?? 0
//   const numTotal = total ?? 0
//   if (numTotal <= 0)
//     return 0
//   const percentage = Math.round((numValue / numTotal) * 100)
//   return Math.max(0, Math.min(100, percentage))
// }

const quotaWeeklyBarSeries = ref([{ name: 'Penggunaan Harian', data: Array.from({ length: 7 }).fill(0) as number[] }])

function formatDayLabel(value: string): string {
  return mobile.value ? value.substring(0, 2) : value.substring(0, 3)
}

const quotaWeeklyBarOptions = computed<ApexOptions>(() => {
  const today = new Date()
  const categories = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(today)
    date.setDate(today.getDate() - (6 - i))
    return date.toLocaleDateString('id-ID', { weekday: 'long' })
  })

  const processedSeriesData = quotaWeeklyBarSeries.value[0]?.data ?? Array.from({ length: 7 }).fill(0)
  const allZero = processedSeriesData.every(item => item === 0)

  const primRgbVal = primaryColorRgb.value ?? (vuetifyTheme.current.value.dark ? '166, 114, 255' : '115, 103, 240')
  const inactiveOpVal = draggedOpacity.value
  const activeBarColor = primaryColor.value
  const inactiveBarColor = `rgba(${primRgbVal}, ${inactiveOpVal})`

  const barColors = processedSeriesData.map((value, index) => {
    if (index === processedSeriesData.length - 1 && value > 0 && !allZero) {
      return activeBarColor
    }
    return inactiveBarColor
  })

  const axisLabelColorRgbVal = onSurfaceColorRgb.value ?? (vuetifyTheme.current.value.dark ? '255, 255, 255' : '0, 0, 0')
  const axisLabelColor = `rgba(${axisLabelColorRgbVal}, ${disabledOpacity.value})`

  const noDataDisplayColor = chartContainerFailedOverall.value || props.parentError != null
    ? errorDisplayColor.value
    : (props.parentLoading ? primaryColor.value : `rgba(${axisLabelColorRgbVal}, ${disabledOpacity.value})`)

  return {
    chart: {
      parentHeightOffset: 0,
      type: 'bar',
      height: chartHeight.value,
      toolbar: { show: false },
      animations: { enabled: true, easing: 'easeinout', speed: 500, dynamicAnimation: { enabled: true, speed: 300 } },
    },
    plotOptions: {
      bar: {
        barHeight: '60%',
        columnWidth: smAndDown.value ? '45%' : '38%',
        startingShape: 'rounded',
        endingShape: 'rounded',
        borderRadius: 4,
        distributed: true,
        dataLabels: {
          position: 'top',
        },
        states: {
          hover: {
            filter: {
              type: 'none',
            },
          },
        },
      },
    },
    grid: { show: false, padding: { top: 0, bottom: 0, left: -10, right: -10 } },
    colors: barColors,
    dataLabels: { enabled: false },
    legend: { show: false },
    xaxis: {
      categories,
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: {
        formatter: formatDayLabel,
        style: {
          colors: axisLabelColor,
          fontSize: mobile.value ? '10px' : (smAndDown.value ? '11px' : '13px'),
          fontFamily: 'inherit',
        },
      },
    },
    yaxis: { labels: { show: false }, min: 0 },
    tooltip: {
      enabled: true,
      theme: vuetifyTheme.current.value.dark ? 'dark' : 'light',
      style: {
        fontSize: mobile.value ? '10px' : '12px',
        fontFamily: 'inherit',
      },
      custom({ series, seriesIndex, dataPointIndex, w }) {
        const dayName = w.globals.labels[dataPointIndex] ?? categories[dataPointIndex] ?? ''
        const usageValue = series[seriesIndex][dataPointIndex]
        const usageFormatted = formatQuota(usageValue)
        return `<div class="apexcharts-tooltip-custom vuexy-tooltip custom-tooltip">
                  <span>${dayName}: ${usageFormatted}</span>
                </div>`
      },
    },
    noData: {
      text: chartNoDataTextFromLogic.value,
      align: 'center',
      verticalAlign: 'middle',
      offsetY: 0,
      style: {
        color: noDataDisplayColor,
        fontSize: mobile.value ? '12px' : '14px',
        fontFamily: 'inherit',
      },
    },
  }
})

const observer = ref<ResizeObserver | null>(null)
let fallbackTimeoutId: ReturnType<typeof setTimeout> | null = null

function handleChartError(err: Error, contextMessage: string = 'Error pada chart') {
  const messageStr = `[${chartComponentName}] ${contextMessage}: ${err.message}.`
  const stackStr = `Stack: ${err.stack || 'Tidak tersedia'}`
  console.error(`${messageStr} ${stackStr}`)

  const devMsgPart1 = `[${contextMessage}] ${err.message}`
  const devMsgPart2 = err.stack ? `\nStack: ${err.stack}` : ''
  devErrorMessage.value = `${devMsgPart1}${devMsgPart2}`

  chartContainerFailedOverall.value = true
  isChartReadyToRender.value = false
}

async function attemptSetReady() {
  if (!canInitChart.value) {
    attemptSetReadyRetries = 0
    return
  }
  await vueNextTick()
  const containerEl = unref(chartContainerActualRef)

  if (containerEl === null || !containerEl.isConnected || containerEl.offsetWidth === 0 || containerEl.offsetHeight === 0) {
    const reason = containerEl === null ? 'tidak ditemukan' : (!containerEl.isConnected ? 'tidak terhubung' : 'dimensi nol')
    if (attemptSetReadyRetries < MAX_ATTEMPT_RETRIES) {
      attemptSetReadyRetries++
      setTimeout(attemptSetReady, RETRY_DELAY_MS)
    }
    else {
      const errorMsgStr = `Elemen kontainer chart (${reason}) setelah ${MAX_ATTEMPT_RETRIES} percobaan. Chart tidak dapat ditampilkan.`
      const errorObj = new Error(errorMsgStr)
      handleChartError(errorObj, 'Inisiasi Elemen Kontainer Gagal')
    }
    return
  }

  attemptSetReadyRetries = 0
  devErrorMessage.value = null
  if (observer.value) {
    observer.value.disconnect()
  }
  if (fallbackTimeoutId) {
    clearTimeout(fallbackTimeoutId)
    fallbackTimeoutId = null
  }
  isChartReadyToRender.value = false

  try {
    observer.value = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 30 && height > 30) {
          if (!isChartReadyToRender.value) {
            isChartReadyToRender.value = true
            chartContainerFailedOverall.value = false
            weeklyChartKey.value++
          }
          if (observer.value && containerEl instanceof Element) {
            observer.value.unobserve(containerEl)
          }
          if (observer.value) {
            observer.value.disconnect()
            observer.value = null
          }
          if (fallbackTimeoutId) {
            clearTimeout(fallbackTimeoutId)
            fallbackTimeoutId = null
          }
          return
        }
      }
    })
    if (containerEl instanceof Element) {
      observer.value.observe(containerEl)
    }
    else {
      const initError = new Error('chartContainerActualRef bukan Element yang valid untuk ResizeObserver.')
      handleChartError(initError, 'ResizeObserver Init Error')
      return
    }

    fallbackTimeoutId = setTimeout(() => {
      if (!isChartReadyToRender.value && observer.value) {
        const errorDetail = `Kontainer (${containerEl?.offsetWidth}x${containerEl?.offsetHeight}) mungkin tidak visible atau dimensi nol setelah timeout.`
        const timeoutError = new Error(`Timeout untuk ResizeObserver. ${errorDetail}`)
        handleChartError(timeoutError, 'Fallback Timeout ResizeObserver')
        if (containerEl instanceof Element) {
          observer.value?.unobserve(containerEl)
        }
        observer.value?.disconnect()
        observer.value = null
      }
    }, RETRY_DELAY_MS * MAX_ATTEMPT_RETRIES + 500)
  }
  catch (err) {
    handleChartError(err as Error, 'Eksepsi saat inisiasi ResizeObserver')
  }
}

async function retryChartInit() {
  chartContainerFailedOverall.value = false
  isChartReadyToRender.value = false
  devErrorMessage.value = null
  attemptSetReadyRetries = 0

  if (observer.value) {
    observer.value.disconnect()
    observer.value = null
  }
  if (fallbackTimeoutId) {
    clearTimeout(fallbackTimeoutId)
    fallbackTimeoutId = null
  }

  await vueNextTick()
  updateChartData()

  if (!props.parentLoading && props.parentError === null) { // Hanya memeriksa parentError, tidak quotaData
    attemptSetReady()
  }
}

function updateChartData() {
  const newWeeklyData = props.weeklyUsageData
  // const newQuotaData = props.quotaData // Tidak digunakan lagi
  const newParentLoading = props.parentLoading
  const newParentError = props.parentError
  const oldParentLoadingValue = lastParentLoading.value

  if (newParentLoading === false && oldParentLoadingValue === true) {
    weeklyDataProcessed.value = true
  }
  else if (newParentLoading === true && oldParentLoadingValue === false) {
    weeklyDataProcessed.value = false
    isChartReadyToRender.value = false
  }

  let currentNoDataText = 'Belum ada penggunaan minggu ini.'
  let newSeriesDataValues: number[] = Array.from({ length: 7 }, () => 0)

  if (newParentLoading) {
    currentNoDataText = 'Memuat data...'
    quotaWeeklyBarSeries.value = [{ name: 'Penggunaan Harian', data: newSeriesDataValues }]
    chartNoDataTextFromLogic.value = currentNoDataText
    lastParentLoading.value = newParentLoading
    return
  }

  if (chartContainerFailedOverall.value) {
    currentNoDataText = 'Area chart tidak dapat disiapkan.'
  }
  else if (newParentError != null) {
    currentNoDataText = 'Gagal memuat data tren mingguan.'
    if (devErrorMessage.value == null && newParentError != null) {
      devErrorMessage.value = typeof newParentError === 'string' ? newParentError : (newParentError.message || 'Error tidak diketahui dari parent.')
    }
  }
  // Tidak ada lagi kondisi !newQuotaData
  else if (Array.isArray(newWeeklyData?.weekly_data)) {
    const rawSeriesData = newWeeklyData.weekly_data.slice(-7)
    while (rawSeriesData.length < 7) {
      rawSeriesData.unshift(0)
    }
    newSeriesDataValues = rawSeriesData.map(val => Number(Number.parseFloat(val?.toString() ?? '0').toFixed(1)) || 0)

    if (newSeriesDataValues.every(d => d === 0)) {
      currentNoDataText = 'Belum ada penggunaan minggu ini.'
    }
    else {
      currentNoDataText = ''
    }
    weeklyDataProcessed.value = true
  }
  else {
    currentNoDataText = 'Data tren tidak tersedia atau format salah.'
    weeklyDataProcessed.value = true
  }

  chartNoDataTextFromLogic.value = currentNoDataText
  quotaWeeklyBarSeries.value = [{ name: 'Penggunaan Harian', data: newSeriesDataValues }]

  if (!newParentLoading && newParentError === null && !isChartReadyToRender.value && !chartContainerFailedOverall.value) { // Hapus cek !newQuotaData
    vueNextTick().then(attemptSetReady)
  }

  if (weeklyChartRef.value && isChartReadyToRender.value && !chartContainerFailedOverall.value && !newParentLoading) {
    try {
      const newOptions = quotaWeeklyBarOptions.value
      weeklyChartRef.value.updateOptions(newOptions, false, true, true)
      weeklyChartRef.value.updateSeries(quotaWeeklyBarSeries.value, true)
    }
    catch (e: any) {
      handleChartError(e, 'Gagal update chart di updateChartData')
    }
  }
  lastParentLoading.value = newParentLoading
}

watch(() => props.weeklyUsageData, () => {
  if (!props.parentLoading)
    updateChartData()
}, { deep: true, flush: 'post' })

// Hapus watch untuk props.quotaData
// watch(() => props.quotaData, () => {
//   if (!props.parentLoading)
//     updateChartData()
// }, { deep: true, flush: 'post' })

watch(() => props.parentLoading, (newVal, oldVal) => {
  updateChartData()
  if (!newVal && oldVal && props.parentError === null && !isChartReadyToRender.value && !chartContainerFailedOverall.value) { // Hapus cek props.quotaData
    vueNextTick().then(attemptSetReady)
  }
}, { flush: 'post' })

watch(() => props.parentError, (newErr) => {
  if (newErr != null && !props.parentLoading) {
    devErrorMessage.value = typeof newErr === 'string' ? newErr : (newErr.message || 'Error tidak diketahui dari parent.')
  }
  if (!props.parentLoading)
    updateChartData()
}, { flush: 'post' })

watch(() => vuetifyTheme.current.value.dark, () => {
  if (!props.parentLoading)
    updateChartData()
}, { flush: 'post' })

watch(() => props.dashboardRenderKey, async (_newKey, _oldKey) => {
  chartContainerFailedOverall.value = false
  isChartReadyToRender.value = false
  attemptSetReadyRetries = 0
  devErrorMessage.value = null

  if (observer.value) {
    observer.value.disconnect()
    observer.value = null
  }
  if (fallbackTimeoutId) {
    clearTimeout(fallbackTimeoutId)
    fallbackTimeoutId = null
  }

  await vueNextTick()
  updateChartData()
  if (canInitChart.value) {
    attemptSetReady()
  }
}, { immediate: true, flush: 'post' })

watchDebounced([() => smAndDown.value, () => mobile.value], () => {
  if (weeklyChartRef.value && isChartReadyToRender.value && !chartContainerFailedOverall.value && !props.parentLoading) {
    try {
      weeklyChartRef.value.updateOptions(quotaWeeklyBarOptions.value, false, true, true)
    }
    catch (e: any) {
      handleChartError(e, 'Gagal update chart akibat perubahan ukuran layar')
    }
  }
}, { debounce: 150, maxWait: 500, flush: 'post' })
</script>

<template>
  <div class="chart-error-boundary">
    <template v-if="!props.parentLoading && props.parentError != null && !chartContainerFailedOverall">
      <VCard style="height: 100%;" class="vuexy-card d-flex flex-column" :class="{ 'vuexy-card-shadow': vuetifyTheme.current.value.dark }">
        <VCardItem class="vuexy-card-header pb-1 pt-4">
          <VCardTitle class="vuexy-card-title">
            <VIcon icon="tabler-calendar-stats" class="me-2" />Tren Mingguan
          </VCardTitle>
        </VCardItem>
        <VCardText class="flex-grow-1 d-flex flex-column justify-center align-items-center text-center pa-4">
          <VAlert
            type="error"
            variant="tonal"
            prominent
            border="start"
            class="w-100 text-start vuexy-alert"
            :color="errorDisplayColor"
          >
            <template #prepend>
              <VIcon size="24" class="me-2">
                tabler-alert-circle-filled
              </VIcon>
            </template>
            <h6 class="text-h6 mb-1">
              Gagal Memuat Data Induk
            </h6>
            <p class="text-body-2">
              Tidak dapat mengambil data tren mingguan dari server.
            </p>
            <p v-if="typeof props.parentError === 'string'" class="text-caption mt-1">
              Detail: {{ props.parentError }}
            </p>
            <p v-else-if="props.parentError?.message != null" class="text-caption mt-1">
              Detail: {{ props.parentError.message }}
            </p>
            <div v-if="devErrorMessage != null && devErrorMessage !== (Boolean(props.parentError.message) ? props.parentError.message : props.parentError.toString())" class="dev-error-overlay-message mt-2">
              <strong>Pesan Error Tambahan (Dev):</strong><br>{{ devErrorMessage }}
            </div>
          </VAlert>
          <VBtn :color="errorDisplayColor" variant="outlined" size="small" class="mt-4" prepend-icon="tabler-refresh" @click="emit('refresh')">
            Ulangi Muat Data Induk
          </VBtn>
        </VCardText>
      </VCard>
    </template>

    <template v-else-if="!props.parentLoading && chartContainerFailedOverall">
      <VCard style="height: 100%;" class="vuexy-card d-flex flex-column" :class="{ 'vuexy-card-shadow': vuetifyTheme.current.value.dark }">
        <VCardItem class="vuexy-card-header pb-1 pt-4">
          <VCardTitle class="vuexy-card-title">
            <VIcon icon="tabler-calendar-stats" class="me-2" />Tren Mingguan
          </VCardTitle>
        </VCardItem>
        <VCardText class="flex-grow-1 d-flex flex-column justify-center align-items-center text-center pa-4">
          <VAlert
            type="error"
            variant="tonal"
            prominent
            border="start"
            class="w-100 text-start vuexy-alert"
            :color="errorDisplayColor"
          >
            <template #prepend>
              <VIcon size="24" class="me-2">
                tabler-error-404
              </VIcon>
            </template>
            <h6 class="text-h6 mb-1">
              Chart Tidak Dapat Ditampilkan
            </h6>
            <p class="text-body-2">
              Terjadi masalah saat menyiapkan area untuk menampilkan chart mingguan.
            </p>
            <div v-if="typeof devErrorMessage === 'string'" class="dev-error-overlay-message mt-2">
              <strong>Pesan Error (Dev):</strong><br>{{ devErrorMessage }}
            </div>
          </VAlert>
          <VBtn variant="tonal" color="primary" class="mt-4" size="small" @click="retryChartInit">
            <VIcon start icon="tabler-refresh-dot" /> Coba Inisiasi Ulang Chart
          </VBtn>
        </VCardText>
      </VCard>
    </template>

    <template v-else-if="!props.parentLoading">
      <VCard style="height: 100%;" class="vuexy-card" :class="{ 'vuexy-card-shadow': vuetifyTheme.current.value.dark }">
        <VCardItem class="vuexy-card-header pb-1 pt-4">
          <VCardTitle class="vuexy-card-title">
            <VIcon icon="tabler-calendar-stats" class="me-2" />Tren Mingguan
          </VCardTitle>
          <VCardSubtitle>Ringkasan 7 Hari Terakhir</VCardSubtitle>
        </VCardItem>

        <VCardText class="chart-card-text d-flex flex-column pt-2 chart-container">
          <div class="flex-grow-1 d-flex flex-column justify-space-between">
            <VRow class="mb-2 mt-0">
              <template v-if="mobile || smAndDown">
                <VCol cols="12" class="d-flex flex-column pa-0 weekly-chart-col mt-4">
                  <div ref="chartContainerActualRef" class="weekly-chart-container-actual" :style="{ minHeight: chartHeightInPx, flexGrow: 1, position: 'relative' }">
                    <div class="chart-inner-wrapper">
                      <ClientOnly>
                        <VueApexCharts
                          v-if="isChartReadyToRender && weeklyDataProcessed && !props.parentLoading"
                          ref="weeklyChartRef"
                          :key="`${weeklyChartKey}-${vuetifyTheme.current.value.dark}-dinamis-mobile-unlimited`" type="bar" :height="chartHeight"
                          :options="quotaWeeklyBarOptions" :series="quotaWeeklyBarSeries"
                          class="w-100"
                        />
                        <div v-else-if="!props.parentLoading" class="chart-fallback-container text-center pa-2 d-flex flex-column justify-center align-items-center" :style="{ height: '100%', width: '100%', minHeight: chartHeightInPx }">
                          <VProgressCircular v-if="isLoadingInternalProcessing === true" indeterminate size="28" color="primary" class="mb-2" />
                          <VIcon v-else-if="!isLoadingInternalProcessing && hasNoWeeklyData" size="32" :color="infoDisplayColor" class="mb-1">
                            tabler-chart-infographic
                          </VIcon>
                          <p class="text-caption text-medium-emphasis">
                            {{ chartNoDataTextFromLogic !== '' ? chartNoDataTextFromLogic : 'Menyiapkan tampilan chart...' }}
                          </p>
                        </div>
                        <template #fallback>
                          <div class="chart-fallback-container d-flex flex-column justify-center align-items-center" :style="{ height: '100%', width: '100%', minHeight: chartHeightInPx }">
                            <VProgressCircular indeterminate size="28" color="primary" />
                            <p class="text-caption mt-2 text-medium-emphasis">
                              Memuat komponen chart...
                            </p>
                          </div>
                        </template>
                      </ClientOnly>
                    </div>
                  </div>
                </VCol>
              </template>
              <template v-else>
                <VCol cols="12" class="d-flex flex-column pa-0 weekly-chart-col">
                  <div ref="chartContainerActualRef" class="weekly-chart-container-actual" :style="{ minHeight: chartHeightInPx, flexGrow: 1, position: 'relative' }">
                    <div class="chart-inner-wrapper">
                      <ClientOnly>
                        <VueApexCharts
                          v-if="isChartReadyToRender && weeklyDataProcessed && !props.parentLoading"
                          ref="weeklyChartRef"
                          :key="`${weeklyChartKey}-${vuetifyTheme.current.value.dark}-dinamis-desktop-unlimited`" type="bar" :height="chartHeight"
                          :options="quotaWeeklyBarOptions" :series="quotaWeeklyBarSeries"
                          class="w-100"
                        />
                        <div v-else-if="!props.parentLoading" class="chart-fallback-container text-center pa-2 d-flex flex-column justify-center align-items-center" :style="{ height: '100%', width: '100%', minHeight: chartHeightInPx }">
                          <VProgressCircular v-if="isLoadingInternalProcessing === true" indeterminate size="28" color="primary" class="mb-2" />
                          <VIcon v-else-if="!isLoadingInternalProcessing && hasNoWeeklyData" size="32" :color="infoDisplayColor" class="mb-1">
                            tabler-chart-infographic
                          </VIcon>
                          <p class="text-caption text-medium-emphasis">
                            {{ chartNoDataTextFromLogic !== '' ? chartNoDataTextFromLogic : 'Menyiapkan tampilan chart...' }}
                          </p>
                        </div>
                        <template #fallback>
                          <div class="chart-fallback-container d-flex flex-column justify-center align-items-center" :style="{ height: '100%', width: '100%', minHeight: chartHeightInPx }">
                            <VProgressCircular indeterminate size="28" color="primary" />
                            <p class="text-caption mt-2 text-medium-emphasis">
                              Memuat komponen chart...
                            </p>
                          </div>
                        </template>
                      </ClientOnly>
                    </div>
                  </div>
                </VCol>
              </template>
            </VRow>

            <VCardText class="border rounded pa-sm-3 pa-2 mt-auto mb-0 mx-0 weekly-summary-box vuexy-inner-card">
              <VRow class="ma-0 justify-center">
                <VCol cols="12" sm="6" class="pa-2 text-center">
                  <div class="d-flex align-center justify-center mb-1">
                    <VAvatar color="primary" variant="tonal" rounded size="28" class="me-2">
                      <VIcon icon="tabler-calendar-today" size="18" />
                    </VAvatar>
                    <span class="text-caption">Total Pemakaian Hari Ini</span>
                  </div>
                  <div class="summary-item-content d-flex flex-column align-center">
                    <h6 class="font-weight-medium summary-value">
                      {{ lastWeeklyUsage != null ? formatQuota(lastWeeklyUsage) : 'N/A' }}
                    </h6>
                  </div>
                </VCol>
              </VRow>
            </VCardText>
          </div>
        </VCardText>
      </VCard>
    </template>
    <template v-else>
      <VCard style="height: 100%;" class="vuexy-card d-flex flex-column justify-center align-items-center" :class="{ 'vuexy-card-shadow': vuetifyTheme.current.value.dark }">
        <div class="vuexy-loading-overlay">
          <VProgressCircular indeterminate size="48" :color="primaryColor" class="vuexy-spinner" />
          <p class="text-body-1 mt-3 loading-text" :style="{ color: primaryColor }">
            Memuat Data Tren Mingguan...
          </p>
        </div>
      </VCard>
    </template>
  </div>
</template>

<style scoped>
/* Pertahankan gaya yang sudah ada dan sesuaikan jika ada perubahan */
.vuexy-card {
  border-radius: 0.75rem;
  transition: box-shadow 0.25s ease;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: visible;
}
.vuexy-card-shadow {
  box-shadow: 0 4px 18px 0 rgba(var(--v-shadow-key-umbra-color), 0.12);
}
.vuexy-card-header {
  background: rgba(var(--v-theme-primary), var(--v-selected-opacity, 0.08));
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
  overflow: visible;
}
.vuexy-loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(var(--v-theme-surface), var(--v-hover-opacity, 0.85));
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
.chart-card-text { min-height: 370px; }
.vue-apexcharts { max-width: 100%; direction: ltr; }
.terpakai-chip { position: relative; top: -1px; font-size: 0.6875rem; padding: 0 6px; line-height: 1.2; height: auto; border-radius: 0.55rem !important; }

.chart-fallback-container {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    width: 100%;
    flex-grow: 1;
    padding: 1rem;
    text-align: center;
}
.weekly-summary-box {
  width: 100%;
  margin-top: auto;
  background-color: rgba(var(--v-theme-surface-variant), 0.3);
  border-radius: 6px;
}
.vuexy-inner-card {
    border-radius: 6px;
    background-color: rgba(var(--v-theme-surface-light, var(--v-theme-surface)), 0.5);
    border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
/* Hapus border-right untuk weekly-summary-box .v-col-sm-6:first-child */
/* .weekly-summary-box .v-col-sm-6:first-child {
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
} */
@media (max-width: 599.98px) {
  .weekly-summary-box .v-col-sm-6:first-child {
    border-right: none;
    border-bottom: none; /* Hapus border-bottom juga karena hanya ada 1 kolom */
  }
  .weekly-summary-col {
    padding-top: 0.6rem !important;
    padding-bottom: 0.6rem !important;
    padding-left: 0.65rem !important;
    padding-right: 0.65rem !important;
  }
}
.weekly-summary-col .d-flex.align-center.mb-1 { min-height: 28px; }
.summary-item-content { padding: 8px 0; display: flex; flex-direction: column; align-items: flex-start; width: 100%; }
.summary-item-content > .summary-value { line-height: 1.4; margin-bottom: 0.25rem; font-size: 1.125rem; word-break: break-all; }
/* Hapus gaya untuk progress-linear karena tidak digunakan */
/* .summary-item-content > .v-progress-linear { width: 100%; margin-inline-start: 0 !important; } */

.chart-inner-wrapper {
  position: absolute;
  width: 100%;
  height: 100%;
  top: 0;
  left: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.weekly-chart-container-actual {
  overflow: visible;
}

@media (max-width: 959.98px) {
  .chart-card-text { min-height: auto; padding-top: 1rem !important; }
  .weekly-quota-info-col .text-h3 { font-size: 1.75rem !important; }
  .weekly-quota-info-col .text-caption { font-size: 0.7rem !important; }
}

@media (max-width: 599.98px) {
  .summary-item-content > .summary-value { font-size: 1rem !important; }
  .weekly-summary-col .d-flex.align-center.mb-1 .text-caption { font-size: 0.75rem; }
  .weekly-summary-box { padding: 0.5rem !important; }
  .weekly-quota-info-col .text-h3 { font-size: 1.6rem !important; }
  .terpakai-chip { font-size: 0.6rem; }
}

.custom-tooltip.vuexy-tooltip {
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
.progress-bar-custom { cursor: default; }

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

.apexcharts-tooltip-custom {
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
  border-radius: 0.75rem;
  width: 100%;
}
.vuexy-alert .text-h6 {
    color: currentColor;
}
.vuexy-alert .text-body-2,
.vuexy-alert .text-caption {
    color: currentColor;
    opacity: 0.85;
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

:deep(.apexcharts-tooltip) {
  background: rgb(var(--v-theme-surface-light, var(--v-theme-surface))) !important;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important;
  box-shadow: 0px 4px 8px -4px rgba(var(--v-shadow-key-umbra-color), 0.2), 0px 8px 16px -4px rgba(var(--v-shadow-key-penumbra-color), 0.14), 0px 6px 6px -6px rgba(var(--v-shadow-key-ambient-color), 0.12) !important;
  border-radius: 6px !important;
  padding: 0.5rem 0.75rem !important;
  transition: opacity 0.2s ease-in-out, transform 0.2s ease-in-out;
  z-index: 20;
}

:deep(.apexcharts-canvas) {
  overflow: visible !important;
}

:deep(.apexcharts-tooltip-title) {
  background: transparent !important;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important;
  padding-bottom: 0.3rem !important;
  margin-bottom: 0.3rem !important;
  font-weight: 600;
}

:deep(.apexcharts-tooltip-series-group) {
  background: transparent !important;
  padding: 0.3rem 0 !important;
}
</style>
