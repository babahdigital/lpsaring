<script setup lang="ts">
import { watch } from 'vue'
import { useSnackbar } from '@/composables/useSnackbar'
import type { MikrotikVerifyRulesResponseContract } from '@/types/api/contracts'

definePageMeta({
  requiredRole: ['ADMIN', 'SUPER_ADMIN'],
})

useHead({ title: 'Verifikasi MikroTik — Admin' })

const { $api } = useNuxtApp()
const { add: showSnackbar } = useSnackbar()

const {
  data,
  pending,
  error,
  refresh,
} = useFetch<MikrotikVerifyRulesResponseContract>('/admin/mikrotik/verify-rules', {
  lazy: true,
  server: false,
  $fetch: $api,
})

watch(error, (e) => {
  if (!e) return
  const msg = typeof (e as any)?.data?.message === 'string' && (e as any).data.message !== ''
    ? (e as any).data.message
    : 'Gagal mengambil data dari MikroTik. Pastikan koneksi router aktif.'
  showSnackbar({ type: 'error', title: 'Gagal Memuat Data', text: msg })
})

function overallColor(d: MikrotikVerifyRulesResponseContract | null): string {
  if (!d) return 'default'
  if (d.all_found && d.order_ok) return 'success'
  if (!d.all_found) return 'error'
  return 'warning'
}

function overallLabel(d: MikrotikVerifyRulesResponseContract | null): string {
  if (!d) return 'Belum diverifikasi'
  if (d.all_found && d.order_ok) return 'Semua Rule OK & Urutan Benar'
  if (!d.all_found) return 'Ada Rule yang Tidak Ditemukan'
  return 'Rule Ada, Urutan Perlu Dicek'
}
</script>

<template>
  <div>
    <!-- Page Header -->
    <VRow class="mb-2" align="center">
      <VCol cols="12" sm="8">
        <h3 class="text-h5 font-weight-bold">
          Verifikasi MikroTik
        </h3>
        <p class="text-body-2 text-disabled mt-1 mb-0">
          Periksa firewall rules kritis dan status konfigurasi router MikroTik.
        </p>
      </VCol>
      <VCol
        cols="12"
        sm="4"
        class="d-flex justify-start justify-sm-end"
      >
        <VBtn
          color="primary"
          prepend-icon="tabler-refresh"
          :loading="pending"
          @click="refresh()"
        >
          Verifikasi Ulang
        </VBtn>
      </VCol>
    </VRow>

    <VRow>
      <!-- Card 1: Verifikasi Firewall Rules -->
      <VCol
        cols="12"
        md="6"
      >
        <VCard height="100%">
          <VProgressLinear
            v-if="pending"
            indeterminate
            color="primary"
            height="3"
          />

          <VCardItem>
            <template #prepend>
              <VAvatar
                color="primary"
                variant="tonal"
                rounded
                size="40"
                class="me-2"
              >
                <VIcon
                  icon="tabler-shield-check"
                  size="22"
                />
              </VAvatar>
            </template>
            <VCardTitle class="text-body-1 font-weight-semibold">
              Verifikasi Firewall Rules
            </VCardTitle>
            <VCardSubtitle class="text-caption">
              Keberadaan & urutan forward chain rule aktif di MikroTik
            </VCardSubtitle>
          </VCardItem>

          <VCardText>
            <!-- Status setelah verifikasi -->
            <template v-if="data">
              <!-- Overall status chip -->
              <VChip
                :color="overallColor(data)"
                variant="tonal"
                label
                class="mb-3 font-weight-medium"
                size="small"
              >
                <VIcon
                  :icon="data.all_found && data.order_ok ? 'tabler-circle-check' : 'tabler-alert-triangle'"
                  start
                  size="16"
                />
                {{ overallLabel(data) }}
              </VChip>

              <!-- Detail chips -->
              <div class="d-flex flex-wrap ga-2 mb-4">
                <VChip
                  :color="data.all_found ? 'success' : 'error'"
                  variant="outlined"
                  label
                  size="x-small"
                >
                  all_found: {{ data.all_found ? 'Ya' : 'Tidak' }}
                </VChip>
                <VChip
                  :color="data.order_ok ? 'success' : 'warning'"
                  variant="outlined"
                  label
                  size="x-small"
                >
                  order_ok: {{ data.order_ok ? 'Ya' : 'Tidak' }}
                </VChip>
                <VChip
                  color="default"
                  variant="outlined"
                  label
                  size="x-small"
                >
                  Total forward rules: {{ data.total_forward_rules }}
                </VChip>
              </div>

              <!-- Tabel rules dengan overflow-x untuk mobile -->
              <div
                v-if="data.checks?.length"
                style="overflow-x: auto"
              >
                <VTable
                  density="compact"
                  style="min-width: 380px"
                >
                  <thead>
                    <tr>
                      <th class="text-left">
                        Rule
                      </th>
                      <th
                        class="text-center"
                        style="width: 90px"
                      >
                        Ditemukan
                      </th>
                      <th
                        class="text-center"
                        style="width: 70px"
                      >
                        Posisi
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(check, idx) in data.checks"
                      :key="idx"
                    >
                      <td class="text-caption py-2">
                        <code class="text-xs">{{ check.label }}</code>
                      </td>
                      <td class="text-center py-2">
                        <VChip
                          :color="check.found ? 'success' : 'error'"
                          size="x-small"
                          variant="tonal"
                          label
                        >
                          {{ check.found ? 'Ya' : 'Tidak' }}
                        </VChip>
                      </td>
                      <td class="text-center text-caption py-2">
                        {{ check.position >= 0 ? check.position : '—' }}
                      </td>
                    </tr>
                  </tbody>
                </VTable>
              </div>
            </template>

            <!-- Placeholder jika tidak ada data setelah load -->
            <div
              v-else-if="!pending"
              class="text-center py-8"
            >
              <VIcon
                icon="tabler-shield-off"
                size="40"
                class="mb-3 text-error"
              />
              <p class="text-body-2 text-medium-emphasis mb-2">
                Gagal mengambil data dari MikroTik.
              </p>
              <VBtn
                size="small"
                color="primary"
                variant="tonal"
                prepend-icon="tabler-refresh"
                @click="refresh()"
              >
                Coba Lagi
              </VBtn>
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <!-- Card 2: Panduan & Tentang -->
      <VCol
        cols="12"
        md="6"
      >
        <VCard height="100%">
          <VCardItem>
            <template #prepend>
              <VAvatar
                color="info"
                variant="tonal"
                rounded
                size="40"
                class="me-2"
              >
                <VIcon
                  icon="tabler-info-circle"
                  size="22"
                />
              </VAvatar>
            </template>
            <VCardTitle class="text-body-1 font-weight-semibold">
              Panduan Membaca Hasil
            </VCardTitle>
            <VCardSubtitle class="text-caption">
              Penjelasan status dan tindakan yang perlu dilakukan
            </VCardSubtitle>
          </VCardItem>

          <VCardText class="d-flex flex-column ga-3">
            <VAlert
              type="info"
              variant="tonal"
              density="compact"
              icon="tabler-eye"
            >
              <div class="text-caption font-weight-semibold mb-1">
                Apa yang diverifikasi?
              </div>
              <p class="text-caption mb-0">
                Endpoint ini memeriksa 4 <em>forward chain firewall rule</em> kritis:
                keberadaannya di router MikroTik dan apakah urutannya sudah benar
                sesuai kebijakan akses (klient_inactive → klient_aktif → klient_fup).
              </p>
            </VAlert>

            <VAlert
              type="success"
              variant="tonal"
              density="compact"
              icon="tabler-check"
            >
              <div class="text-caption font-weight-semibold mb-1">
                <code>skipped_not_allowed</code> — By Design
              </div>
              <p class="text-caption mb-0">
                Log <code>skipped_not_allowed</code> dari task sync unauthorized bukan bug.
                Host hotspot dengan IP di luar <code>MIKROTIK_UNAUTHORIZED_CIDRS</code>
                (default <code>172.16.2.0/23</code>) memang sengaja di-skip — subnet
                manajemen atau VLAN lain tidak dimonitor.
              </p>
            </VAlert>

            <VAlert
              type="warning"
              variant="tonal"
              density="compact"
              icon="tabler-alert-triangle"
            >
              <div class="text-caption font-weight-semibold mb-1">
                Kapan perlu tindakan?
              </div>
              <p class="text-caption mb-0">
                Jika <strong>all_found = Tidak</strong>: salah satu rule kritis hilang dari
                firewall MikroTik. Tambahkan rule yang hilang via Winbox / SSH sesuai
                panduan instalasi.
              </p>
              <p class="text-caption mt-1 mb-0">
                Jika <strong>order_ok = Tidak</strong> tapi all_found = Ya: reorder rules
                di MikroTik agar urutan prioritas akses sesuai.
              </p>
            </VAlert>

            <VAlert
              type="secondary"
              variant="tonal"
              density="compact"
              icon="tabler-clock"
            >
              <div class="text-caption font-weight-semibold mb-1">
                Kapan verifikasi ulang?
              </div>
              <p class="text-caption mb-0">
                Lakukan verifikasi setelah perubahan konfigurasi MikroTik, upgrade firmware
                router, atau jika ada laporan user tidak bisa akses internet meski status
                aktif di sistem.
              </p>
            </VAlert>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
