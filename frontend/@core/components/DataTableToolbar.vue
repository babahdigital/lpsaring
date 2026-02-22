<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  itemsPerPage: number
  search?: string
  itemsPerPageOptions?: number[]
  showEntries?: boolean
  showSearch?: boolean
  searchPlaceholder?: string
}

interface Emit {
  (e: 'update:itemsPerPage', value: number): void
  (e: 'update:search', value: string): void
}

const props = withDefaults(defineProps<Props>(), {
  search: '',
  itemsPerPageOptions: () => [10, 25, 50, 100],
  showEntries: true,
  showSearch: true,
  searchPlaceholder: 'Search...',
})

const emit = defineEmits<Emit>()

const itemsPerPageProxy = computed({
  get: () => props.itemsPerPage,
  set: (value: number) => emit('update:itemsPerPage', value),
})

const searchProxy = computed({
  get: () => props.search ?? '',
  set: (value: string) => emit('update:search', value),
})

const entriesOptions = computed(() => {
  const options = Array.isArray(props.itemsPerPageOptions) ? props.itemsPerPageOptions : []
  return options.filter(n => Number.isFinite(n) && n > 0)
})
</script>

<template>
  <div class="d-flex align-center justify-sm-space-between justify-center flex-wrap gap-4">
    <div v-if="props.showEntries" class="d-flex align-center flex-wrap gap-2">
      <span class="text-disabled">Show</span>

      <AppSelect
        v-model="itemsPerPageProxy"
        :items="entriesOptions"
        density="compact"
        hide-details
        style="max-width: 90px"
      />

      <span class="text-disabled">entries</span>

      <slot name="start" />
    </div>

    <div class="d-flex align-center flex-wrap gap-2">
      <slot name="end" />

      <template v-if="props.showSearch">
        <span class="text-disabled d-none d-sm-inline">Search:</span>
        <AppTextField
          v-model="searchProxy"
          :placeholder="props.searchPlaceholder"
          density="compact"
          variant="outlined"
          clearable
          prepend-inner-icon="tabler-search"
          single-line
          hide-details
          style="min-width: 220px"
        />
      </template>
    </div>
  </div>
</template>
