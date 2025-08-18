// frontend/navigation/horizontal/admin.ts
export default [
  {
    title: 'Dashboard Admin',
    to: { path: '/admin/dashboard' },
    icon: { icon: 'tabler-layout-dashboard' },
    action: 'read',
    subject: 'AdminDashboard',
  },
  {
    title: 'Manajemen',
    icon: { icon: 'tabler-adjustments-horizontal' },
    action: 'read',
    subject: 'Management',
    children: [
      {
        title: 'Permintaan',
        to: { path: '/admin/requests' },
        icon: { icon: 'tabler-mail-fast' },
        action: 'read',
        subject: 'Requests',
      },
      {
        title: 'Pengguna',
        to: { path: '/admin/users' },
        icon: { icon: 'tabler-users-group' },
        action: 'read',
        subject: 'Users',
      },
      {
        title: 'Paket',
        to: { path: '/admin/packages' },
        icon: { icon: 'tabler-box' },
        action: 'read',
        subject: 'Packages',
      },
      {
        title: 'Transaksi',
        to: { path: '/admin/transactions' },
        icon: { icon: 'tabler-receipt-2' },
        action: 'read',
        subject: 'Transactions',
      },
    ],
  },
  {
    title: 'Event & Promo',
    to: { path: '/admin/promos' },
    icon: { icon: 'tabler-discount' },
    action: 'read',
    subject: 'Promos',
  },
  {
    title: 'Log Aktivitas',
    to: { path: '/admin/logs' },
    icon: { icon: 'tabler-history' },
    action: 'read',
    subject: 'Logs',
  },
]
