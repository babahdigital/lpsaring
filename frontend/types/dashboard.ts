// /types/dashboard.ts

export interface TransaksiTerakhir {
  id: string
  amount: number
  created_at: string
  package: { name: string }
  user: {
    full_name: string
    phone_number?: string
  } | null
}

export interface PaketTerlaris {
  name: string
  count: number
}

export interface PendapatanHarian {
  x: string // ISO date string 'YYYY-MM-DD'
  y: number
}

export interface DashboardStats {
  pendapatanHariIni: number
  pendapatanBulanIni: number
  pendapatanKemarin: number
  transaksiHariIni: number
  pendaftarBaru: number
  penggunaAktif: number
  penggunaOnline: number
  akanKadaluwarsa: number
  kuotaTerjualMb: number
  kuotaTerjual7HariMb: number
  kuotaTerjualKemarinMb: number
  kuotaPerHari: number[]
  pendapatanPerHari: PendapatanHarian[]
  transaksiTerakhir: TransaksiTerakhir[]
  paketTerlaris: PaketTerlaris[]
  pendapatanMingguIni: number
  pendapatanMingguLalu: number
  transaksiMingguIni: number
  transaksiMingguLalu: number
}
