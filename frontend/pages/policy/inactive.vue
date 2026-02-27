<script setup lang="ts">
import PolicyStatusView from '~/components/policy/PolicyStatusView.vue'

definePageMeta({
  layout: 'blank',
  auth: false,
  public: true,
})

useHead({ title: 'Akun Belum Aktif' })
</script>

<template>
  <PolicyStatusView status="inactive" />
</template>
