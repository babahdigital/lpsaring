// frontend/navigation/horizontal/admin.ts

export default [
  {
    title: 'Dashboard Admin',
    to: { path: '/admin/dashboard' },
    icon: { icon: 'tabler-layout-dashboard' },
  },
  {
    title: 'Manajemen Pengguna',
    to: { path: '/admin/users' },
    icon: { icon: 'tabler-users-group' },
  },
  {
    title: 'Manajemen Paket',
    to: { path: '/admin/packages' },
    icon: { icon: 'tabler-box' },
  },
  {
    title: 'Manajemen Transaksi',
    to: { path: '/admin/transactions' },
    icon: { icon: 'tabler-receipt-2' },
  },
]