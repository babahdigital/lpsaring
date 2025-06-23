// store/promo.ts
import { defineStore } from 'pinia'

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

export const usePromoStore = defineStore('promo', {
  state: () => ({
    activePromo: null as PromoEvent | null,
    isPromoDialogVisible: false,
  }),
  actions: {
    /**
     * Mengatur promo yang akan ditampilkan di dialog.
     * @param promo - Objek promo dari API.
     */
    setActivePromo(promo: PromoEvent) {
      this.activePromo = promo
    },

    /**
     * Menampilkan dialog promo.
     */
    showPromoDialog() {
      if (this.activePromo) {
        this.isPromoDialogVisible = true
      }
    },

    /**
     * Menyembunyikan dan mereset dialog promo.
     */
    hidePromoDialog() {
      this.isPromoDialogVisible = false
      // Beri sedikit delay agar transisi penutupan dialog selesai
      setTimeout(() => {
        this.activePromo = null
      }, 300)
    },

    /**
     * Mereset state promo, biasanya saat navigasi halaman.
     */
    resetPromo() {
      this.activePromo = null
      this.isPromoDialogVisible = false
    },
  },
})
