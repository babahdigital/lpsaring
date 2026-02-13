<script lang="ts" setup>
import { useSkins } from '@core/composable/useSkins'
import { useConfigStore } from '@core/stores/config'
import { AppContentLayoutNav } from '@layouts/enums'
import { switchToVerticalNavOnLtOverlayNavBreakpoint } from '@layouts/utils'
import { defineAsyncComponent } from 'vue'

const DefaultLayoutWithHorizontalNav = defineAsyncComponent(() => import('./components/DefaultLayoutWithHorizontalNav.vue'))
const DefaultLayoutWithVerticalNav = defineAsyncComponent(() => import('./components/DefaultLayoutWithVerticalNav.vue'))

const configStore = useConfigStore()

switchToVerticalNavOnLtOverlayNavBreakpoint()

const { layoutAttrs, injectSkinClasses } = useSkins()

injectSkinClasses()

// SECTION: Loading Indicator
const isFallbackStateActive = ref(false)
const refLoadingIndicator = ref<any>(null)

// watching if the fallback state is active and the refLoadingIndicator component is available
watch([isFallbackStateActive, refLoadingIndicator], () => {
  if (isFallbackStateActive.value && refLoadingIndicator.value)
    refLoadingIndicator.value.fallbackHandle()

  if (!isFallbackStateActive.value && refLoadingIndicator.value)
    refLoadingIndicator.value.resolveHandle()
}, { immediate: true })
// !SECTION
</script>

<template>
  <ClientOnly>
    <Component
      v-bind="layoutAttrs"
      :is="configStore.appContentLayoutNav === AppContentLayoutNav.Vertical ? DefaultLayoutWithVerticalNav : DefaultLayoutWithHorizontalNav"
    >
      <AppLoadingIndicator ref="refLoadingIndicator" />

      <Suspense
        :timeout="0"
        @fallback="isFallbackStateActive = true"
        @resolve="isFallbackStateActive = false"
      >
        <slot />
      </Suspense>
    </Component>
    <template #fallback>
      <div class="initial-loading-screen">
        <div class="loading-content">
          <VProgressCircular
            indeterminate
            color="primary"
            size="48"
          />
          <p class="mt-3 text-center text-disabled">
            Memuat tampilan...
          </p>
        </div>
      </div>
    </template>
  </ClientOnly>
</template>

<style lang="scss">
// As we are using `layouts` plugin we need its styles to be imported
@use "@layouts/styles/default-layout";
</style>
