import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { buyStreakFreeze, loadProgress } from './progressStore'

export function LessonShell({
  progress,
  total,
  hearts,
  streak,
  onQuit,
  soundEnabled,
  onToggleSound,
  onOpenGuidebook,
  lessonId,
  footer,
  children,
}: {
  progress: number
  total: number
  hearts: number
  streak: number
  onQuit: () => void
  soundEnabled: boolean
  onToggleSound: () => void
  onOpenGuidebook?: () => void
  lessonId: string
  footer: ReactNode
  children: ReactNode
}) {
  const [confirmQuit, setConfirmQuit] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [notes, setNotes] = useState('')
  const [shopNote, setShopNote] = useState('')
  const pct = total === 0 ? 0 : Math.round((progress / total) * 100)

  useEffect(() => {
    const saved = localStorage.getItem(`patchwork_notes_${lessonId}`)
    setNotes(saved ?? '')
  }, [lessonId])

  return (
    <div className="lp">
      <header className="lp-top">
        <button type="button" className="lp-icon-btn" aria-label="Quit lesson" onClick={() => setConfirmQuit(true)}>
          ✕
        </button>
        <div
          className="lp-progress"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={progress}
          aria-label="Lesson progress"
        >
          <div className="lp-progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <button
          type="button"
          className="lp-icon-btn"
          aria-label="Lesson menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          ⋮
        </button>
        <div className="lp-stat" aria-label={`${streak} day streak`}>
          🔥 {streak}
        </div>
        <div className="lp-stat" aria-label={`${hearts} hearts`}>
          ❤️ {hearts}
        </div>
      </header>

      {menuOpen ? (
        <div className="lp-menu" role="menu">
          <button type="button" onClick={onToggleSound}>
            {soundEnabled ? 'Sound on' : 'Sound off'}
          </button>
          <button type="button" onClick={onOpenGuidebook}>
            Guidebook
          </button>
          <label>
            Session notes
            <textarea
              aria-label="Session notes"
              value={notes}
              onChange={(event) => {
                setNotes(event.target.value)
                localStorage.setItem(`patchwork_notes_${lessonId}`, event.target.value)
              }}
            />
          </label>
          <button
            type="button"
            onClick={() => {
              const result = buyStreakFreeze()
              setShopNote(result.ok ? 'Streak freeze ready.' : 'A streak freeze costs 10 gems.')
            }}
          >
            Shop · streak freeze ({loadProgress().gems} gems)
          </button>
          {shopNote ? <p>{shopNote}</p> : null}
        </div>
      ) : null}

      <main className="lp-main">{children}</main>
      {footer}

      {confirmQuit ? (
        <div className="lp-modal" role="dialog" aria-modal="true" aria-label="Quit lesson? You'll lose progress">
          <div className="lp-modal-card">
            <h2>Quit lesson?</h2>
            <p>You'll lose progress.</p>
            <div className="lp-modal-actions">
              <button type="button" className="lp-btn lp-btn-secondary" onClick={() => setConfirmQuit(false)}>
                Stay
              </button>
              <button type="button" className="lp-btn lp-btn-primary" onClick={onQuit}>
                Quit
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
