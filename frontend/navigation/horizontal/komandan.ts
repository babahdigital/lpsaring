export default [
  {
    title: 'Dashboard',
    to: { path: '/dashboard' },
    icon: { icon: 'tabler-smart-home' },
    action: 'read',
    subject: 'Dashboard',
  },
  {
    title: 'Riwayat Request', // Menu baru
    to: { path: '/requests' }, // Arahkan ke halaman riwayat yang baru kita buat
    icon: { icon: 'tabler-history' },
    action: 'read',
    subject: 'Requests',
  },
]
