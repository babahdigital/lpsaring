// VERSI FINAL - Menghapus impor yang tidak perlu

export function formatQuota(value: number | null | undefined): string {
  const numericValue = value ?? 0
  if (numericValue >= 1024)
    return `${(numericValue / 1024).toFixed(2)} GB`
  return `${numericValue.toFixed(0)} MB`
}

export function getUsageChipColor(used: number | null | undefined, purchased: number | null | undefined): string {
  const numUsed = used ?? 0
  const numPurchased = purchased ?? 0
  if (numPurchased <= 0)
    return 'grey'
  const percentageUsed = (numUsed / numPurchased) * 100
  if (percentageUsed >= 80)
    return 'error'
  if (percentageUsed >= 50)
    return 'warning'
  return 'success'
}

export function calculatePercentage(value: number | null | undefined, total: number | null | undefined): number {
  const numValue = value ?? 0
  const numTotal = total ?? 0
  if (numTotal <= 0)
    return 0
  const percentage = Math.round((numValue / numTotal) * 100)
  return Math.max(0, Math.min(100, percentage))
}
