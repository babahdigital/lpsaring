<script setup lang="ts">
import PolicyStatusView from '~/components/policy/PolicyStatusView.vue'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Masa Aktif Berakhir' })
</script>

<template>
  <PolicyStatusView status="expired" />
</template>
