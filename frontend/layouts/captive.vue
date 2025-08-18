// layouts/captive.vue
<template>
  <div class="captive-layout-wrapper">
    <div class="background-gradient" />

    <VContainer fluid class="fill-height pa-4">
      <VRow justify="center" align="center" class="fill-height">
        <VCol cols="12" sm="10" md="6" lg="5" xl="4" class="d-flex flex-column align-center">
          <div class="logo-header mb-6">
            <VIcon icon="tabler-wifi" size="32" color="white" />
            <h1 class="logo-text ml-3">
              Portal Hotspot
            </h1>
          </div>

          <main class="w-100">
            <slot />
          </main>

          <footer class="footer-info mt-8">
            <p class="text-caption text-white text-center">
              Mode captive portal: autentikasi akan otomatis menyesuaikan IP/MAC perangkat Anda.
            </p>
          </footer>
        </VCol>
      </VRow>
    </VContainer>
  </div>
</template>

<style scoped>
.captive-layout-wrapper {
  min-height: 100vh;
  min-height: 100dvh;
  position: relative;
  overflow-x: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #1a1a1a;
}

.background-gradient {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: radial-gradient(circle at 10% 20%, rgba(var(--v-theme-primary), 0.3) 0%, transparent 40%),
              radial-gradient(circle at 90% 80%, rgba(var(--v-theme-success), 0.25) 0%, transparent 50%);
  animation: background-pan 20s ease-in-out infinite;
}

@keyframes background-pan {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.logo-header {
  display: flex;
  align-items: center;
  justify-content: center;
  animation: slide-down 0.8s ease-out both;
}

.logo-text {
  font-size: 1.5rem;
  font-weight: 600;
  color: white;
  text-shadow: 0 2px 8px rgba(0,0,0,0.5);
}

.footer-info {
  opacity: 0.6;
  animation: slide-up 0.8s ease-out 0.2s both;
}

@keyframes slide-down {
  from { opacity: 0; transform: translateY(-30px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes slide-up {
  from { opacity: 0; transform: translateY(30px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
