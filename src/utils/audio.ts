let sharedAudioCtx: AudioContext | null = null

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (!sharedAudioCtx || sharedAudioCtx.state === 'closed') {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) return null
    try {
      sharedAudioCtx = new AudioCtx()
    } catch (err) {
      console.warn('Failed to initialize AudioContext:', err)
      return null
    }
  }
  if (sharedAudioCtx.state === 'suspended') {
    sharedAudioCtx.resume().catch((err) => {
      console.warn('Failed to resume AudioContext:', err)
    })
  }
  return sharedAudioCtx
}

export function playPatchworkSound(
  type:
    | 'success'
    | 'correct_chime'
    | 'error'
    | 'xp_gain'
    | 'boost_active'
    | 'streak_milestone'
    | 'lesson_complete'
    | 'checkpoint_complete',
  enabled: boolean = true
) {
  if (!enabled) return
  try {
    const ctx = getAudioContext()
    if (!ctx) return
    const now = ctx.currentTime

    if (type === 'success') {
      const notes = [523.25, 659.25, 783.99] // C5, E5, G5
      notes.forEach((freq, idx) => {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'triangle'
        osc.frequency.setValueAtTime(freq, now + idx * 0.08)
        gain.gain.setValueAtTime(0.15, now + idx * 0.08)
        gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.08 + 0.3)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start(now + idx * 0.08)
        osc.stop(now + idx * 0.08 + 0.35)
      })
    } else if (type === 'correct_chime') {
      // Duolingo-style bell: bright two-tone ding with a shimmering tail.
      const strikes: Array<{ freq: number; at: number }> = [
        { freq: 880, at: 0 }, // A5
        { freq: 1318.5, at: 0.12 }, // E6
      ]
      strikes.forEach(({ freq, at }) => {
        ;[1, 2.01, 2.74].forEach((partial, pIdx) => {
          const osc = ctx.createOscillator()
          const gain = ctx.createGain()
          osc.type = 'sine'
          osc.frequency.setValueAtTime(freq * partial, now + at)
          const peak = pIdx === 0 ? 0.22 : 0.07 / pIdx
          gain.gain.setValueAtTime(0.0001, now + at)
          gain.gain.exponentialRampToValueAtTime(peak, now + at + 0.015)
          gain.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.9)
          osc.connect(gain)
          gain.connect(ctx.destination)
          osc.start(now + at)
          osc.stop(now + at + 1)
        })
      })
    } else if (type === 'error') {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sawtooth'
      osc.frequency.setValueAtTime(180, now)
      osc.frequency.exponentialRampToValueAtTime(120, now + 0.25)
      gain.gain.setValueAtTime(0.12, now)
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(now)
      osc.stop(now + 0.25)
    } else if (type === 'boost_active' || type === 'streak_milestone') {
      const notes = [440, 554.37, 659.25, 880] // A4, C#5, E5, A5
      notes.forEach((freq, idx) => {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sine'
        osc.frequency.setValueAtTime(freq, now + idx * 0.06)
        gain.gain.setValueAtTime(0.15, now + idx * 0.06)
        gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.06 + 0.4)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start(now + idx * 0.06)
        osc.stop(now + idx * 0.06 + 0.45)
      })
    } else if (type === 'lesson_complete' || type === 'checkpoint_complete') {
      const chords = [523.25, 659.25, 783.99, 1046.5]
      chords.forEach((freq, idx) => {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'triangle'
        osc.frequency.setValueAtTime(freq, now + idx * 0.1)
        gain.gain.setValueAtTime(0.18, now + idx * 0.1)
        gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.1 + 0.6)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start(now + idx * 0.1)
        osc.stop(now + idx * 0.1 + 0.65)
      })
    }
  } catch (err) {
    console.warn('Audio playback error:', err)
  }
}
