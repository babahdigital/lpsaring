# Runbook Operasional - `audit-hotspot-parity`

Dokumen ini menjelaskan command CLI `flask audit-hotspot-parity` untuk audit
holistik parity antara:

- status address-list hotspot,
- ip-binding,
- list `unauthorized`,
- DHCP lease,
- dan cakupan user unlimited.

## 1) Tujuan

Gunakan command ini untuk memastikan policy akses hotspot tetap konsisten dan
mudah diaudit melalui artefak JSON.

Target utama:

- mendeteksi status list yang tidak punya pasangan binding,
- memastikan `unauthorized` tidak overlap dengan status list,
- memantau alignment antara authorized MAC, ip-binding, dan DHCP,
- memberi sampel data agar tindak lanjut cepat.

## 2) Command Dasar

Jalankan di konteks aplikasi Flask (container backend):

```bash
flask audit-hotspot-parity
```

Contoh produksi (DigitalOcean split stack):

```bash
cd /home/abdullah/lpsaring/app
docker exec hotspot_prod_flask_backend \
  /opt/venv/bin/flask audit-hotspot-parity \
  --output /tmp/lpsaring_addrlist_binding_parity_dryrun.json
```

## 3) Opsi Command

- `--output <path>`
  - Default: `/tmp/lpsaring_addrlist_binding_parity_dryrun.json`
  - Lokasi file JSON hasil audit.
- `--sample-size <n>`
  - Default: `20`
  - Jumlah sampel per kategori temuan.
- `--managed-only` / `--include-all`
  - Default: `--managed-only`
  - `managed-only` hanya menghitung row status dengan marker comment
    `lpsaring|status=`.
- `--fail-on-drift` / `--no-fail-on-drift`
  - Default: `--no-fail-on-drift`
  - Jika `--fail-on-drift`, command akan exit non-zero bila ada drift penting.

## 4) Ringkasan Output CLI

Di akhir run, command mencetak satu baris summary, contoh:

```text
output_json=/tmp/parity.json status_without_binding=0 critical_without_binding=0 unauthorized_overlap=0 unauthorized_with_binding=0 authorized_mac_without_binding=0 authorized_mac_without_dhcp=6 binding_dhcp_ip_mismatch=0 unlimited_without_binding_scoped=0
```

Makna ringkas:

- `status_without_binding`
  - Semua status list terkelola yang belum punya pasangan binding.
- `critical_without_binding`
  - Subset kritikal: active/fup/habis/blocked.
- `unauthorized_overlap`
  - Jumlah IP yang muncul di `unauthorized` sekaligus status list.
- `unauthorized_with_binding`
  - Row unauthorized yang ternyata masih punya binding.
- `authorized_mac_without_binding`
  - MAC authorized di DB yang tidak ditemukan pada ip-binding.
- `authorized_mac_without_dhcp`
  - MAC authorized di DB yang belum punya DHCP lease.
- `binding_dhcp_ip_mismatch`
  - MAC yang punya binding + DHCP tetapi IP berbeda.
- `unlimited_without_binding_scoped`
  - User unlimited (yang sudah punya authorized device) namun tidak punya
    binding valid.

## 5) Struktur JSON Penting

Field yang paling sering dipakai untuk gate operasional:

- `policy_focus.critical_without_binding_total`
- `policy_focus.all_status_without_binding_total`
- `policy_focus.unauthorized_must_not_duplicate_status_count`
- `unauthorized.rows_with_binding_count`
- `dhcp_alignment.authorized_without_ip_binding`
- `dhcp_alignment.authorized_without_dhcp_lease`
- `dhcp_alignment.binding_dhcp_ip_mismatch`
- `unlimited_alignment.scoped_unlimited_users_with_authorized_device.without_binding`

Sampel detail tersedia di `samples.*` untuk percepatan investigasi.

## 6) Guardrail Rekomendasi

Untuk policy akses yang sehat, target berikut sebaiknya `0`:

- `policy_focus.critical_without_binding_total`
- `policy_focus.unauthorized_must_not_duplicate_status_count`
- `unauthorized.rows_with_binding_count`
- `dhcp_alignment.binding_dhcp_ip_mismatch`
- `unlimited_alignment.scoped_unlimited_users_with_authorized_device.without_binding`

Catatan operasional:

- `dhcp_alignment.authorized_without_dhcp_lease` bisa non-zero saat device
  authorized sedang offline atau belum terlihat oleh router.

## 7) Contoh Mode Gate

Gunakan mode fail-fast untuk otomatisasi:

```bash
docker exec hotspot_prod_flask_backend \
  /opt/venv/bin/flask audit-hotspot-parity \
  --output /tmp/parity.json \
  --fail-on-drift
```

Jika ada drift, command gagal dengan exit non-zero dan menampilkan metrik yang
gagal.

## 8) Tindak Lanjut Cepat Per Temuan

- `unauthorized_overlap > 0`
  - jalankan `sync-unauthorized-hosts --apply`, lalu audit ulang.
- `critical_without_binding_total > 0`
  - jalankan `prune-hotspot-status-without-binding` dalam mode dry-run, validasi,
    lalu apply sesuai SOP.
- `authorized_without_dhcp_lease > 0`
  - cek apakah device sedang online dan punya binding IP yang valid,
    lalu jalankan `sync-dhcp-leases --only-authorized`.
- `binding_dhcp_ip_mismatch > 0`
  - investigasi konflik stale lease/binding pada MAC terkait.

## 9) Referensi Implementasi

- Command: `backend/app/commands/audit_hotspot_parity_command.py`
- Registrasi CLI: `backend/app/__init__.py`
- Runbook umum sinkronisasi MikroTik: `docs/OPERATIONS_MIKROTIK_SYNC.md`
