export default [
  {
    title: 'Dashboard Admin',
    to: { path: '/admin/dashboard' },
    icon: { icon: 'tabler-layout-dashboard' },
  },
  // PENYEMPURNAAN: Membuat grup menu "Manajemen"
  {
    title: 'Manajemen',
    icon: { icon: 'tabler-adjustments-horizontal' }, // Ikon untuk grup
    children: [
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
      // --- PENAMBAHAN MENU BARU ---
      {
        title: 'Event & Promo',
        to: { path: '/admin/promos' },
        icon: { icon: 'tabler-discount-2' }, // Menggunakan ikon yang konsisten
      },
      // --- AKHIR PENAMBAHAN ---
    ],
  },
]