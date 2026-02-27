<script setup lang="ts">
import PolicyStatusView from '~/components/policy/PolicyStatusView.vue'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Akses Diblokir' })
</script>

<template>
  <PolicyStatusView status="blocked" />
</template>
