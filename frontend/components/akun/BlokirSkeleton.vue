<script setup lang="ts">
// Komponen ini murni untuk tampilan, tidak memerlukan logika script.
</script>

<template>
  <VCard
    class="text-center pa-6 pa-md-10"
    elevation="8"
    rounded="lg"
  >
    <VSkeletonLoader
      type="avatar"
      class="mx-auto mb-6"
      width="80"
      height="80"
    />

    <VSkeletonLoader
      type="heading"
      class="mx-auto mb-4"
      max-width="280"
    />

    <VSkeletonLoader
      type="paragraph"
      class="mx-auto mb-8"
      max-width="480"
    />

    <VSkeletonLoader
      type="button"
      class="mx-auto"
      height="44"
      :width="$vuetify.display.smAndDown ? '100%' : '180'"
    />
  </VCard>
</template>
