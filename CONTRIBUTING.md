# Panduan Kontribusi (CONTRIBUTING)

Terima kasih sudah ingin berkontribusi.

## 1) Alur PR (Pull Request)
1. Buat branch dari `main`.
   - Format: `feature/<ringkas>`, `fix/<ringkas>`, `chore/<ringkas>`
2. Kerjakan perubahan dengan fokus scope yang jelas.
3. Jalankan lint + testing yang relevan.
4. Buka PR dan isi checklist di bawah.

## 2) Checklist PR
- [ ] Perubahan sesuai scope dan tidak menambah regresi.
- [ ] Lint frontend lolos.
- [ ] Typecheck frontend lolos (jika ada perubahan TS).
- [ ] Testing backend (jika ada perubahan backend).
- [ ] Dokumentasi diperbarui jika ada perubahan API / perilaku penting.

## 3) Lint & Typecheck
### Frontend (Nuxt 3)
- Lint:
  - `pnpm lint`
- Typecheck (Nuxt):
  - `pnpm exec nuxi typecheck`

### Backend (Flask)
- Jika ada tests:
  - `pytest`

## 4) Standar Kode
- Ikuti style/konvensi yang sudah ada di file terkait.
- Hindari perubahan format massal yang tidak terkait.
- Tambahkan handling error yang konsisten.

## 5) Dokumentasi
Jika ada perubahan API / request / response:
- Update [docs/API_DETAIL.md](docs/API_DETAIL.md)
- Update [docs/API_OVERVIEW.md](docs/API_OVERVIEW.md) bila diperlukan
- Tambahkan entri di [CHANGELOG.md](CHANGELOG.md)
- Lampirkan tautan [.github/copilot-instructions.md](.github/copilot-instructions.md) di dokumen terkait.

## 6) Komunikasi
- Jelaskan konteks perubahan secara ringkas di PR.
- Sertakan langkah uji yang dijalankan.
