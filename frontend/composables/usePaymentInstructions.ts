import type { ComputedRef } from 'vue'
import { computed } from 'vue'

interface UsePaymentInstructionsOptions {
  paymentMethod: ComputedRef<string | null>
  deeplinkAppName: ComputedRef<string | null>
}

export function usePaymentInstructions(options: UsePaymentInstructionsOptions) {
  const { paymentMethod, deeplinkAppName } = options

  const vaInstructionTitle = computed(() => {
    const pm = paymentMethod.value?.toLowerCase() ?? ''
    if (pm.includes('bca'))
      return 'Cara bayar VA BCA'
    if (pm.includes('bni'))
      return 'Cara bayar VA BNI'
    if (pm.includes('bri'))
      return 'Cara bayar VA BRI'
    if (pm.includes('permata'))
      return 'Cara bayar VA Permata'
    if (pm.includes('cimb'))
      return 'Cara bayar VA CIMB'
    return 'Cara bayar Virtual Account'
  })

  const vaInstructions = computed(() => {
    return [
      'Buka aplikasi mobile banking / internet banking / ATM bank Anda.',
      'Pilih menu Transfer → Virtual Account.',
      'Masukkan nomor Virtual Account di atas, lalu konfirmasi pembayaran.',
      'Kembali ke halaman ini dan klik “Cek Status Pembayaran”.',
    ]
  })

  const qrisInstructions = computed(() => {
    return [
      'Buka aplikasi pembayaran (BCA, Mandiri, GoPay, OVO, dll).',
      'Pilih menu Scan QR.',
      'Pindai QR Code di atas atau download QR lalu unggah dari galeri Anda.',
      'Periksa detail pembayaran dan konfirmasi.',
    ]
  })

  const appDeeplinkInstructions = computed(() => {
    const appName = deeplinkAppName.value
    if (appName === 'GoPay') {
      return [
        'Klik tombol "Buka Aplikasi GoPay" di bawah.',
        'Aplikasi Gojek/GoPay akan terbuka otomatis (jika tersedia di perangkat Anda).',
        'Periksa nominal tagihan dan klik konfirmasi bayar.',
        'Masukkan PIN GoPay Anda untuk menyelesaikan transaksi.',
      ]
    }

    if (appName === 'ShopeePay') {
      return [
        'Klik tombol "Buka ShopeePay" di bawah.',
        'Aplikasi Shopee akan terbuka otomatis (jika tersedia di perangkat Anda).',
        'Buka menu ShopeePay dan konfirmasi pembayaran.',
        'Masukkan PIN ShopeePay Anda untuk menyelesaikan transaksi.',
      ]
    }

    return []
  })

  return {
    vaInstructionTitle,
    vaInstructions,
    qrisInstructions,
    appDeeplinkInstructions,
  }
}
