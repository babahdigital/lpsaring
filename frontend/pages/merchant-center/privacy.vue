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

useHead({ title: `Privacy Policy - Merchant Center ${merchantName.value}` })
</script>

<template>
  <div class="merchant-doc-page">
    <VContainer class="py-6 py-md-10" style="max-inline-size: 980px;">
      <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-5">
        <div>
          <p class="text-overline mb-1">Merchant Center</p>
          <h1 class="text-h4 font-weight-bold mb-0">Privacy Policy</h1>
        </div>
        <div class="d-flex flex-wrap ga-2">
          <VBtn variant="text" to="/merchant-center">Kembali</VBtn>
          <VBtn variant="tonal" color="primary" to="/merchant-center/terms">Terms of Service</VBtn>
        </div>
      </div>

      <VCard rounded="xl">
        <VCardText class="pa-6 pa-md-8 text-body-1">
          <p>
            {{ merchantName }} menghargai privasi pelanggan. Kebijakan ini menjelaskan bagaimana data pelanggan
            dikumpulkan, digunakan, dan dilindungi dalam layanan hotspot dan pembayaran digital.
          </p>

          <h2 class="text-h6 mt-6 mb-2">1. Data yang Dikumpulkan</h2>
          <ul class="pl-6">
            <li>Data identitas akun: nama, nomor HP, dan informasi profil pengguna.</li>
            <li>Data transaksi: paket yang dipilih, nominal pembayaran, status transaksi, dan waktu transaksi.</li>
            <li>Data operasional layanan: log OTP/auth, data perangkat, client IP/MAC, dan metadata teknis untuk keamanan layanan.</li>
          </ul>

          <h2 class="text-h6 mt-6 mb-2">2. Tujuan Penggunaan Data</h2>
          <ul class="pl-6">
            <li>Memberikan akses layanan internet sesuai paket yang dibeli.</li>
            <li>Memproses pembayaran melalui payment gateway resmi.</li>
            <li>Menyediakan halaman status pembayaran dan notifikasi transaksi kepada pelanggan.</li>
            <li>Mengelola dukungan pelanggan, audit transaksi, dan pencegahan penyalahgunaan layanan.</li>
          </ul>

          <h2 class="text-h6 mt-6 mb-2">3. Pembagian Data</h2>
          <p>
            Data pelanggan tidak diperjualbelikan. Data hanya dibagikan kepada mitra pemrosesan yang diperlukan
            (misalnya payment gateway/infrastruktur), atau kepada pihak berwenang sesuai ketentuan hukum.
          </p>

          <h2 class="text-h6 mt-6 mb-2">4. Keamanan Data</h2>
          <p>
            Sistem menggunakan kontrol akses internal, pencatatan aktivitas, dan komunikasi terenkripsi (HTTPS)
            untuk menjaga kerahasiaan serta integritas data.
          </p>

          <h2 class="text-h6 mt-6 mb-2">5. Hak Pengguna</h2>
          <p>
            Pengguna dapat mengajukan koreksi data atau pertanyaan terkait penggunaan data melalui kanal customer support resmi.
          </p>

          <h2 class="text-h6 mt-6 mb-2">6. Kontak Privasi</h2>
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
