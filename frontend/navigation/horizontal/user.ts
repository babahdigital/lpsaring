// frontend/navigation/horizontal/user.ts

export default [
  {
    title: 'Dashboard',
    to: { path: '/dashboard' },
    icon: { icon: 'tabler-smart-home' },
    action: 'read',
    subject: 'Dashboard',
  },
  {
    title: 'Beli Paket',
    to: { path: '/beli' },
    icon: { icon: 'tabler-shopping-cart-plus' },
    action: 'read',
    subject: 'Packages',
  },
  {
    title: 'Riwayat Transaksi',
    to: { path: '/riwayat' },
    icon: { icon: 'tabler-history' },
    action: 'read',
    subject: 'Transactions',
  },
]
