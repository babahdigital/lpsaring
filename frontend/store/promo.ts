// store/promo.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

// Definisikan tipe data PromoEvent agar konsisten
interface PromoEvent {
  id: string
  name: string
  description?: string
  event_type: 'BONUS_REGISTRATION' | 'GENERAL_ANNOUNCEMENT'
  status: 'DRAFT' | 'ACTIVE' | 'SCHEDULED' | 'EXPIRED' | 'ARCHIVED'
  start_date: string
  end_date?: string
  bonus_value_mb?: number
  bonus_duration_days?: number
}

export const usePromoStore = defineStore('promo', () => {
  // --- STATE ---
  const activePromo = ref<PromoEvent | null>(null)
  const isPromoDialogVisible = ref(false)

  // --- ACTIONS ---

  /**
   * Mengatur promo yang akan ditampilkan di dialog.
   * @param promo - Objek promo dari API.
   */
  function setActivePromo(promo: PromoEvent) {
    activePromo.value = promo
  }

  /**
   * Menampilkan dialog promo.
   */
  function showPromoDialog() {
    if (activePromo.value) {
      isPromoDialogVisible.value = true
    }
  }

  /**
   * Menyembunyikan dan mereset dialog promo.
   */
  function hidePromoDialog() {
    isPromoDialogVisible.value = false
    // Beri sedikit delay agar transisi penutupan dialog selesai
    setTimeout(() => {
      activePromo.value = null
    }, 300)
  }

  /**
   * Mereset state promo, biasanya saat navigasi halaman.
   */
  function resetPromo() {
    activePromo.value = null
    isPromoDialogVisible.value = false
  }

  // --- RETURN ---
  return {
    activePromo,
    isPromoDialogVisible,
    setActivePromo,
    showPromoDialog,
    hidePromoDialog,
    resetPromo,
  }
})
