/**
 * plugins/webfontloader.js
 *
 * webfontloader documentation: https://github.com/typekit/webfontloader
 */

export async function loadFonts(enableRemoteFonts: boolean) {
  if (!enableRemoteFonts)
    return

  try {
    const webFontLoader = await import(/* webpackChunkName: "webfontloader" */'webfontloader')

    webFontLoader.load({
      google: {
        families: ['Public+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,300;1,400;1,500;1,600;1,700&display=swap'],
      },
    })
  }
  catch {
    // Kegagalan memuat font eksternal tidak boleh mengganggu aplikasi.
  }
}

export default defineNuxtPlugin(() => {
  const runtimeConfig = useRuntimeConfig()
  const enableRemoteFonts = String(runtimeConfig.public.enableRemoteFonts ?? 'false').toLowerCase() === 'true'
  loadFonts(enableRemoteFonts)
})
