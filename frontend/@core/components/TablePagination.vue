<script setup lang="ts">
import { paginationMeta } from '@/utils/paginationMeta'
import { computed } from 'vue'

interface Props {
  page: number
  itemsPerPage: number
  totalItems: number
}

interface Emit {
  (e: 'update:page', value: number): void
}

const props = defineProps<Props>()

const emit = defineEmits<Emit>()

function updatePage(value: number) {
  emit('update:page', value)
}

const pageCount = computed(() => {
  if (props.itemsPerPage <= 0)
    return 1

  return Math.max(1, Math.ceil(props.totalItems / props.itemsPerPage))
})

const shouldShowPagination = computed(() => props.totalItems > props.itemsPerPage)
</script>

<template>
  <div>
    <VDivider />

    <div class="d-flex align-center justify-sm-space-between justify-center flex-wrap gap-3 px-6 py-3">
      <p class="text-disabled mb-0">
        {{ paginationMeta({ page: props.page, itemsPerPage: props.itemsPerPage }, props.totalItems) }}
      </p>

      <VPagination
        v-if="shouldShowPagination"
        :model-value="props.page"
        active-color="primary"
        :length="pageCount"
        :total-visible="$vuetify.display.xs ? 1 : Math.min(pageCount, 5)"
        @update:model-value="updatePage"
      />
    </div>
  </div>
</template>
