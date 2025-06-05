// frontend/navigation/horizontal/index.ts

interface HorizontalNavItem {
  title: string
  to: { name: string } | { path: string }
  icon: { icon: string }
  requiresAuth?: boolean
  requiresAdmin?: boolean
}

export default [
  // --- Menu untuk Semua Pengguna (User & Admin) ---
  {
    title: 'Dashboard',
    to: { path: '/dashboard' },
    icon: { icon: 'tabler-smart-home' },
    requiresAuth: true,
  },
  {
    title: 'Beli Paket',
    to: { path: '/beli' },
    icon: { icon: 'tabler-shopping-cart-plus' },
    requiresAuth: true,
  },
  {
    title: 'Riwayat Transaksi',
    to: { path: '/riwayat' },
    icon: { icon: 'tabler-history' },
    requiresAuth: true,
  },
  {
    title: 'Akun Saya',
    to: { path: '/akun' },
    icon: { icon: 'tabler-user-circle' },
    requiresAuth: true,
  },

  // --- Menu Khusus Administrator ---
  {
    title: 'Manajemen Pengguna',
    to: { path: '/admin/users' },
    icon: { icon: 'tabler-users-group' },
    requiresAuth: true,
    requiresAdmin: true,
  },
  {
    title: 'Manajemen Paket',
    to: { path: '/admin/packages' },
    icon: { icon: 'tabler-box' },
    requiresAuth: true,
    requiresAdmin: true,
  },
  {
    title: 'Manajemen Transaksi',
    to: { path: '/admin/transactions' },
    icon: { icon: 'tabler-receipt-2' },
    requiresAuth: true,
    requiresAdmin: true,
  },
  {
    title: 'Laporan',
    to: { path: '/admin/reports' },
    icon: { icon: 'tabler-chart-bar' },
    requiresAuth: true,
    requiresAdmin: true,
  },
  {
    title: 'Pengaturan Sistem',
    to: { path: '/admin/settings' },
    icon: { icon: 'tabler-settings' },
    requiresAuth: true,
    requiresAdmin: true,
  },
] as HorizontalNavItem[]
