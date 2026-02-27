export const ACCESS_STATUS_VALUES = ['ok', 'blocked', 'inactive', 'expired', 'habis', 'fup'] as const
export type AccessStatus = (typeof ACCESS_STATUS_VALUES)[number]

export const STATUS_PAGE_ALLOWED_VALUES = ['blocked', 'inactive', 'expired', 'habis', 'fup'] as const
