import type { MongoAbility, MongoQuery } from '@casl/ability'

import { AbilityBuilder, createMongoAbility } from '@casl/ability'
import { abilitiesPlugin } from '@casl/vue'

// Definisikan tipe Ability khusus untuk aplikasi Anda.
export type AppAbility = MongoAbility<[string, 'all' | string], MongoQuery>

export default defineNuxtPlugin((nuxtApp) => {
  // PERBAIKAN: Berikan 'createMongoAbility' sebagai argumen ke AbilityBuilder.
  const { can, rules } = new AbilityBuilder<AppAbility>(createMongoAbility)

  // Untuk sementara, berikan akses penuh ke semua resource
  // Nanti ini bisa disesuaikan berdasarkan role user
  can('read', 'all')
  can('create', 'all')
  can('update', 'all')
  can('delete', 'all')

  // Buat instansi ability dengan aturan awal yang sudah benar tipenya.
  const ability = createMongoAbility<AppAbility>(rules)

  // Gunakan plugin 'abilitiesPlugin' untuk menyediakan 'ability' ke seluruh aplikasi.
  nuxtApp.vueApp.use(abilitiesPlugin, ability, {
    useGlobalProperties: true,
  })

  // Sediakan 'ability' agar bisa diakses di tempat lain via useNuxtApp().
  return {
    provide: {
      ability,
    },
  }
})
