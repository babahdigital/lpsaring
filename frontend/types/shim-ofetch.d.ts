// shim-ofetch.d.ts - ensures ofetch types recognized if TS has resolution hiccups
declare module 'ofetch' {
  export interface FetchError<T = any> extends Error { statusCode?: number, statusMessage?: string, data?: T }
}
