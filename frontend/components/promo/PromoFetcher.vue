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
  if (promoStore.isPromoDialogVisible)
    return

  try {
    const allActivePromos = await $api<PromoEvent[]>('/public/promos/active')

    if (!allActivePromos || allActivePromos.length === 0)
      return

    const unseenPromos = allActivePromos.filter(p => !seenPromos.value[p.id])

    if (unseenPromos.length === 0)
      return

    let promoToShow: PromoEvent | null = null
    const bonusPromo = unseenPromos.find(p => p.event_type === 'BONUS_REGISTRATION')

    if (bonusPromo) {
      promoToShow = bonusPromo
    }
    else {
      const announcementPromo = unseenPromos.find(p => p.event_type === 'GENERAL_ANNOUNCEMENT')
      if (announcementPromo)
        promoToShow = announcementPromo
    }

    if (promoToShow) {
      seenPromos.value = { ...seenPromos.value, [promoToShow.id]: true }
      promoStore.setActivePromo(promoToShow)
      promoStore.showPromoDialog()
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
