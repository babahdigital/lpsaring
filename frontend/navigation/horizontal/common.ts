// frontend/navigation/horizontal/common.ts

export default [
  {
    title: 'Perangkat Saya', // [BARU] Menu untuk manajemen perangkat
    to: { path: '/akun/perangkat' },
    icon: { icon: 'tabler-devices-2' },
    action: 'read',
    subject: 'Devices',
  },
  {
    title: 'Profile',
    to: { path: '/akun/profile' }, // Arahkan langsung ke tab profil
    icon: { icon: 'tabler-user-circle' },
    action: 'read',
    subject: 'Profile',
  },
]
