<script lang="ts" setup>
import { useSkins } from '@core/composable/useSkins'

const { injectSkinClasses } = useSkins()

// ℹ️ This will inject classes in body tag for accurate styling
injectSkinClasses()
</script>

<template>
  <div class="layout-wrapper layout-blank">
    <v-app>
      <v-main>
        <slot />
      </v-main>
    </v-app>
  </div>
</template>

<style>
.layout-wrapper.layout-blank {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.layout-wrapper.layout-blank > .v-application {
  flex-grow: 1;
}
</style>
