<script setup lang="ts">
import PolicyStatusView from '~/components/policy/PolicyStatusView.vue'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Kuota Habis' })
</script>

<template>
  <PolicyStatusView status="habis" />
</template>
