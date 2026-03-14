export type HotspotActivationStage = 'idle' | 'context' | 'sync' | 'verify'
export type HotspotActivationStepState = 'pending' | 'active' | 'completed'

export interface HotspotActivationStep {
  key: Exclude<HotspotActivationStage, 'idle'>
  title: string
  description: string
  state: HotspotActivationStepState
}

export interface HotspotActivationProgress {
  currentStep: number
  totalSteps: number
  progressValue: number
  steps: HotspotActivationStep[]
}

const HOTSPOT_ACTIVATION_STEPS: Array<Omit<HotspotActivationStep, 'state'>> = [
  {
    key: 'context',
    title: 'Deteksi perangkat',
    description: 'Membaca IP dan MAC hotspot yang dipakai perangkat Anda.',
  },
  {
    key: 'sync',
    title: 'Sinkronisasi hotspot',
    description: 'Meminta router memperbarui sesi hotspot secara otomatis.',
  },
  {
    key: 'verify',
    title: 'Verifikasi akses',
    description: 'Memastikan internet sudah aktif sebelum masuk ke portal.',
  },
]

export function resolveHotspotActivationProgress(stage: HotspotActivationStage): HotspotActivationProgress {
  const activeIndex = stage === 'idle'
    ? 0
    : HOTSPOT_ACTIVATION_STEPS.findIndex(step => step.key === stage) + 1

  return {
    currentStep: activeIndex,
    totalSteps: HOTSPOT_ACTIVATION_STEPS.length,
    progressValue: activeIndex > 0
      ? Math.round((activeIndex / HOTSPOT_ACTIVATION_STEPS.length) * 100)
      : 0,
    steps: HOTSPOT_ACTIVATION_STEPS.map((step, index) => ({
      ...step,
      state: activeIndex === 0
        ? 'pending'
        : index < (activeIndex - 1)
            ? 'completed'
            : index === (activeIndex - 1)
                ? 'active'
                : 'pending',
    })),
  }
}