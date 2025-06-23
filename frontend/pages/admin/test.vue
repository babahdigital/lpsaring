<template>
  <div>
    <h3>Test Icons</h3>
    <VIcon icon="tabler:circle-check" size="x-large" />
    <p>Icon "tabler:circle-check" should be above.</p>

    <VIcon icon="complete" size="x-large" />
    <p>Icon "complete" (tabler:circle-check alias) should be above.</p>

    <VIcon icon="mdi-check" size="x-large" />
    <p>Icon "mdi-check" should be above.</p>

    <span class="tabler-circle-check custom-icon" style="font-size: 48px;"></span>
    <p>Icon "tabler-circle-check" via span should be above.</p>
  </div>
</template>
