<script setup lang="ts">
import { useCookie } from '#app'
import { onMounted } from 'vue'
import { usePromoStore } from '~/store/promo'
import GeneralAnnouncementDialog from './GeneralAnnouncementDialog.vue'
import RegistrationBonusDialog from './RegistrationBonusDialog.vue'

// Definisikan tipe data PromoEvent
interface PromoEvent {
  id: string
  name: string
  description?: string
  event_type: 'BONUS_REGISTRATION' | 'GENERAL_ANNOUNCEMENT'
  status: 'ACTIVE'
  start_date: string
  end_date?: string
  bonus_value_mb?: number
  bonus_duration_days?: number
}

const { $api } = useNuxtApp()
const promoStore = usePromoStore()

const seenPromos = useCookie<Record<string, boolean>>('seen_promos', {
  default: () => ({}),
  maxAge: 60 * 60 * 24 * 365,
})

async function fetchAndShowPromo() {
  console.log('[PromoFetcher] Memulai pengecekan promo...')

  if (promoStore.isPromoDialogVisible) {
    console.log('[PromoFetcher] Pengecekan dibatalkan, dialog lain sudah aktif.')
    return
  }

  try {
    const allActivePromos = await $api<PromoEvent[]>('/public/promos/active')
    console.log('[PromoFetcher] Data promo aktif dari API:', allActivePromos)

    if (!allActivePromos || allActivePromos.length === 0) {
      console.log('[PromoFetcher] Tidak ada promo aktif dari API. Selesai.')
      return
    }

    const unseenPromos = allActivePromos.filter(p => !seenPromos.value[p.id])
    console.log('[PromoFetcher] Promo yang belum pernah dilihat:', unseenPromos)
    console.log('[PromoFetcher] Cookie "seen_promos" saat ini:', seenPromos.value)

    if (unseenPromos.length === 0) {
      console.log('[PromoFetcher] Semua promo aktif sudah pernah dilihat. Selesai.')
      return
    }

    let promoToShow: PromoEvent | null = null
    const bonusPromo = unseenPromos.find(p => p.event_type === 'BONUS_REGISTRATION')
    console.log('[PromoFetcher] Mencari promo bonus:', bonusPromo)

    if (bonusPromo) {
      promoToShow = bonusPromo
    }
    else {
      const announcementPromo = unseenPromos.find(p => p.event_type === 'GENERAL_ANNOUNCEMENT')
      console.log('[PromoFetcher] Mencari promo pengumuman:', announcementPromo)
      if (announcementPromo) {
        promoToShow = announcementPromo
      }
    }

    console.log('[PromoFetcher] Promo yang akan ditampilkan sebagai popup:', promoToShow)

    if (promoToShow) {
      console.log(`[PromoFetcher] Menampilkan popup untuk promo ID: ${promoToShow.id}`)
      seenPromos.value = { ...seenPromos.value, [promoToShow.id]: true }
      promoStore.setActivePromo(promoToShow)
      promoStore.showPromoDialog()
    }
    else {
      console.log('[PromoFetcher] Tidak ada promo yang memenuhi syarat untuk ditampilkan sebagai popup.')
    }
  }
  catch (e) {
    console.error('[PromoFetcher] Gagal mengambil promo aktif:', e)
  }
}

onMounted(() => {
  if (process.client) {
    setTimeout(fetchAndShowPromo, 1500)
  }
})
</script>

<template>
  <div>
    <RegistrationBonusDialog />
    <GeneralAnnouncementDialog />
  </div>
</template>
