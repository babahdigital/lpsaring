/**
 * @file composables/useMonthlyDataProcessing.ts
 * @description Composable murni untuk memproses data penggunaan bulanan.
 * Mengubah data mentah dari API menjadi format yang siap pakai untuk chart.
 */
import type { MonthlyUsageData } from '~/types/user'

export function processMonthlyDataForChart(data: MonthlyUsageData[] | undefined | null) {
  const result = {
    categories: [] as string[],
    seriesData: [] as number[],
    originalMonthYear: [] as string[],
    yAxisTitle: 'Penggunaan (MB)',
    displayMax: 10,
    useGigaByteScale: false,
    allZero: true,
    isValid: false,
    totalUsageMb: 0,
  }

  if (!Array.isArray(data) || data.length === 0)
    return result

  // Urutkan data berdasarkan bulan-tahun untuk memastikan urutan yang benar
  const sortedData = [...data].sort((a, b) => {
    const dateA = new Date(a.month_year.replace(/(\d{4})-(\d{2})/, '$1/$2/01'))
    const dateB = new Date(b.month_year.replace(/(\d{4})-(\d{2})/, '$1/$2/01'))
    return dateA.getTime() - dateB.getTime()
  })

  const rawSeriesMb = sortedData.map(item => item.usage_mb ?? 0)
  result.totalUsageMb = rawSeriesMb.reduce((sum, current) => sum + current, 0) // Hitung total penggunaan

  // Validasi dan format kategori (nama bulan)
  const validPoints = sortedData
    .map((item, index) => {
      try {
        const [year, month] = item.month_year.split('-').map(Number)
        const yearNum = year ?? 0
        const monthNum = month ?? 0
        const date = new Date(yearNum, monthNum - 1)
        // Pastikan tanggal valid sebelum memformat
        if (Number.isNaN(date.getTime()))
          return null
        return {
          category: date.toLocaleString('id-ID', { month: 'short' }),
          value: rawSeriesMb[index],
          originalMY: item.month_year,
        }
      }
      catch {
        return null
      }
    })
    .filter(point => point !== null) as { category: string, value: number, originalMY: string }[]

  result.categories = validPoints.map(p => p.category)
  result.originalMonthYear = validPoints.map(p => p.originalMY)
  const finalSeriesMb = validPoints.map(p => p.value)

  result.isValid = finalSeriesMb.length > 0
  result.allZero = result.totalUsageMb === 0

  if (result.isValid) {
    const maxUsageMb = Math.max(...finalSeriesMb, 0)
    result.useGigaByteScale = maxUsageMb / 1024 >= 1.0

    if (result.useGigaByteScale) {
      const maxGb = maxUsageMb / 1024
      // Atur headroom (ruang atas) untuk sumbu Y agar bar tidak mentok
      let displayMaxGb = Math.ceil(maxGb * 1.15)
      // Pembulatan cerdas untuk sumbu Y agar labelnya bagus (misal: 2.5, 5, 10)
      if (displayMaxGb > 10)
        displayMaxGb = Math.ceil(displayMaxGb / 2.5) * 2.5
      else if (displayMaxGb > 1)
        displayMaxGb = Math.ceil(displayMaxGb)
      else
        displayMaxGb = Math.max(0.1, Math.ceil(displayMaxGb * 10) / 10)

      result.displayMax = displayMaxGb
      result.yAxisTitle = 'Penggunaan (GB)'
      result.seriesData = finalSeriesMb.map(mb => Number.parseFloat((mb / 1024).toFixed(1)))
    }
    else {
      let displayMaxMb = Math.ceil(maxUsageMb * 1.15)
      // Pembulatan ke puluhan atau ratusan terdekat
      const roundingFactor = 10 ** Math.max(0, Math.floor(Math.log10(displayMaxMb)) - 1)
      displayMaxMb = Math.ceil(displayMaxMb / roundingFactor) * roundingFactor

      result.displayMax = Math.max(10, displayMaxMb) // Minimum 10 MB
      result.yAxisTitle = 'Penggunaan (MB)'
      result.seriesData = finalSeriesMb.map(mb => Math.round(mb))
    }
  }

  return result
}
