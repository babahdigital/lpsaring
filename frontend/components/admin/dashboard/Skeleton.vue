<script setup lang="ts">
// Komponen ini murni untuk tampilan, tidak memerlukan script
</script>

<template>
  <div class="pa-4">
    <VRow class="mb-4">
      <VCol
        v-for="i in 4"
        :key="i"
        cols="12"
        md="3"
        sm="6"
      >
        <VSkeletonLoader type="card-avatar, article" />
      </VCol>
    </VRow>
    <VRow match-height>
      <VCol
        cols="12"
        md="4"
      >
        <VSkeletonLoader
          type="image"
          height="270"
        />
      </VCol>
      <VCol
        cols="12"
        md="4"
      >
        <VSkeletonLoader
          type="image"
          height="270"
        />
      </VCol>
      <VCol
        cols="12"
        md="4"
      >
        <VSkeletonLoader
          type="image"
          height="270"
        />
      </VCol>
    </VRow>
    <VRow class="mt-4">
      <VCol
        cols="12"
        md="5"
      >
        <VSkeletonLoader
          type="image"
          height="400"
        />
      </VCol>
      <VCol
        cols="12"
        md="7"
      >
        <VSkeletonLoader
          type="image"
          height="400"
        />
      </VCol>
    </VRow>
  </div>
</template>
