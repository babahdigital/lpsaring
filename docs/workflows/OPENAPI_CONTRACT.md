# Workflow OpenAPI Contract

Dokumen ini menjelaskan workflow resmi ketika endpoint prioritas berubah.

Lampiran wajib:
- [.github/copilot-instructions.md](../../.github/copilot-instructions.md)

## Artefak Yang Harus Tetap Sinkron

1. `backend/app/infrastructure/http/**`
2. `contracts/openapi/openapi.v1.yaml`
3. `frontend/types/api/contracts.generated.ts`
4. `frontend/types/api/contracts.ts`
5. [docs/API_DETAIL.md](../API_DETAIL.md)

## Kapan Workflow Ini Wajib Diikuti

- Menambah endpoint baru.
- Mengubah method, path, query, request body, atau response body endpoint prioritas.
- Mengubah otorisasi endpoint sehingga behavior `401` atau role berubah.

## Urutan Kerja

1. Implementasikan perubahan backend terlebih dahulu.
2. Perbarui OpenAPI agar path, schema, dan response sinkron.
3. Regenerasi typed contract frontend.
4. Sesuaikan frontend yang mengonsumsi endpoint tersebut.
5. Perbarui [docs/API_DETAIL.md](../API_DETAIL.md) bila signature atau cakupan endpoint berubah.
6. Jalankan gate lokal atau biarkan CI memverifikasi perubahan.

## Gate Yang Menjaga Workflow Ini

- `scripts/api_quality_gate.py`: validasi integritas OpenAPI dan marker generated contract.
- `scripts/access_status_parity_gate.py`: sinkronisasi status akses lintas FE, BE, dan docs.
- `scripts/contract_gate.py`: memastikan perubahan endpoint prioritas disertai perubahan kontrak dan dokumen API.

## Checklist PR

- OpenAPI sudah diperbarui.
- Typed contract frontend sudah ikut berubah.
- `docs/API_DETAIL.md` ikut berubah bila perlu.
- Test atau smoke check yang relevan sudah dijalankan.