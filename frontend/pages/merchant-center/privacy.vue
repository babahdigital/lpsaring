<script setup lang="ts">
const {
  merchantName,
  merchantAddress,
  supportEmail,
  supportWhatsAppFormatted,
  supportWhatsAppHref,
} = useMerchantProfile()
const route = useRoute()
const referrerBackPath = ref<string | null>(null)

const sourceFromQuery = computed(() => {
  const raw = route.query.from
  return typeof raw === 'string' ? raw.trim().toLowerCase() : ''
})

const backPath = computed(() => {
  if (sourceFromQuery.value === 'beli')
    return '/beli'
  if (sourceFromQuery.value === 'dashboard')
    return '/dashboard'
  if (sourceFromQuery.value === 'merchant')
    return '/merchant-center'
  return referrerBackPath.value ?? '/merchant-center'
})

const legalSource = computed(() => {
  if (sourceFromQuery.value === 'beli' || sourceFromQuery.value === 'dashboard' || sourceFromQuery.value === 'merchant')
    return sourceFromQuery.value

  if (backPath.value.startsWith('/dashboard'))
    return 'dashboard'
  if (backPath.value.startsWith('/beli') || backPath.value.startsWith('/captive/beli'))
    return 'beli'
  return 'merchant'
})

onMounted(() => {
  if (!import.meta.client || document.referrer === '')
    return

  try {
    const pathname = new URL(document.referrer).pathname

    if (pathname.startsWith('/dashboard')) {
      referrerBackPath.value = '/dashboard'
      return
    }

    if (pathname.startsWith('/beli') || pathname.startsWith('/captive/beli')) {
      referrerBackPath.value = '/beli'
      return
    }

    if (pathname.startsWith('/merchant-center'))
      referrerBackPath.value = '/merchant-center'
  }
  catch {
    referrerBackPath.value = null
  }
})

definePageMeta({
  layout: 'blank',
  public: true,
})

useHead({ title: `Privacy Policy - Merchant Center ${merchantName.value}` })
</script>

<template>
  <div class="merchant-doc-page">
    <VContainer class="py-4 py-sm-6 py-md-10" style="max-inline-size: 980px;">
      <VCard class="doc-header mb-6" rounded="xl" variant="outlined">
        <VCardText class="pa-5 pa-sm-6">
          <div class="d-flex flex-column flex-sm-row align-start align-sm-center justify-space-between ga-4">
            <div>
              <p class="doc-overline mb-1">Dokumen Legal</p>
              <h1 class="text-h5 text-sm-h4 font-weight-bold text-white mb-0">Privacy Policy</h1>
            </div>
            <div class="doc-actions">
              <VBtn class="doc-action-btn" variant="tonal" color="secondary" :to="backPath">Kembali</VBtn>
              <VBtn class="doc-action-btn" variant="flat" color="primary" :to="{ path: '/merchant-center/terms', query: { from: legalSource } }">Terms Of Service</VBtn>
            </div>
          </div>
        </VCardText>
      </VCard>

      <VCard class="doc-card" rounded="xl" variant="outlined">
        <VCardText class="pa-6 pa-sm-8 pa-md-10">
          <p class="doc-intro">
            {{ merchantName }} menghargai privasi pelanggan. Kebijakan ini menjelaskan bagaimana data pelanggan
            dikumpulkan, digunakan, dan dilindungi dalam layanan hotspot dan pembayaran digital.
          </p>

          <section class="doc-section">
            <h2 class="doc-title">1. Data yang Dikumpulkan</h2>
            <ul class="doc-list">
              <li>Data identitas akun: nama, nomor HP, dan informasi profil pengguna.</li>
              <li>Data transaksi: paket yang dipilih, nominal pembayaran, status transaksi, dan waktu transaksi.</li>
              <li>Data operasional layanan: log OTP/auth, data perangkat, client IP/MAC, dan metadata teknis untuk keamanan layanan.</li>
            </ul>
          </section>

          <section class="doc-section">
            <h2 class="doc-title">2. Tujuan Penggunaan Data</h2>
            <ul class="doc-list">
              <li>Memberikan akses layanan internet sesuai paket yang dibeli.</li>
              <li>Memproses pembayaran melalui payment gateway resmi.</li>
              <li>Menyediakan halaman status pembayaran dan notifikasi transaksi kepada pelanggan.</li>
              <li>Mengelola dukungan pelanggan, audit transaksi, dan pencegahan penyalahgunaan layanan.</li>
            </ul>
          </section>

          <section class="doc-section">
            <h2 class="doc-title">3. Pembagian Data</h2>
            <p class="doc-paragraph">
              Data pelanggan tidak diperjualbelikan. Data hanya dibagikan kepada mitra pemrosesan yang diperlukan
              (misalnya payment gateway/infrastruktur), atau kepada pihak berwenang sesuai ketentuan hukum.
            </p>
          </section>

          <section class="doc-section">
            <h2 class="doc-title">4. Keamanan Data</h2>
            <p class="doc-paragraph">
              Sistem menggunakan kontrol akses internal, pencatatan aktivitas, dan komunikasi terenkripsi (HTTPS)
              untuk menjaga kerahasiaan serta integritas data.
            </p>
          </section>

          <section class="doc-section">
            <h2 class="doc-title">5. Hak Pengguna</h2>
            <p class="doc-paragraph">
              Pengguna dapat mengajukan koreksi data atau pertanyaan terkait penggunaan data melalui kanal customer support resmi.
            </p>
          </section>

          <section class="doc-section">
            <h2 class="doc-title">6. Kontak Privasi</h2>
            <ul class="doc-list">
              <li>
                Email CS: 
                <a v-if="supportEmail" class="doc-link" :href="`mailto:${supportEmail}`">{{ supportEmail }}</a>
                <span v-else>-</span>
              </li>
              <li>
                WhatsApp CS: 
                <a v-if="supportWhatsAppHref" class="doc-link" :href="supportWhatsAppHref" target="_blank" rel="noopener noreferrer">
                  {{ supportWhatsAppFormatted }}
                </a>
                <span v-else>-</span>
              </li>
              <li>Alamat Merchant: {{ merchantAddress || '-' }}</li>
            </ul>
          </section>

          <p class="doc-updated mb-0">
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

.doc-header,
.doc-card {
  background-color: rgba(var(--v-theme-surface), 1);
  border-color: rgba(var(--v-border-color), 0.28) !important;
  box-shadow: 0 4px 14px rgba(15, 20, 34, 0.14);
}

.doc-overline {
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.doc-actions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  inline-size: 100%;
}

.doc-action-btn {
  inline-size: 100%;
}

.doc-intro {
  color: rgba(var(--v-theme-on-surface), 0.9);
  font-size: clamp(1rem, 2.6vw, 1.08rem);
  line-height: 1.7;
  font-weight: 500;
  margin-block-end: 1.5rem;
}

.doc-section {
  margin-block-start: 1.35rem;
}

.doc-title {
  color: rgb(var(--v-theme-on-surface));
  font-size: clamp(1.04rem, 2.8vw, 1.24rem);
  font-weight: 800;
  line-height: 1.4;
  margin-block-end: 0.85rem;
  padding-block-end: 0.65rem;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.22);
}

.doc-list {
  list-style: none;
  padding-inline-start: 0;
  margin: 0;
  display: grid;
  gap: 0.75rem;
}

.doc-list li {
  position: relative;
  color: rgba(var(--v-theme-on-surface), 0.86);
  line-height: 1.68;
  padding-inline-start: 1rem;
  word-break: break-word;
}

.doc-list li::before {
  content: '';
  position: absolute;
  inset-inline-start: 0;
  inset-block-start: 0.6rem;
  inline-size: 0.32rem;
  block-size: 0.32rem;
  border-radius: 999px;
  background: rgb(var(--v-theme-primary));
}

.doc-paragraph {
  color: rgba(var(--v-theme-on-surface), 0.86);
  line-height: 1.72;
  margin: 0;
}

.doc-link {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  font-weight: 600;

  &:hover {
    text-decoration: underline;
  }
}

.doc-updated {
  margin-block-start: 2rem;
  padding-block-start: 1.3rem;
  border-top: 1px solid rgba(var(--v-border-color), 0.24);
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.8rem;
  font-weight: 600;
}

@media (min-width: 600px) {
  .doc-actions {
    inline-size: auto;
    flex-direction: row;
    align-items: center;
  }

  .doc-action-btn {
    inline-size: auto;
    min-inline-size: 10.75rem;
  }
}
</style>
