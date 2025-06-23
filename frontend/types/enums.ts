// frontend/types/enums.ts

export enum UserRole {
  USER = 'USER',
  ADMIN = 'ADMIN',
  SUPER_ADMIN = 'SUPER_ADMIN',
}

export enum ApprovalStatus {
  PENDING_APPROVAL = 'PENDING_APPROVAL',
  APPROVED = 'APPROVED',
  REJECTED = 'REJECTED',
}

export enum UserBlok {
  A = 'A',
  B = 'B',
  C = 'C',
  D = 'D',
  E = 'E',
  F = 'F',
}

export enum UserKamar {
  Kamar_1 = '1',
  Kamar_2 = '2',
  Kamar_3 = '3',
  Kamar_4 = '4',
  Kamar_5 = '5',
  Kamar_6 = '6',
}

export enum TransactionStatus {
  PENDING = 'PENDING',
  SUCCESS = 'SUCCESS',
  FAILED = 'FAILED',
  EXPIRED = 'EXPIRED',
  CANCELLED = 'CANCELLED',
  UNKNOWN = 'UNKNOWN',
}

// ------ ENUM Yang Dimigrasi dari @core/enums dan @layouts/enums ------
export enum Skins {
  Default = 'default',
  Bordered = 'bordered',
}

export enum Theme {
  Light = 'light',
  Dark = 'dark',
  System = 'system',
}

export enum Layout {
  Vertical = 'vertical',
  Horizontal = 'horizontal',
  Collapsed = 'collapsed',
}

export enum Direction {
  Ltr = 'ltr',
  Rtl = 'rtl',
}

export enum ContentWidth {
  Fluid = 'fluid',
  Boxed = 'boxed',
}

export enum NavbarType {
  Sticky = 'sticky',
  Static = 'static',
  Hidden = 'hidden',
}

export enum FooterType {
  Sticky = 'sticky',
  Static = 'static',
  Hidden = 'hidden',
}

export enum AppContentLayoutNav { // Ini yang menyebabkan error Anda
  Vertical = 'vertical',
  Horizontal = 'horizontal',
}

export enum HorizontalNavType {
  Sticky = 'sticky',
  Static = 'static',
  Hidden = 'hidden',
}
