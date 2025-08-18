/**
 * @file composables/utils/chartUtils.ts
 * @description Berisi fungsi utilitas murni (pure functions) yang digunakan bersama oleh berbagai komponen chart.
 * Tujuannya adalah untuk mengisolasi logika yang dapat digunakan kembali.
 */
import type { ApexOptions } from 'apexcharts'

// CATATAN: Fungsi hexToRgb sengaja dihapus dari file ini untuk mengatasi peringatan "Duplicated imports".
// Proyek Anda sudah menyediakan fungsi ini dari '@core/utils/colorConverter.ts'.

/**
 * Memformat nilai kuota untuk ditampilkan di UI (misal: '1.2 GB' atau '500 MB').
 * Fungsi ini lebih disukai karena menggunakan API Intl.NumberFormat untuk lokalisasi yang tepat.
 * @param value Nilai numerik kuota (misalnya dalam MB atau GB).
 * @param useGbScale Menentukan apakah nilai harus diformat sebagai Gigabyte.
 * @param forDataLabel Opsi untuk label data di atas bar chart (menyembunyikan nilai yang sangat kecil agar tidak ramai).
 * @returns String kuota yang telah diformat dengan unitnya.
 */
export function formatQuotaForDisplay(value: number | null | undefined, useGbScale: boolean, forDataLabel = false): string {
  const numericValue = value ?? 0

  if (forDataLabel && Math.abs(numericValue) < 0.1)
    return ''

  try {
    const formatter = new Intl.NumberFormat('id-ID', {
      maximumFractionDigits: useGbScale ? 1 : 0,
      style: 'unit',
      unit: useGbScale ? 'gigabyte' : 'megabyte',
      unitDisplay: 'narrow',
    })
    return formatter.format(numericValue)
  }
  catch (e) {
    console.warn(`[chartUtils] Intl.NumberFormat gagal, menggunakan fallback manual. Error: ${(e as Error).message}`)
    return useGbScale ? `${numericValue.toFixed(1)} GB` : `${Math.round(numericValue)} MB`
  }
}

/**
 * Menghasilkan objek konfigurasi (options) dasar untuk ApexCharts.
 * Opsi ini dirancang agar reaktif terhadap perubahan tema dan ukuran layar (responsif).
 * @returns Objek konfigurasi ApexOptions yang siap pakai.
 */
export function getRefactoredMonthlyOptions(
  noDataMessage: string,
  isDarkTheme: boolean,
  chartPrimaryColor: string,
  themeBorderColor: string,
  themeLabelColor: string,
  legendColor: string,
  isMobile: boolean,
): ApexOptions {
  const responsiveOptions: ApexOptions['responsive'] = []

  if (!isMobile) {
    responsiveOptions.push(
      { breakpoint: 1441, options: { plotOptions: { bar: { columnWidth: '41%' } } } },
      { breakpoint: 960, options: { plotOptions: { bar: { columnWidth: '45%' } } } },
    )
  }
  else {
    responsiveOptions.push(
      {
        breakpoint: 599,
        options: {
          plotOptions: { bar: { columnWidth: '55%' } },
          yaxis: { labels: { show: false } },
          grid: { padding: { right: 0, left: -15 } },
          dataLabels: { style: { fontSize: '10px' } },
        },
      },
      {
        breakpoint: 420,
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
      animations: {
        enabled: true,
        easing: 'easeinout',
        speed: 600,
        dynamicAnimation: { enabled: true, speed: 350 },
      } as any,
      states: {
        hover: {
          filter: {
            type: 'none',
          },
        },
      },
    } as any, // PERBAIKAN: Menambahkan `as any` untuk mengatasi tipe `states` yang hilang
    plotOptions: {
      bar: {
        columnWidth: '32%',
        borderRadiusApplication: 'end',
        borderRadius: 4,
        distributed: false,
        dataLabels: { position: 'top' },
      },
    },
    colors: [chartPrimaryColor],
    dataLabels: {
      enabled: true,
      offsetY: -20,
      style: {
        fontSize: '12px',
        colors: [legendColor],
        fontWeight: '600',
        fontFamily: 'Public Sans, sans-serif',
      },
    },
    grid: {
      show: false,
      padding: { top: 0, bottom: 0, left: -10, right: -10 },
    },
    legend: { show: false },
    tooltip: {
      enabled: true,
      theme: isDarkTheme ? 'dark' : 'light',
      style: { fontSize: '12px', fontFamily: 'Public Sans, sans-serif' },
      marker: { show: false },
    },
    xaxis: {
      categories: [],
      axisBorder: { show: true, color: themeBorderColor },
      axisTicks: { show: false },
      labels: {
        formatter: (value: string | number) => {
          // Ensure value is string and handle edge cases
          const stringValue = value ? String(value) : ''
          return stringValue.length > 3 ? stringValue.substring(0, 3) : stringValue
        },
        style: { colors: themeLabelColor, fontSize: '13px', fontFamily: 'Public Sans, sans-serif' },
      },
    },
    yaxis: {
      min: 0,
      title: { text: undefined },
      labels: {
        offsetX: -15,
        style: { fontSize: '13px', colors: themeLabelColor, fontFamily: 'Public Sans, sans-serif' },
      },
      axisBorder: { show: false },
      axisTicks: { show: true, color: themeBorderColor },
    },
    noData: {
      text: noDataMessage,
      align: 'center',
      verticalAlign: 'middle',
      offsetX: 0,
      offsetY: -10,
      style: { color: themeLabelColor, fontSize: '14px', fontFamily: 'Public Sans, sans-serif' },
    },
    responsive: responsiveOptions,
  }
}
