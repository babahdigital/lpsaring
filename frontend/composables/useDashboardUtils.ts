// /composables/useDashboardUtils.ts

export function useDashboardUtils() {
  const formatCurrency = (value: number): string => {
    if (typeof value !== 'number')
      return ''
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value)
  }

  const formatBytes = (megabytes: number, decimals = 1) => {
    if (typeof megabytes !== 'number' || isNaN(megabytes) || megabytes === 0)
      return '0 MB'
    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['MB', 'GB', 'TB', 'PB']

    let size = megabytes
    let i = 0

    while (size >= k && i < sizes.length - 1) {
      size /= k
      i++
    }

    return `${Number.parseFloat(size.toFixed(dm))} ${sizes[i]}`
  }

  const formatRelativeTime = (dateString: string): string => {
    if (!dateString)
      return ''
    const date = new Date(dateString)
    const now = new Date()
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)
    if (seconds < 60)
      return 'Baru saja'
    const intervals = [
      { unit: 'tahun', secondsInUnit: 31536000 },
      { unit: 'bulan', secondsInUnit: 2592000 },
      { unit: 'hari', secondsInUnit: 86400 },
      { unit: 'jam', secondsInUnit: 3600 },
      { unit: 'menit', secondsInUnit: 60 },
    ]
    for (const { unit, secondsInUnit } of intervals) {
      const interval = seconds / secondsInUnit
      if (interval > 1)
        return `${Math.floor(interval)} ${unit} lalu`
    }
    return 'Baru saja'
  }

  const formatPhoneNumberForDisplay = (phoneNumber?: string | null) => {
    if (!phoneNumber)
      return 'No. Telp tidak ada'
    if (phoneNumber.startsWith('+62')) {
      const localNumber = `0${phoneNumber.substring(3)}`
      return localNumber.length > 8
        ? `${localNumber.substring(0, 4)}-xxxx-${localNumber.substring(localNumber.length - 4)}`
        : localNumber
    }
    return phoneNumber
  }

  const getUserInitials = (name?: string) => {
    if (!name || name.trim() === '')
      return 'N/A'
    const words = name.split(' ').filter(Boolean)
    if (words.length >= 2)
      return (words[0]![0]! + words[1]![0]!).toUpperCase()
    if (words.length === 1 && words[0]!.length > 1)
      return words[0]![0]!.toUpperCase()
    return name.substring(0, 1).toUpperCase()
  }

  return {
    formatCurrency,
    formatBytes,
    formatRelativeTime,
    formatPhoneNumberForDisplay,
    getUserInitials,
  }
}
