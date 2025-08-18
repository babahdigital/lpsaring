import { differenceInHours, differenceInMinutes, parseISO } from 'date-fns'

/**
 * Mengubah ISO-8601 string → label relatif “5 menit”, “10 menit”, “1 jam”, dst.
 * Aturan:
 *  •  <5 menit  → "baru saja"
 *  •  5-9 menit → "5 menit lalu"
 *  • 10-59 menit→ "10 menit lalu"
 *  •  ≥60 menit → dibulatkan ke jam terdekat, ex: "1 jam lalu", "2 jam lalu", ...
 */
export function relativeLabel(isoUtcOrLocal: string): string {
  const dateObj = parseISO(isoUtcOrLocal)
  const now = new Date()
  const diffMins = differenceInMinutes(now, dateObj)

  /* < 5 menit  */
  if (diffMins < 5)
    return 'baru saja'

  /* 5-9 menit  */
  if (diffMins < 10)
    return '5 menit lalu'

  /* 10-59 menit */
  if (diffMins < 60)
    return '10 menit lalu'

  /* ≥ 1 jam     */
  const diffHours = differenceInHours(now, dateObj)
  return `${diffHours} jam lalu`
}
