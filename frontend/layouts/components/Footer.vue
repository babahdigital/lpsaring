<template>
  <div class="footer-root h-100 d-flex flex-column flex-md-row align-center justify-md-space-between justify-center gap-y-1">
    <span class="d-flex align-center text-high-emphasis text-center text-md-left">
      S O B I G I D U L &copy; {{ new Date().getFullYear() }}
    </span>
    <span class="d-flex align-center justify-center text-center text-md-left text-subtitle-2 font-weight-light text-medium-emphasis footer-sync-text">
      Sinkronisasi data akan dilakukan secara otomatis dan berkala
    </span>
  </div>
</template>

<style scoped>
.footer-root {
  padding-inline: 0.5rem;
  padding-block-end: calc(0.75rem + env(safe-area-inset-bottom));
}

.footer-sync-text {
  max-inline-size: 560px;
}

@media (max-width: 599.98px) {
  .footer-sync-text {
    max-inline-size: 320px;
    line-height: 1.45;
  }
}
</style>
