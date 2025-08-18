<!-- pages/settings/devices.vue -->
<script>
import { mapGetters } from 'vuex'

import UserDeviceManager from '~/components/settings/UserDeviceManager.vue'

export default {
  name: 'DevicesSettingsPage',

  components: {
    UserDeviceManager,
  },

  layout: 'dashboard',

  middleware: ['auth'],

  computed: {
    ...mapGetters('auth', ['isAuthenticated', 'user']),
  },

  head() {
    return {
      title: 'Pengaturan Perangkat',
    }
  },
}
</script>

<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="mb-4">
          <v-card-title>
            <v-icon left>mdi-shield-account</v-icon>
            Keamanan Perangkat
          </v-card-title>
          <v-card-text>
            <p>Halaman ini memungkinkan Anda mengelola perangkat yang diizinkan untuk mengakses akun Anda. Jika ada perangkat yang tidak Anda kenali, segera hapus dan ubah kata sandi Anda.</p>

            <v-alert color="info" outlined class="mt-4">
              <v-row align="center">
                <v-col class="grow">
                  <div>
                    <strong>Mengapa penting?</strong>
                    <p class="mb-0">Setiap perangkat baru yang mengakses akun Anda akan memerlukan otorisasi. Ini membantu melindungi akun Anda dari akses yang tidak sah.</p>
                  </div>
                </v-col>
                <v-col class="shrink">
                  <v-icon large>mdi-shield-check</v-icon>
                </v-col>
              </v-row>
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <UserDeviceManager />
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title>
            <v-icon left>mdi-frequently-asked-questions</v-icon>
            FAQ
          </v-card-title>
          <v-card-text>
            <v-expansion-panels>
              <v-expansion-panel>
                <v-expansion-panel-header>
                  Mengapa saya perlu mengotorisasi perangkat saya?
                </v-expansion-panel-header>
                <v-expansion-panel-content>
                  Otorisasi perangkat membantu melindungi akun Anda dari akses yang tidak sah. Jika seseorang mencoba masuk ke akun Anda dari perangkat yang tidak dikenal, mereka akan diminta untuk mengotorisasi perangkat tersebut.
                </v-expansion-panel-content>
              </v-expansion-panel>

              <v-expansion-panel>
                <v-expansion-panel-header>
                  Apa yang terjadi jika saya menghapus perangkat dari daftar?
                </v-expansion-panel-header>
                <v-expansion-panel-content>
                  Menghapus perangkat dari daftar akan mencabut aksesnya ke akun Anda. Jika Anda mencoba masuk dari perangkat tersebut lagi, Anda akan diminta untuk mengotorisasi perangkat tersebut lagi.
                </v-expansion-panel-content>
              </v-expansion-panel>

              <v-expansion-panel>
                <v-expansion-panel-header>
                  Mengapa perangkat saya muncul beberapa kali di daftar?
                </v-expansion-panel-header>
                <v-expansion-panel-content>
                  Jika perangkat Anda terhubung ke jaringan yang berbeda (seperti beralih dari WiFi ke data seluler), sistem mungkin mendeteksi perubahan alamat IP dan mencatatnya sebagai perangkat baru. Ini normal dan Anda dapat menghapus entri lama jika diinginkan.
                </v-expansion-panel-content>
              </v-expansion-panel>
            </v-expansion-panels>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
