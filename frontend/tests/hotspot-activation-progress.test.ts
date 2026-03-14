import { describe, expect, it } from 'vitest'

import { resolveHotspotActivationProgress } from '../utils/hotspotActivationProgress'

describe('hotspotActivationProgress', () => {
  it('starts with no active step while idle', () => {
    expect(resolveHotspotActivationProgress('idle')).toEqual({
      currentStep: 0,
      totalSteps: 3,
      progressValue: 0,
      steps: [
        {
          key: 'context',
          title: 'Deteksi perangkat',
          description: 'Membaca IP dan MAC hotspot yang dipakai perangkat Anda.',
          state: 'pending',
        },
        {
          key: 'sync',
          title: 'Sinkronisasi hotspot',
          description: 'Meminta router memperbarui sesi hotspot secara otomatis.',
          state: 'pending',
        },
        {
          key: 'verify',
          title: 'Verifikasi akses',
          description: 'Memastikan internet sudah aktif sebelum masuk ke portal.',
          state: 'pending',
        },
      ],
    })
  })

  it('marks earlier steps completed when verification is running', () => {
    expect(resolveHotspotActivationProgress('verify')).toMatchObject({
      currentStep: 3,
      totalSteps: 3,
      progressValue: 100,
      steps: [
        { key: 'context', state: 'completed' },
        { key: 'sync', state: 'completed' },
        { key: 'verify', state: 'active' },
      ],
    })
  })
})