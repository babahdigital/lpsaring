import { describe, expect, it } from 'vitest'

import {
  format_for_whatsapp_link,
  format_to_local_phone,
  normalize_to_e164,
} from '../utils/formatters'

describe('formatters', () => {
  it('normalizes local numbers to E.164', () => {
    expect(normalize_to_e164('081234567890')).toBe('+6281234567890')
    expect(normalize_to_e164('6281234567890')).toBe('+6281234567890')
    expect(normalize_to_e164('+6281234567890')).toBe('+6281234567890')
    expect(normalize_to_e164('+67512345678')).toBe('+67512345678')
    expect(normalize_to_e164('67512345678')).toBe('+67512345678')
    expect(normalize_to_e164('0067512345678')).toBe('+67512345678')
    expect(normalize_to_e164('+123456789012345')).toBe('+123456789012345')
  })

  it('formats to local phone number', () => {
    expect(format_to_local_phone('6281234567890')).toBe('081234567890')
    expect(format_to_local_phone('81234567890')).toBe('081234567890')
  })

  it('formats for whatsapp links', () => {
    expect(format_for_whatsapp_link('081234567890')).toBe('6281234567890')
    expect(format_for_whatsapp_link('6281234567890')).toBe('6281234567890')
    expect(format_for_whatsapp_link('+67512345678')).toBe('67512345678')
  })
})
