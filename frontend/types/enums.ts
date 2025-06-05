// frontend/types/enums.ts

export enum UserRole {
  USER = "USER",
  ADMIN = "ADMIN",
  SUPER_ADMIN = "SUPER_ADMIN",
}

export enum ApprovalStatus {
  PENDING_APPROVAL = "PENDING_APPROVAL",
  APPROVED = "APPROVED",
  REJECTED = "REJECTED",
}

export enum UserBlok {
  A = "A",
  B = "B",
  C = "C",
  D = "D",
  E = "E",
  F = "F",
}

export enum UserKamar {
  // Menggunakan nama member yang valid di TypeScript
  Kamar_1 = "1",
  Kamar_2 = "2",
  Kamar_3 = "3",
  Kamar_4 = "4",
  Kamar_5 = "5",
  Kamar_6 = "6",
}

export enum TransactionStatus {
  PENDING = "PENDING",
  SUCCESS = "SUCCESS",
  FAILED = "FAILED",
  EXPIRED = "EXPIRED",
  CANCELLED = "CANCELLED",
  UNKNOWN = "UNKNOWN",
}

// Tambahkan Enum lain yang Anda butuhkan dan ada di models.py