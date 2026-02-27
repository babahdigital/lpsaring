<script setup lang="ts">
import PolicyStatusView from '~/components/policy/PolicyStatusView.vue'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Kuota FUP' })
</script>

<template>
  <PolicyStatusView status="fup" />
</template>
