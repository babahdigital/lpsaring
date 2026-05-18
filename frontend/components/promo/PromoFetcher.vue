<script setup lang="ts">
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

// Sprint 17 BUG-F1: Pindah dari cookie ke localStorage. Sebelumnya cookie
// `seen_promos` dengan maxAge=1 tahun + dikirim di SETIAP request → header
// bloat (200+ UUID entries ~9 KB) bisa hit `large_client_header_buffers`
// nginx default (8 KB per line) → 400 Bad Request. Plus prune entry yang
// tidak ada di promos aktif lagi.
const SEEN_PROMOS_KEY = 'lpsaring:seen_promos'

function readSeenPromos(): Record<string, boolean> {
  if (!import.meta.client || typeof localStorage === 'undefined')
    return {}
  try {
    const raw = localStorage.getItem(SEEN_PROMOS_KEY)
    if (!raw)
      return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  }
  catch {
    return {}
  }
}

function writeSeenPromos(value: Record<string, boolean>): void {
  if (!import.meta.client || typeof localStorage === 'undefined')
    return
  try {
    localStorage.setItem(SEEN_PROMOS_KEY, JSON.stringify(value))
  }
  catch {
    // localStorage quota exceeded — silently ignore.
  }
}

async function fetchAndShowPromo() {
  if (promoStore.isPromoDialogVisible)
    return

  try {
    const allActivePromos = await $api<PromoEvent[]>('/public/promos/active')

    if (!allActivePromos || allActivePromos.length === 0)
      return

    const seenMap = readSeenPromos()

    // Prune: keep hanya entry yang masih ada di promo aktif. Cegah unbounded
    // growth (promo ARCHIVED/EXPIRED akan dibersihkan dari local storage).
    const activeIds = new Set(allActivePromos.map(p => p.id))
    const prunedMap: Record<string, boolean> = {}
    for (const id of Object.keys(seenMap)) {
      if (activeIds.has(id))
        prunedMap[id] = true
    }

    const unseenPromos = allActivePromos.filter(p => !prunedMap[p.id])

    if (unseenPromos.length === 0) {
      writeSeenPromos(prunedMap)
      return
    }

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
      prunedMap[promoToShow.id] = true
      writeSeenPromos(prunedMap)
      promoStore.setActivePromo(promoToShow)
      promoStore.showPromoDialog()
    }
    else {
      writeSeenPromos(prunedMap)
    }
  }
  catch (e) {
    console.error('[PromoFetcher] Gagal mengambil promo aktif:', e)
  }
}

onMounted(() => {
  // Sprint 17: `import.meta.client` (Nuxt 4 standard) bukan `process.client`
  // legacy Nuxt 2 yang deprecated.
  if (import.meta.client)
    setTimeout(fetchAndShowPromo, 1500)
})
</script>

<template>
  <div>
    <RegistrationBonusDialog />
    <GeneralAnnouncementDialog />
  </div>
</template>
