<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

interface Props {
  error?: Error | null
}

const props = withDefaults(defineProps<Props>(), {
  error: null,
})

const hasError = ref(false)
const isRetrying = ref(false)
const showDetails = ref(false)
// Variabel retryCount dipertahankan untuk potensi penggunaan di masa depan (misal: logging atau backoff)
const retryCount = ref(0)

const errorMessage = computed(() => {
  if (!props.error)
    return 'Terjadi kesalahan yang tidak terduga. Silakan coba lagi.'

  const message = props.error.message.toLowerCase()

  if (message.includes('failed to fetch dynamically imported module')) {
    return 'Gagal memuat beberapa komponen aplikasi. Masalah ini seringkali disebabkan oleh cache jaringan yang usang.'
  }
  if (message.includes('net::err_aborted') || message.includes('gateway timeout')) {
    return 'Koneksi ke server terputus. Mohon periksa koneksi internet atau hotspot Anda.'
  }
  if (message.includes('timeout')) {
    return 'Waktu koneksi habis. Server mungkin sedang sibuk atau koneksi Anda terlalu lambat.'
  }

  return 'Terjadi kesalahan yang tidak terduga. Tim kami telah diberitahu.'
})

async function handleRetry() {
  if (isRetrying.value)
    return

  isRetrying.value = true
  retryCount.value++

  // Memberi jeda visual sebelum reload untuk UX yang lebih baik
  await new Promise(resolve => setTimeout(resolve, 750))

  // Menggunakan window.location.reload() adalah cara paling andal untuk mengatasi chunk loading errors.
  window.location.reload()
}

function toggleDetails() {
  showDetails.value = !showDetails.value
}

// ---- Penanganan Error Global ----

// Daftar pesan error yang aman untuk diabaikan
const ignoredErrorMessages = [
  'resizeobserver loop limit exceeded',
  'loading css chunk',
  'favicon.png was preloaded',
  'cannot read properties of undefined (reading \'call\')',
  'patharray.parse',
]

// Fungsi untuk menangani error yang tidak tertangkap oleh promise
function handleUnhandledRejection(event: PromiseRejectionEvent) {
  const reason = event.reason
  if (!reason)
    return

  const message = (reason.message || '').toLowerCase()

  // Menangkap error spesifik terkait pemuatan modul/chunk
  if (message.includes('failed to fetch') || message.includes('loading chunk')) {
    console.error('Unhandled Rejection (Network/Chunk Error):', reason)
    hasError.value = true
    event.preventDefault()
  }
}

// Fungsi untuk menangani error global pada window
function handleGlobalError(event: ErrorEvent) {
  const error = event.error
  if (!error)
    return

  const message = (error.message || '').toLowerCase()

  // Jika pesan error termasuk dalam daftar yang diabaikan, hentikan eksekusi
  if (ignoredErrorMessages.some(ignoredMsg => message.includes(ignoredMsg))) {
    return
  }

  console.error('Global Error Captured:', error)
  hasError.value = true
}

watch(() => props.error, (newError) => {
  if (newError) {
    hasError.value = true
    console.error('Error Prop Captured:', newError)
  }
}, { immediate: true })

// Mendaftarkan dan membersihkan event listener sesuai siklus hidup komponen
onMounted(() => {
  if (import.meta.client) {
    window.addEventListener('unhandledrejection', handleUnhandledRejection)
    window.addEventListener('error', handleGlobalError)
  }
})

onUnmounted(() => {
  if (import.meta.client) {
    window.removeEventListener('unhandledrejection', handleUnhandledRejection)
    window.removeEventListener('error', handleGlobalError)
  }
})
</script>

<template>
  <div class="error-boundary-container">
    <Transition name="fade" appear>
      <div v-if="hasError" class="error-content-wrapper">
        <div class="error-card">
          <div class="error-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              <path d="M12 9v4" />
              <path d="M12 17h.01" />
            </svg>
          </div>
          <h3>Aplikasi Mengalami Kendala</h3>
          <p>{{ errorMessage }}</p>

          <div class="error-actions">
            <button class="action-btn primary" :disabled="isRetrying" @click="handleRetry">
              <span v-if="!isRetrying">Coba Lagi</span>
              <span v-else class="loading-state">
                <span class="spinner" />
                Memuat Ulang...
              </span>
            </button>
          </div>

          <div class="details-section">
            <button class="action-btn secondary" @click="toggleDetails">
              {{ showDetails ? 'Sembunyikan Detail' : 'Tampilkan Detail' }}
            </button>
            <Transition name="slide-fade">
              <div v-if="showDetails" class="error-details">
                <details open>
                  <summary>Informasi Teknis</summary>
                  <pre>{{ error }}</pre>
                </details>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </Transition>
    <slot v-if="!hasError" />
  </div>
</template>

<style scoped>
/* Transisi untuk fade-in card */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.5s ease, transform 0.5s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

/* Transisi untuk slide-down detail error */
.slide-fade-enter-active {
  transition: all 0.3s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.3s cubic-bezier(1, 0.5, 0.8, 1);
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}

.error-boundary-container {
  width: 100%;
}

.error-content-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  width: 100%;
  padding: 1rem;
  box-sizing: border-box;
  /* Tambahkan background pada parent atau body untuk efek glassmorphism yang maksimal */
  /* background: url(...) no-repeat center center / cover; */
}

.error-card {
  text-align: center;
  padding: 2.5rem 2rem;
  max-width: 550px;
  width: 100%;
  background: rgba(30, 30, 40, 0.7);
  border-radius: 16px;
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.125);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
}

.error-icon {
  color: #ffc107; /* Amber color */
  margin-bottom: 1.5rem;
}

.error-card h3 {
  color: #ffffff;
  margin-bottom: 1rem;
  font-size: 1.75rem;
  font-weight: 600;
}

.error-card p {
  color: #d1d5db; /* Gray 300 */
  margin-bottom: 2rem;
  line-height: 1.6;
  font-size: 1rem;
}

.error-actions {
  margin-bottom: 1.5rem;
}

.action-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  font-size: 1rem;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 160px;
}

.action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.action-btn.primary {
  background: #3b82f6; /* Blue 500 */
  color: white;
}

.action-btn.primary:not(:disabled):hover {
  background: #2563eb; /* Blue 600 */
  transform: translateY(-2px);
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
}

.action-btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: #e5e7eb; /* Gray 200 */
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.action-btn.secondary:not(:disabled):hover {
  background: rgba(255, 255, 255, 0.2);
  color: white;
}

.loading-state {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.spinner {
  width: 1em;
  height: 1em;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.details-section {
  margin-top: 1.5rem;
}

.error-details {
  margin-top: 1rem;
  text-align: left;
}

.error-details details {
  background: rgba(0, 0, 0, 0.4);
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.error-details summary {
  color: #f3f4f6; /* Gray 100 */
  cursor: pointer;
  margin-bottom: 0.75rem;
  font-weight: 500;
}

.error-details pre {
  color: #fca5a5; /* Red 300 */
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-all;
  background-color: rgba(0, 0, 0, 0.2);
  padding: 0.75rem;
  border-radius: 6px;
  font-family: 'Courier New', Courier, monospace;
}
</style>
