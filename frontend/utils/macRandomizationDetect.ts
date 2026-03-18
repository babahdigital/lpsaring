/**
 * MAC Randomization Detection Utility
 *
 * Detects if device MAC address is randomized (Locally Administered Address — LAA bit set).
 * iOS 14+, Android 10+ support MAC randomization per-SSID connection.
 *
 * Reference: RFC 7042 — LAA bit is bit 1 of first octet (U/L bit).
 */

/**
 * Check if MAC address appears to be randomized (LAA — Locally Administered Address).
 *
 * MAC format: XX:YY:ZZ:AA:BB:CC
 * LAA detection: If (XX & 0x02) != 0, then address is locally administered (randomized).
 *
 * @param macAddress Normalized MAC (XX:XX:XX:XX:XX:XX or XXXXXXXXXXXX)
 * @returns true if appears randomized, false if universal/OUI-based
 */
export function isMacAddressRandomized(macAddress: string | null | undefined): boolean {
  if (!macAddress)
    return false

  // Clean input: support both colon-separated and dash-separated formats
  const cleaned = String(macAddress).trim().toLowerCase().replace(/[-:]/g, '')

  // Must be valid 48-bit MAC (12 hex chars)
  if (!/^[0-9a-f]{12}$/.test(cleaned))
    return false

  // Get first octet
  const firstOctetHex = cleaned.substring(0, 2)
  const firstOctetByte = parseInt(firstOctetHex, 16)

  // LAA bit is bit 1 (counting from LSB as bit 0)
  // I/G bit is bit 0 (Individual/Group)
  // U/L bit is bit 1 (Universal/Local)
  // If bit 1 = 1, it's a locally administered address
  const lsaBit = (firstOctetByte & 0x02) >> 1

  return lsaBit === 1
}

/**
 * Get human-readable description of MAC status.
 */
export function describeMacStatus(macAddress: string | null | undefined): string {
  if (!macAddress)
    return 'Alamat MAC tidak tersedia'

  if (isMacAddressRandomized(macAddress))
    return 'Alamat MAC tampak di-randomisasi (LAA). Matikan "Private Address" di WiFi settings untuk koneksi stabil.'

  return 'Alamat MAC Normal (OUI-based)'
}

/**
 * Get appropriate warning level for MAC randomization.
 */
export function getMacRandomizationWarningLevel(macAddress: string | null | undefined): 'none' | 'warning' | 'critical' {
  if (!macAddress)
    return 'none'

  if (isMacAddressRandomized(macAddress))
    return 'warning'

  return 'none'
}

export interface MacRandomizationAnalysis {
  isRandomized: boolean
  description: string
  warningLevel: 'none' | 'warning' | 'critical'
  recommendation: string
}

/**
 * Full analysis of MAC address randomization status.
 */
export function analyzeMacRandomization(macAddress: string | null | undefined): MacRandomizationAnalysis {
  const isRandomized = isMacAddressRandomized(macAddress)
  const warningLevel = getMacRandomizationWarningLevel(macAddress)

  let recommendation = ''
  if (isRandomized) {
    recommendation = `
Device Anda menggunakan "Private Address" (MAC randomization).
Ini dapat menyebabkan:
- Portal login diminta berulang kali
- Koneksi terputus dan masuk kembali
- Device tidak terdeteksi dengan baik

Solusi:
1. Buka WiFi Settings
2. Pilih jaringan "ikhlas"
3. Matikan "Private Address" atau "Random MAC"
4. Login kembali

Catatan: Matikan hanya untuk jaringan hotspot ini, bukan semua WiFi.
    `.trim()
  }

  return {
    isRandomized,
    description: describeMacStatus(macAddress),
    warningLevel,
    recommendation,
  }
}
