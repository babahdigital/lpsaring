// layouts/blank.vue - VERSI FINAL

<script lang="ts" setup>
import { computed } from 'vue'

import { useSettingsStore } from '~/store/settings'

const settingsStore = useSettingsStore()
const layoutClasses = computed(() => {
  const s = settingsStore.settings
  return [
    'layout-wrapper',
    'layout-blank',
    s.SKIN ? `skin--${s.SKIN}` : '',
    s.APP_CONTENT_WIDTH ? `content-width-${s.APP_CONTENT_WIDTH}` : '',
    s.APP_CONTENT_LAYOUT_NAV ? `layout-nav-type-${s.APP_CONTENT_LAYOUT_NAV}` : '',
    s.FOOTER_TYPE ? `footer-type-${s.FOOTER_TYPE}` : '',
    s.NAVBAR_TYPE ? `navbar-type-${s.NAVBAR_TYPE}` : '',
  ].filter(Boolean)
})
</script>

<template>
  <div :class="layoutClasses">
    <slot />
  </div>
</template>

<style>
.layout-wrapper.layout-blank {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
</style>
