// frontend/navigation/horizontal/superadmin.ts
export default [
  {
    title: 'Operasional',
    to: { path: '/admin/operations' },
    icon: { icon: 'tabler-activity-heartbeat' },
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
  {
    title: 'Pengaturan',
    icon: { icon: 'tabler-settings' },
    children: [
      {
        title: 'Aplikasi',
        to: { path: '/admin/settings/general' },
        icon: { icon: 'tabler-tool' },
      },
      {
        title: 'Notifikasi',
        to: { path: '/admin/settings/notifications' },
        icon: { icon: 'tabler-bell-ringing' },
      },
      {
        title: 'MikroTik',
        to: { path: '/admin/mikrotik' },
        icon: { icon: 'tabler-router' },
      },
    ],
  },
]
