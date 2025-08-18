<script setup lang="ts">
interface Statistic {
  icon: string
  color: string
  title: string
  value: number
  change: number
}

defineProps<{
  statistics: Statistic[]
}>()
</script>

<template>
  <VRow class="mb-4">
    <VCol
      v-for="(data, index) in statistics"
      :key="index"
      cols="12"
      md="3"
      sm="6"
    >
      <VCard>
        <VCardText>
          <div class="d-flex align-center justify-space-between">
            <div>
              <div class="d-flex align-center gap-x-2">
                <VAvatar
                  variant="tonal"
                  :color="data.color"
                  rounded
                  size="42"
                >
                  <VIcon
                    :icon="data.icon"
                    size="24"
                  />
                </VAvatar>
                <h5 class="text-h5 font-weight-bold">
                  {{ data.value }}
                </h5>
              </div>
              <div class="mt-2 text-body-1">
                {{ data.title }}
              </div>
            </div>
          </div>
        </VCardText>
      </VCard>
    </VCol>
  </VRow>
</template>
