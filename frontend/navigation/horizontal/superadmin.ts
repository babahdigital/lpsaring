// frontend/navigation/horizontal/superadmin.ts
export default [
  // PENYEMPURNAAN: Membuat grup menu "Pengaturan" untuk Super Admin
  {
    title: 'Pengaturan',
    icon: { icon: 'tabler-settings' }, // Ikon untuk grup
    action: 'read',
    subject: 'Settings',
    children: [
      {
        title: 'Notifikasi',
        to: { path: '/admin/settings/notifications' },
        icon: { icon: 'tabler-bell-ringing' },
        action: 'read',
        subject: 'Notifications',
      },
      {
        title: 'Aplikasi',
        to: { path: '/admin/settings/general' },
        icon: { icon: 'tabler-tool' },
        action: 'read',
        subject: 'GeneralSettings',
      },
    ],
  },
]
