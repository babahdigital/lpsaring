<script setup lang="ts">
import type { NuxtError } from '#app'
import { clearError } from '#app'
// defineProps tidak lagi diimpor dari 'vue'
import { computed } from 'vue' // computed tetap diimpor jika digunakan
import { useRoute } from 'vue-router'

// Mendefinisikan prop 'error' yang akan dikirim oleh Nuxt ke halaman ini
// defineProps sekarang otomatis tersedia dalam <script setup>
const props = defineProps<{
  error: NuxtError
}>()

const isDev = import.meta.dev
const route = useRoute()

const errorPageTitle = computed(() => {
  if (props.error?.statusCode === 404) {
    return 'Halaman Tidak Ditemukan'
  }
  if (props.error?.statusCode && props.error.statusCode >= 500 && props.error.statusCode < 600) {
    return 'Kesalahan Pada Server'
  }
  return 'Terjadi Kesalahan'
})

const errorMessage = computed(() => {
  if (props.error?.statusCode === 404) {
    const urlPath = route.fullPath || '(URL tidak diketahui)'
    return `Maaf, kami tidak dapat menemukan halaman yang Anda cari di alamat ${urlPath}. Mungkin halaman tersebut telah dihapus, dipindahkan, atau URL yang Anda masukkan salah.`
  }
  if (props.error?.statusCode && props.error.statusCode >= 500 && props.error.statusCode < 600) {
    return 'Maaf, sistem kami sedang mengalami gangguan teknis. Tim kami sedang berupaya memperbaikinya. Silakan coba lagi dalam beberapa saat.'
  }
  return props.error?.message || props.error?.statusMessage || 'Terjadi kesalahan yang tidak dapat diidentifikasi. Silakan coba kembali atau hubungi dukungan jika masalah berlanjut.'
})

function handleErrorClear() {
  clearError({ redirect: '/' })
}
</script>

<template>
  <v-app class="bg-grey-lighten-5">
    <v-container fluid class="fill-height">
      <v-row align="center" justify="center" class="fill-height text-center">
        <v-col cols="12" sm="10" md="8" lg="6">
          <div class="pa-5">
            <h1 class="text-h2 font-weight-bold mb-3" :class="props.error?.statusCode === 404 ? 'text-amber-darken-2' : 'text-red-darken-2'">
              {{ props.error?.statusCode || 'Oops!' }}
            </h1>
            <h2 class="text-h5 font-weight-medium mb-6 text-grey-darken-2">
              {{ errorPageTitle }}
            </h2>
            <p class="text-body-1 mb-8 text-grey-darken-1" style="line-height: 1.7;">
              {{ errorMessage }}
            </p>

            <v-btn
              color="primary"
              variant="flat"
              size="large"
              rounded="lg"
              class="px-6"
              @click="handleErrorClear"
            >
              <v-icon start>
                mdi-home-outline
              </v-icon>
              Kembali ke Beranda
            </v-btn>

            <div v-if="isDev && props.error" class="mt-10 text-left">
              <p class="text-caption text-disabled mb-1">
                Informasi Debug (Hanya Development):
              </p>
              <v-sheet border rounded="md" class="pa-3 bg-grey-lighten-4 overflow-auto" max-height="200px">
                <pre class="text-caption" style="white-space: pre-wrap; word-break: break-all;">Error Object: {{ JSON.stringify(props.error, null, 2) }}</pre>
              </v-sheet>
            </div>
          </div>
        </v-col>
      </v-row>
    </v-container>
  </v-app>
</template>

<style scoped>
.text-h2 {
  font-size: 4rem !important;
  line-height: 1.1;
}
.text-h5 {
  font-size: 1.5rem !important;
}
.text-body-1 {
  font-size: 1rem !important;
}
pre {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
}
</style>
