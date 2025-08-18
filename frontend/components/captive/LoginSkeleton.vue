<script setup lang="ts">
// Komponen ini murni untuk tampilan, tidak memerlukan logika script.
</script>

<template>
  <VCard
    class="text-center pa-8"
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
      class="mx-auto mb-2"
      max-width="280"
    />

    <VSkeletonLoader
      type="paragraph"
      class="mx-auto mb-8"
      max-width="320"
    />

    <VSkeletonLoader
      type="text"
      class="mb-4"
      height="56"
    />

    <VSkeletonLoader
      type="button"
      height="44"
    />
  </VCard>
</template>
