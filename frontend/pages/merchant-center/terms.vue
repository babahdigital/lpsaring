<script setup lang="ts">
const {
  merchantName,
  merchantAddress,
  supportEmail,
  supportWhatsAppFormatted,
  supportWhatsAppHref,
} = useMerchantProfile()

definePageMeta({
  layout: 'blank',
  public: true,
})

useHead({ title: `Terms of Service - Merchant Center ${merchantName.value}` })
</script>

<template>
  <div class="merchant-doc-page">
    <VContainer class="py-6 py-md-10" style="max-inline-size: 980px;">
      <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-5">
        <div>
          <p class="text-overline mb-1">Merchant Center</p>
          <h1 class="text-h4 font-weight-bold mb-0">Terms of Service</h1>
        </div>
        <div class="d-flex flex-wrap ga-2">
          <VBtn variant="text" to="/merchant-center">Kembali</VBtn>
          <VBtn variant="tonal" color="primary" to="/merchant-center/privacy">Privacy Policy</VBtn>
        </div>
      </div>

      <VCard rounded="xl">
        <VCardText class="pa-6 pa-md-8 text-body-1">
          <p>
            Dengan menggunakan layanan {{ merchantName }}, pengguna menyetujui syarat dan ketentuan berikut.
          </p>

          <h2 class="text-h6 mt-6 mb-2">1. Produk dan Harga</h2>
          <ul class="pl-6">
            <li>Produk yang dijual berupa layanan digital (voucher/paket internet).</li>
            <li>Semua harga menggunakan mata uang Rupiah (IDR).</li>
            <li>Total biaya yang ditampilkan di checkout bersifat transparan sesuai komponen biaya sistem.</li>
          </ul>

          <h2 class="text-h6 mt-6 mb-2">2. Delivery Policy</h2>
          <p>
            Aktivasi paket dilakukan secara digital dan otomatis setelah pembayaran terkonfirmasi berhasil.
            Status pembayaran dapat dipantau melalui halaman status transaksi yang disediakan sistem.
          </p>

          <h2 class="text-h6 mt-6 mb-2">3. Billing dan Pengiriman</h2>
          <p>
            Karena produk bersifat digital, tidak ada pengiriman fisik maupun ongkos kirim. Sistem menyimpan data billing
            untuk keperluan transaksi dan layanan pelanggan.
          </p>

          <h2 class="text-h6 mt-6 mb-2">4. Refund Policy</h2>
          <p>
            Pembelian produk digital pada prinsipnya tidak dapat dibatalkan atau diuangkan kembali.
            Pengembalian dana dapat diproses untuk kasus tertentu, misalnya pembayaran sukses namun layanan tidak terprovisioning
            akibat gangguan sistem setelah proses verifikasi internal.
          </p>

          <h2 class="text-h6 mt-6 mb-2">5. Penggunaan yang Diperbolehkan</h2>
          <p>
            Pengguna wajib menggunakan layanan secara sah, tidak melanggar hukum, dan tidak menyalahgunakan sistem.
          </p>

          <h2 class="text-h6 mt-6 mb-2">6. Kontak Merchant</h2>
          <ul class="pl-6">
            <li>
              Email CS: 
              <a v-if="supportEmail" :href="`mailto:${supportEmail}`">{{ supportEmail }}</a>
              <span v-else>-</span>
            </li>
            <li>
              WhatsApp CS: 
              <a v-if="supportWhatsAppHref" :href="supportWhatsAppHref" target="_blank" rel="noopener noreferrer">
                {{ supportWhatsAppFormatted }}
              </a>
              <span v-else>-</span>
            </li>
            <li>Alamat Merchant: {{ merchantAddress || '-' }}</li>
          </ul>

          <h2 class="text-h6 mt-6 mb-2">7. Perubahan Ketentuan</h2>
          <p>
            Syarat layanan dapat diperbarui sewaktu-waktu. Perubahan berlaku sejak dipublikasikan di halaman ini.
          </p>

          <p class="text-medium-emphasis mt-8 mb-0">
            Terakhir diperbarui: 25 Februari 2026
          </p>
        </VCardText>
      </VCard>
    </VContainer>
  </div>
</template>

<style scoped lang="scss">
.merchant-doc-page {
  min-block-size: 100vh;
  background: rgb(var(--v-theme-background));
}
</style>
