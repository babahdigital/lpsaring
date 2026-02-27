type HotspotRedirectInput = {
  hotspotLoginRequired?: boolean | null
  hotspotSessionActive?: boolean | null
}

export function shouldRedirectToHotspotRequired(input: HotspotRedirectInput): boolean {
  return input.hotspotLoginRequired === true && input.hotspotSessionActive === false
}
