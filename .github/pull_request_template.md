## Ringkasan Perubahan

- Jelaskan singkat apa yang diubah dan alasannya.

## Policy Impact (Wajib Diisi)

Centang semua area yang terdampak:

- [ ] Quota sync / perhitungan usage (`bytes -> MB`, `total_quota_used_mb`)
- [ ] Auto debt policy (`quota_auto_debt_limit`)
- [ ] Manual debt policy (pre-EOM vs EOM hard-block)
- [ ] Unlimited policy (debt=0, time-based expiry)
- [ ] Access policy (`blocked/fup/habis/expired/active/unlimited`)
- [ ] MikroTik ip-binding policy (`blocked/regular/bypassed`)
- [ ] Address-list sync (`active/fup/habis/expired/inactive/blocked/unauthorized`)
- [ ] Reset login cleanup (active/cookie/ip-binding/dhcp/arp/address-list)
- [ ] DHCP static lease flow saat login sukses
- [ ] Device authorization / MAC resolution flow

## Invariant Check (Wajib)

Jika salah satu invariant berikut berubah, tandai sebagai breaking policy dan update dokumen aturan:

- [ ] Auto debt block **tidak** hard-block jaringan.
- [ ] Manual debt pre-EOM **tidak** block.
- [ ] Manual debt EOM **wajib** hard-block.
- [ ] Unlimited **tidak** membawa debt kuota.
- [ ] Reset login membersihkan state auth/router sesuai flow.

## Dokumen & Test

- [ ] Sudah review/update [docs/REFERENCE_PENGEMBANGAN.md](../docs/REFERENCE_PENGEMBANGAN.md) dan [docs/ACCESS_STATUS_MATRIX.md](../docs/ACCESS_STATUS_MATRIX.md) bila policy terdampak.
- [ ] Sudah menambah/menyesuaikan test policy yang relevan.
- [ ] Test backend terkait policy lulus lokal.

## Risiko & Rollback

- Risiko perubahan:
- Strategi rollback:
## Summary
- 

## Validation
- [ ] Backend tests relevant to change executed
- [ ] Frontend lint/typecheck/tests relevant to change executed
- [ ] OpenAPI contract updated when endpoint payload/signature changes

## UI Standards Checklist (Vuexy policy)
- [ ] Tidak mengimpor runtime dari `typescript-version/full-version` atau `starter-kit`
- [ ] Mengikuti pedoman [docs/VUEXY_BASELINE_STRATEGY.md](docs/VUEXY_BASELINE_STRATEGY.md)
- [ ] Table/filter/pagination mengikuti pola komponen admin yang sudah ada
- [ ] Tidak menambah token warna/font/shadow di luar design system
