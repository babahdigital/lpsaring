// types/nitro-h3.d.ts
import 'nitropack'

declare module 'nitropack' {
  // patch: tambahkan opsi h3 ke NitroConfig
  interface NitroConfig {
    h3?: {
      trustedProxies?: string[]
    }
  }
}
