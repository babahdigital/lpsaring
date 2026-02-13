// frontend/navigation/horizontal/admin.ts
export default [
  {
    title: 'Dashboard Admin',
    to: { path: '/admin/dashboard' },
    icon: { icon: 'tabler-layout-dashboard' },
  },
  {
    title: 'Manajemen',
    icon: { icon: 'tabler-adjustments-horizontal' },
    children: [
      {
        title: 'Permintaan',
        to: { path: '/admin/requests' },
        icon: { icon: 'tabler-mail-fast' },
      },
      {
        title: 'Pengguna',
        to: { path: '/admin/users' },
        icon: { icon: 'tabler-users-group' },
      },
      {
        title: 'Paket',
        to: { path: '/admin/packages' },
        icon: { icon: 'tabler-box' },
      },
      {
        title: 'Transaksi',
        to: { path: '/admin/transactions' },
        icon: { icon: 'tabler-receipt-2' },
      },
    ],
  },
  {
    title: 'Event & Promo',
    to: { path: '/admin/promos' },
    icon: { icon: 'tabler-discount' },
  },
  {
    title: 'Log Aktivitas',
    to: { path: '/admin/logs' },
    icon: { icon: 'tabler-history' },
  },
  {
    title: 'WhatsApp',
    to: { path: '/admin/whatsapp' },
    icon: { icon: 'tabler-brand-whatsapp' },
  },
  {
    title: 'Backup & Restore',
    to: { path: '/admin/backup' },
    icon: { icon: 'tabler-database-export' },
  },
]
