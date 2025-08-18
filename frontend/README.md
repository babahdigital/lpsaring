# vue

This template should help get you started developing with Vue 3 in Vite.

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) + [Volar](https://marketplace.visualstudio.com/items?itemName=johnsoncodehk.volar) (and disable Vetur).

## Type Support for `.vue` Imports in TS

Since TypeScript cannot handle type information for `.vue` imports, they are shimmed to be a generic Vue component type by default. In most cases this is fine if you don't really care about component prop types outside of templates.

However, if you wish to get actual prop types in `.vue` imports (for example to get props validation when using manual `h(...)` calls), you can run `Volar: Switch TS Plugin on/off` from VS Code command palette.

## Customize configuration

See [Vite Configuration Reference](https://vitejs.dev/config/).

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

### Type-Check, Compile and Minify for Production

```sh
npm run build
```

## Harmonisasi Backend Metrics

Komponen baru:
- `useMetrics` (SWR, interval default 15s) → konsumsi `/api/metrics/brief`.
- `MetricsStatusBadge.vue` → badge status (ok/waspada/gangguan) berdasar failure_ratio.
- Metrics ringkas sekarang ditampilkan di Footer (lookup total, % gagal, grace size, waktu terakhir & jadwal berikut, tombol Refresh) + badge tambahan:
	- Dot WS (status koneksi / degraded)
	- SSE (muncul bila fallback EventSource aktif)
	- CIR:OPEN (muncul bila circuit breaker API terbuka)
	- Streak gagal berturut-turut (xN)
	`MetricsPanel.vue` dihapus (fungsi diagnostik disederhanakan agar UI tetap ringan).
	- Menggunakan Pinia store `metrics` (polling tunggal) + deltaLookups eksperimen.
	- Adaptive backoff: 15s normal, naik eksponensial hingga 120s saat gagal berturut-turut (1.8^n, min 5s).
	- Persistence localStorage (valid 10 menit) untuk mengurangi flash kosong saat reload.
	- Menampilkan estimasi refresh berikut (nextPlannedDelayMs) dan streak kegagalan.

Contoh pemakaian di layout header:
```vue
<template>
  <header class="flex items-center gap-4">
    <!-- ... existing nav ... -->
	<!-- Metrics ringkas kini otomatis ada di footer -->
  </header>
</template>
```

Failure ratio thresholds:
- < 0.2 : Stabil
- 0.2 – 0.4 : Waspada (indikasi peningkatan kegagalan / latency)
- > 0.4 : Gangguan (perlu investigasi konektivitas MikroTik / Redis)

Optimasi lanjutan (opsional):
- Pinia store untuk share state metrics antar halaman.
	(SUDAH: `store/metrics.ts`)
- Tambah warna tema konsisten (token SCSS) untuk status.
- Ekstensi endpoint backend dengan query `?since=` untuk delta minimal.
