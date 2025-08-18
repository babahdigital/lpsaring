<script setup lang="ts">
import type { User, WeeklyUsageResponse } from '~/types/user'

import { calculatePercentage, formatQuota, getUsageChipColor } from './composables/useChartUtils'
import { useWeeklyChart } from './composables/useWeeklyChart'

const props = defineProps<{
  quotaData: User | null
  weeklyUsageData: WeeklyUsageResponse | null
  parentLoading: boolean
  parentError: any | null
  dashboardRenderKey: number
}>()

const emit = defineEmits<{
  refresh: []
}>()

const {
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
  handleRefresh,
} = useWeeklyChart(props, emit)
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
          <VAlert type="error" variant="tonal" prominent border="start" class="w-100 text-start vuexy-alert" :color="errorDisplayColor">
            <template #prepend>
              <VIcon size="24" class="me-2">
                tabler-alert-circle-filled
              </VIcon>
            </template>
            <h6 class="text-h6 mb-1">
              Gagal Memuat Data
            </h6>
            <p class="text-body-2">
              Tidak dapat mengambil data tren mingguan.
            </p>
            <p v-if="typeof props.parentError === 'string'" class="text-caption mt-1">
              Detail: {{ props.parentError }}
            </p>
            <p v-else-if="props.parentError?.message != null" class="text-caption mt-1">
              Detail: {{ props.parentError.message }}
            </p>
            <div v-if="devErrorMessage != null" class="dev-error-overlay-message mt-2">
              <strong>Pesan Error Tambahan:</strong><br />{{ devErrorMessage }}
            </div>
          </VAlert>
          <VBtn :color="errorDisplayColor" variant="outlined" size="small" class="mt-4" prepend-icon="tabler-refresh" @click="handleRefresh">
            Ulangi
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
              <template v-if="!mobile">
                <VCol cols="12" md="5" class="d-flex flex-column align-self-stretch weekly-quota-info-col">
                  <div class="pt-1 pb-2 px-1">
                    <div class="d-flex align-baseline">
                      <h3 class="text-h3 font-weight-semibold mr-2">
                        {{ props.quotaData ? formatQuota(props.quotaData.total_quota_used_mb) : 'N/A' }}
                      </h3>
                      <VChip v-if="props.quotaData && props.quotaData.total_quota_purchased_mb != null && props.quotaData.total_quota_purchased_mb > 0" :color="getUsageChipColor(props.quotaData.total_quota_used_mb ?? 0, props.quotaData.total_quota_purchased_mb)" size="x-small" class="terpakai-chip" label>
                        {{ calculatePercentage(props.quotaData.total_quota_used_mb ?? 0, props.quotaData.total_quota_purchased_mb) }}%
                      </VChip>
                    </div>
                    <p class="text-caption mt-1">
                      Total Pemakaian
                    </p>
                  </div>
                </VCol>
                <VCol cols="12" md="7" class="d-flex flex-column pa-0 weekly-chart-col">
                  <div ref="chartContainerActualRef" class="weekly-chart-container-actual" :style="{ minHeight: chartHeightInPx, flexGrow: 1, position: 'relative' }">
                    <div class="chart-inner-wrapper">
                      <VueApexCharts v-if="isChartReadyToRender && VueApexCharts && weeklyDataProcessed" ref="weeklyChartRef" :key="`${weeklyChartKey}-desktop`" type="bar" :height="chartHeight" :options="quotaWeeklyBarOptions" :series="quotaWeeklyBarSeries" class="w-100" />
                      <div v-else class="chart-fallback-container" :style="{ height: '100%', minHeight: chartHeightInPx }">
                        <VProgressCircular v-if="isLoadingInternalProcessing" indeterminate size="28" color="primary" class="mb-2" />
                        <p class="text-caption text-medium-emphasis">
                          {{ chartNoDataTextFromLogic || 'Menyiapkan chart...' }}
                        </p>
                      </div>
                    </div>
                  </div>
                </VCol>
              </template>
              <template v-else>
                <VCol cols="12" class="d-flex flex-column align-self-stretch weekly-quota-info-col">
                  <div class="pt-1 pb-2 px-1 text-center">
                    <div class="d-flex align-baseline justify-center">
                      <h3 class="text-h3 font-weight-semibold mr-2">
                        {{ props.quotaData ? formatQuota(props.quotaData.total_quota_used_mb) : 'N/A' }}
                      </h3>
                      <VChip v-if="props.quotaData && props.quotaData.total_quota_purchased_mb != null && props.quotaData.total_quota_purchased_mb > 0" :color="getUsageChipColor(props.quotaData.total_quota_used_mb ?? 0, props.quotaData.total_quota_purchased_mb)" size="x-small" class="terpakai-chip" label>
                        {{ calculatePercentage(props.quotaData.total_quota_used_mb ?? 0, props.quotaData.total_quota_purchased_mb) }}%
                      </VChip>
                    </div>
                    <p class="text-caption mt-1">
                      Total Pemakaian
                    </p>
                  </div>
                </VCol>
                <VCol cols="12" class="d-flex flex-column pa-0 weekly-chart-col mt-4">
                  <div ref="chartContainerActualRef" class="weekly-chart-container-actual" :style="{ minHeight: chartHeightInPx, flexGrow: 1, position: 'relative' }">
                    <div class="chart-inner-wrapper">
                      <VueApexCharts v-if="isChartReadyToRender && VueApexCharts && weeklyDataProcessed" ref="weeklyChartRef" :key="`${weeklyChartKey}-mobile`" type="bar" :height="chartHeight" :options="quotaWeeklyBarOptions" :series="quotaWeeklyBarSeries" class="w-100" />
                      <div v-else class="chart-fallback-container" :style="{ height: '100%', minHeight: chartHeightInPx }">
                        <VProgressCircular v-if="isLoadingInternalProcessing" indeterminate size="28" color="primary" class="mb-2" />
                        <p class="text-caption text-medium-emphasis">
                          {{ chartNoDataTextFromLogic || 'Menyiapkan chart...' }}
                        </p>
                      </div>
                    </div>
                  </div>
                </VCol>
              </template>
            </VRow>
            <VCardText class="border rounded pa-sm-3 pa-2 mt-auto mb-0 mx-0 weekly-summary-box vuexy-inner-card">
              <VRow class="ma-0">
                <VCol cols="12" sm="6" class="pa-2 weekly-summary-col">
                  <div class="d-flex align-center mb-1">
                    <VAvatar color="primary" variant="tonal" rounded size="28" class="me-2">
                      <VIcon icon="tabler-database" size="18" />
                    </VAvatar>
                    <span class="text-caption">Total Akumulasi</span>
                  </div>
                  <div class="summary-item-content">
                    <h6 class="font-weight-medium summary-value">
                      {{ props.quotaData ? formatQuota(props.quotaData.total_quota_purchased_mb) : 'N/A' }}
                    </h6>
                    <VTooltip location="top" content-class="custom-tooltip vuexy-tooltip" transition="scale-transition">
                      <template #activator="{ props: tooltipProps }">
                        <div v-bind="tooltipProps">
                          <VProgressLinear v-if="props.quotaData" :model-value="calculatePercentage(props.quotaData.total_quota_used_mb, props.quotaData.total_quota_purchased_mb)" color="primary" height="8" rounded class="mt-1 progress-bar-custom" />
                          <VProgressLinear v-else :model-value="0" color="grey" height="8" rounded class="mt-1" />
                        </div>
                      </template>
                      <span>Terpakai: {{ props.quotaData ? formatQuota(props.quotaData.total_quota_used_mb) : 'N/A' }}</span>
                    </VTooltip>
                  </div>
                </VCol>
                <VCol cols="12" sm="6" class="pa-2 weekly-summary-col" :style="{ left: mobile ? '0px' : '3px', position: 'relative' }">
                  <div class="d-flex align-center mb-1">
                    <VAvatar :color="props.quotaData ? getUsageChipColor(props.quotaData.total_quota_used_mb, props.quotaData.total_quota_purchased_mb) : 'grey'" variant="tonal" rounded size="28" class="me-2">
                      <VIcon icon="tabler-arrow-bar-to-down" size="18" />
                    </VAvatar>
                    <span class="text-caption">Sisa Kuota</span>
                  </div>
                  <div class="summary-item-content">
                    <h6 class="font-weight-medium summary-value">
                      {{ props.quotaData && props.quotaData.total_quota_purchased_mb != null && props.quotaData.total_quota_used_mb != null ? formatQuota(props.quotaData.total_quota_purchased_mb - props.quotaData.total_quota_used_mb) : 'N/A' }}
                    </h6>
                    <VTooltip location="top" content-class="custom-tooltip vuexy-tooltip" transition="scale-transition">
                      <template #activator="{ props: tooltipProps }">
                        <div v-bind="tooltipProps">
                          <VProgressLinear v-if="props.quotaData && props.quotaData.total_quota_purchased_mb != null && props.quotaData.total_quota_used_mb != null" :model-value="100 - calculatePercentage(props.quotaData.total_quota_used_mb, props.quotaData.total_quota_purchased_mb)" :color="getUsageChipColor(props.quotaData.total_quota_used_mb, props.quotaData.total_quota_purchased_mb)" height="8" rounded class="mt-1 progress-bar-custom" />
                          <VProgressLinear v-else :model-value="0" color="grey" height="8" rounded class="mt-1" />
                        </div>
                      </template>
                      <span>Sisa: {{ props.quotaData && props.quotaData.total_quota_purchased_mb != null && props.quotaData.total_quota_used_mb != null ? formatQuota(props.quotaData.total_quota_purchased_mb - props.quotaData.total_quota_used_mb) : 'N/A' }}</span>
                    </VTooltip>
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
          <VProgressCircular indeterminate size="48" color="primary" class="vuexy-spinner" />
          <p class="text-body-1 mt-3 loading-text" :style="{ color: 'rgba(var(--v-theme-primary))' }">
            Memuat Data Tren Mingguan...
          </p>
        </div>
      </VCard>
    </template>
  </div>
</template>

<style scoped>
/* Style tidak berubah, dipertahankan seperti aslinya */
.vuexy-card { border-radius: 0.75rem; transition: box-shadow 0.25s ease; display: flex; flex-direction: column; height: 100%; }
.vuexy-card-shadow { box-shadow: 0 4px 18px 0 rgba(var(--v-shadow-key-umbra-color), 0.12); }
.vuexy-card-header { background: rgba(var(--v-theme-primary), var(--v-selected-opacity, 0.08)); border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 0.75rem 0.75rem 0 0; }
.vuexy-card-title { color: rgba(var(--v-theme-primary), 1); font-weight: 600; letter-spacing: 0.15px; display: flex; align-items: center; }
.chart-container { position: relative; z-index: 1; flex-grow: 1; display: flex; flex-direction: column; }
.vuexy-loading-overlay { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(var(--v-theme-surface), var(--v-hover-opacity, 0.85)); z-index: 10; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: inherit; backdrop-filter: blur(2px); }
.vuexy-spinner { filter: drop-shadow(0 2px 8px rgba(var(--v-theme-primary), 0.2)); }
.loading-text { font-weight: 600; letter-spacing: 0.5px; animation: pulse 1.5s infinite ease-in-out; }
@keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.7; transform: scale(0.95); } }
.chart-card-text { min-height: 370px; }
.vue-apexcharts { max-width: 100%; direction: ltr; margin-bottom: 30px; }
.terpakai-chip { position: relative; top: -1px; font-size: 0.6875rem; padding: 0 6px; line-height: 1.2; height: auto; border-radius: 0.55rem !important; }
.chart-fallback-container { display: flex; flex-direction: column; justify-content: center; align-items: center; width: 100%; flex-grow: 1; padding: 1rem; text-align: center; }
.weekly-summary-box { width: 100%; margin-top: auto; background-color: rgba(var(--v-theme-surface-variant), 0.3); border-radius: 6px; max-height: 130px; }
.vuexy-inner-card { border-radius: 6px; background-color: rgba(var(--v-theme-surface-light, var(--v-theme-surface)), 0.5); border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.weekly-summary-box .v-col-sm-6:first-child { border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
@media (max-width: 599.98px) { .weekly-summary-box .v-col-sm-6:first-child { border-right: none; border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); } .weekly-summary-col { padding-top: 0.6rem !important; padding-bottom: 0.6rem !important; padding-left: 0.65rem !important; padding-right: 0.65rem !important; } }
.weekly-summary-col .d-flex.align-center.mb-1 { min-height: 28px; }
.summary-item-content { padding: 8px 0; display: flex; flex-direction: column; align-items: flex-start; width: 100%; }
.summary-item-content > .summary-value { line-height: 1.4; margin-bottom: 0.25rem; font-size: 1.125rem; word-break: break-all; }
.summary-item-content > .v-progress-linear { width: 100%; margin-inline-start: 0 !important; }
.chart-inner-wrapper { position: absolute; width: 100%; height: 100%; top: 0; left: 0; display: flex; align-items: center; justify-content: center; }
@media (max-width: 959.98px) { .chart-card-text { min-height: auto; padding-top: 1rem !important; } .weekly-quota-info-col .text-h3 { font-size: 1.75rem !important; } .weekly-quota-info-col .text-caption { font-size: 0.7rem !important; } }
@media (max-width: 599.98px) { .summary-item-content > .summary-value { font-size: 1rem !important; } .weekly-summary-col .d-flex.align-center.mb-1 .text-caption { font-size: 0.75rem; } .weekly-summary-box { padding: 0.5rem !important; } .weekly-quota-info-col .text-h3 { font-size: 1.6rem !important; } .terpakai-chip { font-size: 0.6rem; } }
.custom-tooltip.vuexy-tooltip { background-color: rgb(var(--v-theme-surface-light, var(--v-theme-surface))) !important; color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important; border-radius: 6px !important; padding: 0.5rem 0.75rem !important; font-size: 0.8125rem !important; box-shadow: 0px 4px 8px -4px rgba(var(--v-shadow-key-umbra-color), 0.2), 0px 8px 16px -4px rgba(var(--v-shadow-key-penumbra-color), 0.14), 0px 6px 6px -6px rgba(var(--v-shadow-key-ambient-color), 0.12) !important; max-width: 250px; text-align: center; }
.progress-bar-custom { cursor: default; }
.dev-error-overlay-message { background-color: rgba(var(--v-theme-error), 0.1); color: rgba(var(--v-theme-error), 1); padding: 0.5rem; border-radius: 4px; font-size: 0.75rem; white-space: pre-wrap; word-break: break-all; max-height: 100px; overflow-y: auto; border: 1px solid rgba(var(--v-theme-error), 0.3); text-align: left; width: 100%; box-sizing: border-box; }
.apexcharts-tooltip-custom { background-color: rgb(var(--v-theme-surface-light, var(--v-theme-surface))) !important; color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important; border-radius: 6px !important; padding: 0.5rem 0.75rem !important; font-size: 0.8125rem !important; box-shadow: 0px 4px 8px -4px rgba(var(--v-shadow-key-umbra-color), 0.2), 0px 8px 16px -4px rgba(var(--v-shadow-key-penumbra-color), 0.14), 0px 6px 6px -6px rgba(var(--v-shadow-key-ambient-color), 0.12) !important; max-width: 250px; text-align: center; }
.vuexy-alert { border-radius: 0.75rem; width: 100%; }
.vuexy-alert .text-h6 { color: currentColor; }
.vuexy-alert .text-body-2, .vuexy-alert .text-caption { color: currentColor; opacity: 0.85; }
</style>

<style>
.chart-error-boundary { position: relative; height: 100%; width: 100%; display: flex; flex-direction: column; }
:deep(.apexcharts-tooltip) { background: rgb(var(--v-theme-surface-light, var(--v-theme-surface))) !important; color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important; box-shadow: 0px 4px 8px -4px rgba(var(--v-shadow-key-umbra-color), 0.2), 0px 8px 16px -4px rgba(var(--v-shadow-key-penumbra-color), 0.14), 0px 6px 6px -6px rgba(var(--v-shadow-key-ambient-color), 0.12) !important; border-radius: 6px !important; padding: 0.5rem 0.75rem !important; transition: opacity 0.2s ease-in-out, transform 0.2s ease-in-out; }
:deep(.apexcharts-tooltip-title) { background: transparent !important; color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity)) !important; border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important; padding-bottom: 0.3rem !important; margin-bottom: 0.3rem !important; font-weight: 600; }
:deep(.apexcharts-tooltip-series-group) { background: transparent !important; padding: 0.3rem 0 !important; }
</style>
