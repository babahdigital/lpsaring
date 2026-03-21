# Incident 2026-03-22: GitHub Actions Dispatch Gagal dari Workspace Lokal — Jalur IPv6/NAT64 `api.github.com` Reset Koneksi

**Severity:** Medium  
**Status:** Resolved  
**Kategori:** Near-miss operasional / CI release tooling

---

## Ringkasan

Manual dispatch ke workflow GitHub Actions `docker-publish.yml` sempat gagal berulang dari workspace Windows lokal. Gejala yang terlihat membingungkan: workflow file tetap valid, `gh auth status` sehat, dan GitHub Actions/CI untuk repo yang sama tetap bisa berjalan normal di sisi GitHub. Namun setiap request manual dari mesin lokal ke `api.github.com` jatuh dengan error seperti:

- `wsarecv: An existing connection was forcibly closed by the remote host`
- `WinError 10054`
- `curl: (35) Send failure: Connection was reset`
- `The underlying connection was closed: An unexpected error occurred on a send`

Root cause akhirnya bukan pada workflow, token, atau repository settings, melainkan pada jalur jaringan lokal yang memprioritaskan endpoint IPv6/NAT64 rusak untuk `api.github.com`.

---

## Dampak

- Manual trigger `workflow_dispatch` dari workspace lokal gagal walaupun workflow valid.
- Release operator bisa salah menyangka bahwa:
  - token `gh` kadaluarsa,
  - workflow `docker-publish.yml` rusak,
  - repository permissions berubah,
  - atau GitHub Actions sedang outage penuh.
- CI reguler yang berjalan di runner GitHub tidak terdampak.

---

## Gejala yang Terlihat

- `gh auth status -h github.com` tetap menunjukkan login aktif dan scope `workflow` tersedia.
- `gh workflow run ...` gagal di request GraphQL/REST.
- `gh api repos/.../dispatches` juga gagal.
- PowerShell `Invoke-RestMethod` dan `curl.exe` ke endpoint dispatch ikut gagal.
- Workflow yang sama bisa di-dispatch kembali setelah request dipaksa memakai IPv4.

---

## Timeline Ringkas

1. Manual dispatch `docker-publish.yml` diminta dari workspace lokal.
2. Dispatch via `gh workflow run`, `gh api`, PowerShell REST, dan `curl.exe` gagal dengan connection reset.
3. Workflow file `.github/workflows/docker-publish.yml` diverifikasi masih memiliki trigger `workflow_dispatch`.
4. `gh auth status` diverifikasi sehat dan token masih punya scope `workflow`.
5. Audit DNS/TLS ke `api.github.com` menunjukkan dua jalur:
   - IPv6/NAT64: `64:ff9b::14cd:f3a8`
   - IPv4: `20.205.243.168`
6. TLS handshake ke IPv4 berhasil, sedangkan jalur IPv6/NAT64 reset koneksi.
7. Request dispatch diulang dengan memaksa resolusi `api.github.com` ke IPv4.
8. Workflow dispatch berhasil (`HTTP 204`) dan run baru terbentuk.

---

## Root Cause

Mesin lokal memilih atau mencoba jalur IPv6/NAT64 untuk `api.github.com`, dan jalur itu sedang rusak di tingkat jaringan. Karena GitHub CLI, PowerShell, dan request default lain memakai resolver sistem normal, mereka terus jatuh ke path yang sama walaupun:

- token masih valid,
- workflow masih mendukung `workflow_dispatch`,
- dan layanan GitHub sebenarnya sehat.

Evidence yang mengunci RCA ini:

- hasil DNS menampilkan alamat NAT64 `64:ff9b::14cd:f3a8` serta IPv4 publik `20.205.243.168`,
- HTTPS/TLS ke IPv4 sukses,
- HTTPS/TLS ke IPv6/NAT64 gagal dengan reset,
- dispatch langsung berhasil setelah `api.github.com` dipaksa resolved ke IPv4.

---

## Resolusi

Langkah yang terbukti benar:

1. jangan langsung menyalahkan workflow atau token bila `gh auth status` masih sehat,
2. cek resolusi dan konektivitas ke `api.github.com` per family address,
3. bila IPv6/NAT64 reset tetapi IPv4 sehat, rerun dispatch dengan helper yang memaksa `api.github.com` ke IPv4,
4. setelah dispatch sukses, verifikasi run baru benar-benar muncul dan mengarah ke SHA target.

Pada insiden ini, dispatch berhasil setelah helper lokal memonkeypatch `socket.getaddrinfo` agar `api.github.com` selalu resolved ke `AF_INET` selama request GitHub API berlangsung.

---

## Guardrail Baru

Dokumentasi CI/CD dan operasi produksi diperbarui dengan aturan berikut:

- jika `gh workflow run` atau `gh api` gagal dengan `wsarecv`, `WinError 10054`, atau `connection reset` tetapi `gh auth status` tetap sehat, curigai jalur jaringan ke `api.github.com`, bukan workflow,
- bedakan kegagalan manual dispatch dari kesehatan CI GitHub secara umum,
- untuk workspace Windows ini, forcing IPv4 ke `api.github.com` adalah workaround yang tervalidasi,
- setelah dispatch sukses, selalu verifikasi run baru dan SHA target sebelum melanjutkan deploy.

---

## Pelajaran

1. `gh auth status` sehat tidak menjamin request API akan lolos jika jalur jaringan sistem sedang bermasalah.
2. CI GitHub yang tetap hijau tidak membuktikan manual dispatch dari mesin lokal juga sehat.
3. Error `connection reset` pada dispatch GitHub bisa murni network-path specific, bukan issue token atau workflow file.
4. Audit address family (`IPv4` vs `IPv6/NAT64`) memberi jawaban jauh lebih cepat daripada mengutak-atik workflow yang sebenarnya tidak rusak.