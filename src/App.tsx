import { useCallback, useEffect, useRef, useState } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────
type TestResult = {
  name: string
  passed: boolean
  required: boolean
  description: string
  error: string | null
}
type LessonSummary = {
  id: string
  title: string
  order: number
  difficulty: string
  duration_minutes: number
  status: 'completed' | 'current' | 'locked'
}
type Lesson = {
  id: string
  title: string
  description: string
  order: number
  difficulty: string
  duration_minutes: number
  starter_code: string
}
type ProviderStatus = {
  provider: string
  name: string
  available: boolean
  model: string
  is_current: boolean
  reason: string | null
  error: string | null
}
type ProvidersOverview = {
  current_provider: string
  fallback_provider: string | null
  providers: ProviderStatus[]
}

type Unit = {
  id: number
  title: string
  description: string
  color: string
  lessonIds: string[]
  isCheckpoint?: boolean
}

// ─── Unit Mapping for Course Path ─────────────────────────────────────────────
const UNITS: Unit[] = [
  {
    id: 1,
    title: 'Unit 1: Python Basics & Variables',
    description: 'Learn values, variable assignment, numbers, and basic math',
    color: '#58cc02', // Duolingo Green
    lessonIds: ['variables-01', 'numbers-01', 'expressions-01'],
  },
  {
    id: 2,
    title: 'Unit 2: Logic & Conditionals',
    description: 'Booleans, comparisons, and branching with if statements',
    color: '#1cb0f6', // Duolingo Blue
    lessonIds: ['booleans-01', 'conditionals-01'],
  },
  {
    id: 3,
    title: 'Unit 3: Strings & Manipulation',
    description: 'Working with text, string formatting, and string methods',
    color: '#ce82ff', // Duolingo Purple
    lessonIds: ['strings-01', 'string-methods-01'],
  },
  {
    id: 4,
    title: 'Unit 4: Sequences & Iteration',
    description: 'Lists, loops, and list manipulation',
    color: '#ff9600', // Duolingo Orange
    lessonIds: ['lists-01', 'loops-01', 'list-methods-01'],
  },
  {
    id: 5,
    title: 'Unit 5: Data Structures & Functions',
    description: 'Dictionaries, tuples, and function capstones',
    color: '#ff4b4b', // Duolingo Coral
    lessonIds: ['dicts-01', 'tuples-01', 'functions-01'],
  },
]

// Helper function to calculate XP
function calculateXP(completedCount: number): number {
  return completedCount * 25
}

// ─── Line Numbers Component ───────────────────────────────────────────────────
function LineNumbers({ code }: { code: string }) {
  const lines = (code ?? '').split('\n')
  return (
    <div className="line-numbers" aria-hidden="true">
      <div className="line-numbers-content">
        {lines.map((_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
    </div>
  )
}

// ─── Main App Component ───────────────────────────────────────────────────────
function App() {
  const [lessons, setLessons] = useState<LessonSummary[]>([])
  const [activeLesson, setActiveLesson] = useState<Lesson | null>(null)
  const [view, setView] = useState<'map' | 'lesson'>('map')
  const [code, setCode] = useState('')
  const [results, setResults] = useState<TestResult[] | null>(null)
  const [hintLevel, setHintLevel] = useState(1)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [aiEnabled, setAiEnabled] = useState(true)
  const [providersOverview, setProvidersOverview] = useState<ProvidersOverview | null>(null)
  const [selectedProvider, setSelectedProvider] = useState<string>('ollama')
  const [previousHints, setPreviousHints] = useState<string[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [isLoadingLesson, setIsLoadingLesson] = useState(false)
  const [isTutorLoading, setIsTutorLoading] = useState(false)
  const [showCompletionModal, setShowCompletionModal] = useState(false)
  const [sessionNotes, setSessionNotes] = useState<string[]>([])
  const [noteInput, setNoteInput] = useState('')
  const [backendError, setBackendError] = useState(false)

  const resultsRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<HTMLTextAreaElement>(null)

  const currentProviderStatus = providersOverview?.providers?.find((p) => p.provider === selectedProvider)
  const isAiAvailable = currentProviderStatus?.available ?? false

  const scrollToResults = useCallback(() => {
    resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [])

  // ── Load Lessons Summary ───────────────────────────────────────────────────
  const fetchLessons = useCallback(async () => {
    try {
      const res = await fetch('/api/lessons')
      if (!res.ok) throw new Error('Backend unavailable')
      const data = (await res.json()) as LessonSummary[]
      setLessons(data)
      setBackendError(false)
    } catch {
      setBackendError(true)
    }
  }, [])

  useEffect(() => {
    fetchLessons()
  }, [fetchLessons])

  // ── AI Providers Health Polling ─────────────────────────────────────────────
  const fetchProvidersHealth = useCallback(async () => {
    try {
      const response = await fetch('/api/ai/providers')
      if (!response.ok) return
      const data = (await response.json()) as ProvidersOverview
      setProvidersOverview(data)
      if (data.current_provider) {
        setSelectedProvider(data.current_provider)
      }
    } catch {
      // Ignore background poll errors
    }
  }, [])

  useEffect(() => {
    fetchProvidersHealth()
    const interval = setInterval(fetchProvidersHealth, 10000)
    return () => clearInterval(interval)
  }, [fetchProvidersHealth])

  const handleProviderChange = async (providerId: string) => {
    setSelectedProvider(providerId)
    try {
      const res = await fetch('/api/ai/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerId }),
      })
      if (res.ok) {
        await fetchProvidersHealth()
      }
    } catch {
      // Ignore
    }
  }

  // ── Start / Open Lesson ────────────────────────────────────────────────────
  const openLesson = useCallback(async (item: LessonSummary) => {
    if (item.status === 'locked') {
      return
    }
    setIsLoadingLesson(true)
    try {
      const response = await fetch(`/api/lessons/${item.id}`)
      if (!response.ok) throw new Error('Lesson unavailable')
      const selected = (await response.json()) as Lesson
      setActiveLesson(selected)
      setCode(selected.starter_code ?? '')
      setResults(null)
      setPreviousHints([])
      setHintLevel(1)
      setFeedback(null)
      setShowCompletionModal(false)
      setView('lesson')
      setTimeout(() => {
        editorRef.current?.focus()
      }, 50)
    } catch {
      setFeedback('Failed to load lesson. Please try again.')
    } finally {
      setIsLoadingLesson(false)
    }
  }, [])

  // ── Run / Check Code ───────────────────────────────────────────────────────
  const runTests = useCallback(async () => {
    if (!activeLesson) return
    setIsRunning(true)
    setFeedback('Evaluating your Python code in the sandbox…')
    try {
      const response = await fetch(`/api/lessons/${activeLesson.id}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      if (!response.ok) throw new Error('Sandbox unavailable')
      const execution = (await response.json()) as {
        passed: boolean
        completed: boolean
        tests: TestResult[]
      }
      setResults(execution.tests)

      if (execution.completed) {
        setShowCompletionModal(true)
        setFeedback('🎉 Outstanding work! All checks passed.')
        fetchLessons()
      } else if (execution.passed) {
        setFeedback('✓ Required checks passed! Ready to submit.')
      } else {
        const failed = execution.tests.filter((t) => !t.passed && t.required)
        setFeedback(
          failed.length > 0
            ? `Not quite! ${failed.length} required check${failed.length > 1 ? 's' : ''} failed.`
            : 'Some optional checks failed. Review and try again!'
        )
      }
      setTimeout(scrollToResults, 100)
    } catch {
      setFeedback('The sandbox execution service is offline.')
    } finally {
      setIsRunning(false)
    }
  }, [activeLesson, code, fetchLessons, scrollToResults])

  // ── Ask Tutor for Hint ─────────────────────────────────────────────────────
  const askTutor = useCallback(async () => {
    if (!activeLesson || !aiEnabled) return
    setIsTutorLoading(true)
    setFeedback('Asking your AI Tutor Coach for guidance…')
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 45000)
    try {
      const response = await fetch('/api/tutor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          lesson_id: activeLesson.id,
          lesson_title: activeLesson.title,
          instructions: activeLesson.description,
          code,
          test_results: results ?? [],
          previous_hints: previousHints,
          hint_level: hintLevel,
          session_id: 'default',
          solution_requested: false,
        }),
      })
      if (!response.ok) throw new Error(`HTTP error ${response.status}`)
      const tutor = (await response.json()) as {
        available: boolean
        message: string
        hint_level: number
      }
      setFeedback(tutor.message)
      if (tutor.available) {
        setPreviousHints((h) => [...h, tutor.message].slice(-8))
        setHintLevel(Math.min(tutor.hint_level + 1, 4))
      }
    } catch {
      setFeedback('AI tutoring is currently unavailable. Deterministic tests are still available.')
    } finally {
      clearTimeout(timeoutId)
      setIsTutorLoading(false)
    }
  }, [activeLesson, aiEnabled, code, results, previousHints, hintLevel])

  // ── Keydown Handler for Editor ─────────────────────────────────────────────
  const handleEditorKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault()
        runTests()
        return
      }
      if (e.key === 'Tab') {
        e.preventDefault()
        const el = e.currentTarget
        const start = el.selectionStart
        const end = el.selectionEnd
        const next = code.substring(0, start) + '    ' + code.substring(end)
        setCode(next)
        requestAnimationFrame(() => {
          el.selectionStart = start + 4
          el.selectionEnd = start + 4
        })
      }
    },
    [code, runTests]
  )

  const addNote = useCallback(() => {
    const trimmed = noteInput.trim()
    if (!trimmed) return
    setSessionNotes((n) => [...n, trimmed])
    setNoteInput('')
  }, [noteInput])

  const nextLessonSummary = lessons.find((l) => l.status === 'current') ?? lessons.find((l) => l.status === 'completed')

  const completedCount = lessons.filter((l) => l.status === 'completed').length
  const totalCount = lessons.length || 13
  const overallProgressPct = Math.round((completedCount / totalCount) * 100)
  const currentXP = calculateXP(completedCount)

  const allPassed = results !== null && results.length > 0 && results.every((r) => r.passed || !r.required)
  const failedRequired = results?.filter((r) => !r.passed && r.required) ?? []

  return (
    <div className="duo-app">
      {/* ── Header Bar ────────────────────────────────────────────────────── */}
      <header className="duo-header" role="banner">
        <div className="duo-brand" onClick={() => setView('map')} style={{ cursor: 'pointer' }}>
          <div className="duo-logo-icon">p</div>
          <span>patchwork</span>
        </div>

        {/* Global Progress Indicators */}
        <div className="duo-header-stats">
          <div className="duo-stat-badge xp-badge" title="Total Experience Points">
            <span className="stat-icon">⚡</span>
            <span>{currentXP} XP</span>
          </div>
          <div className="duo-stat-badge progress-badge" title="Course Completion">
            <span className="stat-icon">🎯</span>
            <span>{overallProgressPct}%</span>
          </div>
        </div>

        <div className="duo-header-right">
          {/* Provider Dropdown & Status */}
          <div className="duo-provider-selector">
            <select
              value={selectedProvider}
              onChange={(e) => handleProviderChange(e.target.value)}
              aria-label="Select AI Provider"
              className="duo-select-provider"
            >
              {providersOverview?.providers?.map((p) => (
                <option key={p.provider} value={p.provider}>
                  {p.available ? `✓ ${p.name}` : `⚠ ${p.name}`}
                </option>
              )) ?? <option value="ollama">Ollama</option>}
            </select>

            <div className="duo-status-badge">
              <span className={`duo-status-dot ${isAiAvailable ? 'active' : ''}`} />
              {isAiAvailable
                ? `${currentProviderStatus?.name || selectedProvider} ready`
                : `${currentProviderStatus?.name || selectedProvider} unavailable`}
            </div>
          </div>

          <button
            className="duo-button duo-button-secondary duo-btn-sm"
            aria-label="AI tutor on"
            onClick={() => setAiEnabled((e) => !e)}
          >
            {aiEnabled ? 'AI tutor on' : 'AI tutor off'}
          </button>
        </div>
      </header>

      {backendError && (
        <div className="backend-error-banner" role="alert">
          <span aria-hidden="true">⚠️</span>
          <span>
            Backend unavailable — run <code>uvicorn backend.main:app --reload</code> then{' '}
            <button onClick={() => window.location.reload()} className="inline-link">
              Try again
            </button>
          </span>
        </div>
      )}

      {/* ── Main View Router ──────────────────────────────────────────────── */}
      {view === 'map' ? (
        /* ── COURSE MAP VIEW ────────────────────────────────────────────── */
        <main className="duo-course-map-container" aria-label="Course path map">
          {/* Hero Unit Banner */}
          <section className="duo-map-hero">
            <div className="duo-hero-info">
              <h2>Python Learning Progression</h2>
              <p>Master Python step-by-step through bite-sized coding exercises and deterministic feedback.</p>
            </div>
            {nextLessonSummary && (
              <button
                className="duo-button duo-button-primary duo-hero-jump-btn"
                onClick={() => openLesson(nextLessonSummary)}
              >
                Jump to Current Exercise →
              </button>
            )}
          </section>

          {/* Visual Learning Path with Units */}
          <div className="duo-path-sections">
            {UNITS.map((unit) => {
              const unitLessons = unit.lessonIds
                .map((id) => lessons.find((l) => l.id === id))
                .filter((l): l is LessonSummary => l !== undefined)

              return (
                <section key={unit.id} className="duo-unit-section">
                  <header className="duo-unit-header" style={{ borderLeftColor: unit.color }}>
                    <div className="duo-unit-tag" style={{ background: unit.color }}>
                      UNIT {unit.id}
                    </div>
                    <h3 className="duo-unit-title">{unit.title}</h3>
                    <p className="duo-unit-desc">{unit.description}</p>
                  </header>

                  <div className="duo-unit-path-nodes">
                    {unitLessons.map((item, index) => {
                      const isCurrent = item.status === 'current'
                      const isCompleted = item.status === 'completed'
                      const isLocked = item.status === 'locked'

                      // Offset positioning for playful curving path feel
                      const offsetClass = index % 2 === 0 ? 'node-offset-left' : 'node-offset-right'

                      return (
                        <div key={item.id} className={`duo-path-node-wrapper ${offsetClass}`}>
                          {index > 0 && <div className="duo-path-connector" />}
                          <button
                            id={`lesson-nav-${item.id}`}
                            className={`duo-path-node ${item.status}`}
                            onClick={() => openLesson(item)}
                            disabled={isLocked || isLoadingLesson}
                            aria-current={isCurrent ? 'page' : undefined}
                            aria-label={`${item.title} — ${
                              isCompleted ? 'Completed' : isCurrent ? 'Current lesson' : 'Locked'
                            }`}
                          >
                            <span className="node-icon">{isCompleted ? '✓' : isLocked ? '🔒' : item.order}</span>
                            <span className="node-pulse" />
                          </button>
                          <div className="node-label-card">
                            <span className="node-title">{item.title}</span>
                            <span className="node-subtitle">
                              {isCompleted ? 'Completed (+25 XP)' : isCurrent ? 'Start Exercise' : 'Locked'}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </section>
              )
            })}
          </div>
        </main>
      ) : (
        /* ── BITE-SIZED LESSON EXERCISE SCREEN ───────────────────────────── */
        <main className="duo-exercise-stage" aria-label="Lesson content">
          {/* Navigation & Header */}
          <div className="duo-exercise-topbar">
            <button className="duo-back-link" onClick={() => setView('map')}>
              ← Back to Course Path
            </button>
            {activeLesson && (
              <div className="duo-exercise-badge">
                LESSON {activeLesson.order} · {activeLesson.title.toUpperCase()}
              </div>
            )}
          </div>

          {isLoadingLesson ? (
            <div className="duo-card text-center py-12" role="status" aria-label="Loading lesson">
              <h2>Loading exercise…</h2>
            </div>
          ) : activeLesson ? (
            <div className="duo-exercise-card">
              {/* Question & Concept */}
              <div className="duo-instruction-box">
                <h2 className="duo-exercise-title">{activeLesson.title}</h2>
                <p className="duo-exercise-instruction">{activeLesson.description}</p>
              </div>

              {/* Code Editor */}
              <div className="duo-editor-container">
                <div className="duo-editor-top">
                  <span>exercise.py</span>
                  <span>Python 3.12</span>
                </div>
                <div className="duo-editor-body">
                  <LineNumbers code={code} />
                  <textarea
                    ref={editorRef}
                    className="duo-textarea"
                    spellCheck={false}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    onKeyDown={handleEditorKeyDown}
                    disabled={isRunning}
                    placeholder="Write your Python code here…"
                    aria-label="Code editor — use Ctrl+Enter to run"
                  />
                </div>
              </div>

              {/* Immediate Test Feedback */}
              {results && (
                <div
                  ref={resultsRef}
                  className={`duo-feedback-panel ${allPassed ? 'success' : 'error'}`}
                  role="region"
                  aria-label="Test results"
                >
                  <div className="duo-feedback-title">
                    <span>
                      {allPassed
                        ? `✓ All ${results.length} checks passed!`
                        : `× ${failedRequired.length} of ${results.filter((r) => r.required).length} required checks failed`}
                    </span>
                  </div>
                  <div className="duo-feedback-msg">
                    {allPassed ? (
                      <p>Outstanding work! Click below to continue your streak.</p>
                    ) : (
                      <p>Review the failing details below or request an AI hint.</p>
                    )}
                  </div>
                  <div className="duo-test-results-list">
                    {results.map((r) => (
                      <div key={r.name} className="result-row">
                        <span role="img" aria-label={r.passed ? 'Passed' : 'Failed'} className={r.passed ? 'pass-icon' : 'fail-icon'}>
                          {r.passed ? '✓' : '×'}
                        </span>
                        <span className="test-name">{r.name}</span>
                        {r.error && <span className="test-error-detail">{r.error}</span>}
                        {!r.required && <span className="opt-badge">opt</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Tutor Coach Feedback Display */}
              <aside aria-label="Tutor feedback">
                <div className="duo-tutor-box" role="status" aria-label="Tutor feedback">
                  <div className="duo-tutor-avatar">p</div>
                  <div className="duo-tutor-content">
                    <div className="duo-tutor-name">Tutor Guide ({currentProviderStatus?.name || selectedProvider})</div>
                    <div className="duo-tutor-text">
                      {isTutorLoading
                        ? 'Thinking…'
                        : feedback ?? (isAiAvailable ? 'Run your code or ask for a hint!' : currentProviderStatus?.reason || 'Selected provider is unconfigured.')}
                    </div>
                  </div>
                </div>
                {!isAiAvailable && (
                  <p className="ai-unavailable-note">
                    {currentProviderStatus?.reason || 'Selected provider is unconfigured.'} Tests always work offline.
                  </p>
                )}
              </aside>

              {/* Notes */}
              <div className="session-notes">
                <div className="notes-input-row">
                  <input
                    type="text"
                    placeholder="Add a learning note…"
                    value={noteInput}
                    onChange={(e) => setNoteInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addNote()
                      }
                    }}
                    aria-label="Session note"
                    className="duo-note-input"
                  />
                  <button onClick={addNote} aria-label="Add note" className="duo-button duo-button-primary duo-btn-sm">
                    + Note
                  </button>
                </div>
                {sessionNotes.length > 0 && (
                  <ul className="notes-list">
                    {sessionNotes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : null}

          {/* Bottom Sticky Action Footer */}
          <footer className="duo-footer-bar">
            <button
              id="hint-button"
              className="duo-button duo-button-secondary"
              onClick={askTutor}
              disabled={!aiEnabled || !isAiAvailable || isTutorLoading || isRunning}
              aria-label={
                !isAiAvailable
                  ? 'AI tutor unavailable'
                  : !aiEnabled
                  ? 'AI tutor is paused'
                  : 'Request a hint'
              }
            >
              {isTutorLoading
                ? 'Getting Hint…'
                : !isAiAvailable
                ? 'AI tutor unavailable'
                : !aiEnabled
                ? 'AI tutor is paused'
                : 'Request a hint'}
            </button>

            <button
              id="run-tests-button"
              className="duo-button duo-button-primary"
              onClick={runTests}
              disabled={isRunning || isLoadingLesson}
              aria-label="Run code"
            >
              {isRunning ? 'Checking…' : 'Check Code'}
            </button>
          </footer>

          {/* Celebratory Completion Modal Overlay */}
          {showCompletionModal && (
            <div className="duo-modal-overlay">
              <div className="duo-completion-card">
                <div className="modal-icon-header">🎉</div>
                <h2 className="modal-title">LESSON COMPLETE!</h2>
                <p className="modal-subtitle">{activeLesson?.title}</p>
                <div className="xp-reward-badge">+25 XP</div>
                <button
                  className="duo-button duo-button-primary duo-btn-full"
                  onClick={() => {
                    setShowCompletionModal(false)
                    setView('map')
                  }}
                >
                  Continue Learning →
                </button>
              </div>
            </div>
          )}
        </main>
      )}
    </div>
  )
}

export default App
