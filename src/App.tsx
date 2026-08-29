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

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getHintLabel(level: number): string {
  if (level === 1) return 'First hint'
  if (level === 2) return 'Second hint'
  if (level === 3) return 'Third hint'
  return 'Final hint'
}

function getHintButtonText(level: number): string {
  if (level === 1) return 'Ask for a hint'
  if (level === 2) return 'Ask for another hint'
  if (level === 3) return 'Ask for a more specific hint'
  return 'Show me the approach'
}

// ─── Line Numbers ─────────────────────────────────────────────────────────────
function LineNumbers({
  code,
  contentRef,
}: {
  code: string
  contentRef: React.RefObject<HTMLDivElement | null>
}) {
  const lines = (code ?? '').split('\n')
  return (
    <div className="line-numbers" aria-hidden="true">
      <div ref={contentRef} className="line-numbers-content">
        {lines.map((_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
    </div>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────
function App() {
  const [lessons, setLessons] = useState<LessonSummary[]>([])
  const [lesson, setLesson] = useState<Lesson | null>(null)
  const [code, setCode] = useState('')
  const [results, setResults] = useState<TestResult[] | null>(null)
  const [hintLevel, setHintLevel] = useState(1)
  const [feedback, setFeedback] = useState(
    'Run your tests to get feedback from the local sandbox.'
  )
  const [aiEnabled, setAiEnabled] = useState(true)
  const [aiAvailable, setAiAvailable] = useState(false)
  const [previousHints, setPreviousHints] = useState<string[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [isLoadingLesson, setIsLoadingLesson] = useState(false)
  const [isTutorLoading, setIsTutorLoading] = useState(false)
  const [showCompletion, setShowCompletion] = useState(false)
  const [sessionNotes, setSessionNotes] = useState<string[]>([])
  const [noteInput, setNoteInput] = useState('')
  const [backendError, setBackendError] = useState(false)

  const resultsRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<HTMLTextAreaElement>(null)
  const gutterContentRef = useRef<HTMLDivElement>(null)

  const scrollToResults = useCallback(() => {
    resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [])

  const syncLineNumbers = useCallback((scrollTop: number) => {
    if (gutterContentRef.current) {
      gutterContentRef.current.style.transform = `translateY(-${scrollTop}px)`
    }
  }, [])

  const resetEditorScroll = useCallback(() => {
    if (editorRef.current) editorRef.current.scrollTop = 0
    syncLineNumbers(0)
  }, [syncLineNumbers])

  // ── Initial data load ──────────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      setIsLoadingLesson(true)
      try {
        const summariesResponse = await fetch('http://localhost:8000/api/lessons')
        if (!summariesResponse.ok) throw new Error('Lesson service unavailable')
        const summaries = (await summariesResponse.json()) as LessonSummary[]
        if (summaries.length === 0) throw new Error('No lessons available')
        setLessons(summaries)
        const current =
          summaries.find((l) => l.status === 'current') ?? summaries[0]
        const lessonResponse = await fetch(`http://localhost:8000/api/lessons/${current.id}`)
        if (!lessonResponse.ok) throw new Error('Lesson unavailable')
        const selected = (await lessonResponse.json()) as Lesson
        setLesson(selected)
        setCode(selected.starter_code ?? '')
        requestAnimationFrame(resetEditorScroll)
        setBackendError(false)
      } catch {
        setBackendError(true)
        setFeedback(
          'The lesson service is unavailable. Start the local backend to continue.'
        )
      } finally {
        setIsLoadingLesson(false)
      }
    }
    load()
  }, [resetEditorScroll])

  // ── Ollama health check ────────────────────────────────────────────────────
  useEffect(() => {
    let latestRequestId = 0
    let activeController: AbortController | null = null

    const checkHealth = async () => {
      const requestId = ++latestRequestId
      const timestamp = new Date().toISOString()
      console.log(`[health:start] req #${requestId} at ${timestamp}`)

      if (activeController) {
        activeController.abort()
      }
      const controller = new AbortController()
      activeController = controller
      const timeoutId = setTimeout(() => controller.abort(), 5000)

      try {
        const response = await fetch('http://localhost:8000/api/health/ollama', {
          signal: controller.signal,
        })
        clearTimeout(timeoutId)

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = (await response.json()) as { available: boolean }
        console.log(`[health:response] req #${requestId} status ${response.status}:`, data)

        // Ignore out-of-order stale responses
        if (requestId === latestRequestId) {
          setAiAvailable(data.available)
          console.log(`[health:state] req #${requestId} set aiAvailable = ${data.available}`)
        }
      } catch (err: unknown) {
        clearTimeout(timeoutId)
        if (err instanceof Error && err.name === 'AbortError') {
          console.log(`[health:aborted] req #${requestId}`)
          return
        }
        console.log(`[health:error] req #${requestId}:`, err)
        if (requestId === latestRequestId) {
          setAiAvailable(false)
          console.log(`[health:state] req #${requestId} set aiAvailable = false (error)`)
        }
      }
    }

    checkHealth()
    const interval = setInterval(checkHealth, 10000)

    return () => {
      clearInterval(interval)
      if (activeController) {
        activeController.abort()
      }
    }
  }, [])

  // ── Navigate to lesson ─────────────────────────────────────────────────────
  const loadLesson = useCallback(async (item: LessonSummary) => {
    if (item.status === 'locked') {
      setFeedback('Complete earlier lessons to unlock this one.')
      return
    }
    setIsLoadingLesson(true)
    try {
      const response = await fetch(`http://localhost:8000/api/lessons/${item.id}`)
      if (!response.ok) throw new Error('Lesson unavailable')
      const selected = (await response.json()) as Lesson
      setLesson(selected)
      setCode(selected.starter_code ?? '')
      setResults(null)
      setPreviousHints([])
      setHintLevel(1)
      setShowCompletion(false)
      setSessionNotes([])
      setNoteInput('')
      setFeedback('Run your tests to get feedback from the local sandbox.')
      setTimeout(() => {
        resetEditorScroll()
        editorRef.current?.focus()
      }, 50)
    } catch {
      setFeedback('Failed to load lesson. Please try again.')
    } finally {
      setIsLoadingLesson(false)
    }
  }, [resetEditorScroll])

  // ── Run tests ──────────────────────────────────────────────────────────────
  const runTests = useCallback(async () => {
    if (!lesson) return
    setIsRunning(true)
    setFeedback('Running your code in the sandbox\u2026')
    try {
      const response = await fetch(
        `http://localhost:8000/api/lessons/${lesson.id}/run`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code }),
        }
      )
      if (!response.ok) throw new Error('Sandbox unavailable')
      const execution = (await response.json()) as {
        passed: boolean
        completed: boolean
        tests: TestResult[]
      }
      setResults(execution.tests)

      if (execution.completed) {
        setShowCompletion(true)
        setFeedback('\uD83C\uDF89 Lesson complete! Great work. The next lesson is now unlocked.')
      } else if (execution.passed) {
        setFeedback('\u2713 All required tests passed. You\'re on the right track!')
      } else {
        const failed = execution.tests.filter((t) => !t.passed && t.required)
        setFeedback(
          failed.length > 0
            ? `\u2717 ${failed.length} test${failed.length > 1 ? 's' : ''} failed. Start with the first failing test above.`
            : '\u2717 Some tests failed. Check the results above and try again.'
        )
      }

      const summariesResponse = await fetch('http://localhost:8000/api/lessons')
      if (!summariesResponse.ok) throw new Error('Lesson list unavailable')
      const summaries = (await summariesResponse.json()) as LessonSummary[]
      setLessons(summaries)
      setTimeout(scrollToResults, 100)
    } catch {
      setFeedback('The sandbox is unavailable. Your code was not graded.')
    } finally {
      setIsRunning(false)
    }
  }, [lesson, code, scrollToResults])

  // ── Ask tutor ──────────────────────────────────────────────────────────────
  const askTutor = useCallback(async () => {
    if (!lesson || !aiEnabled || !aiAvailable) return
    setIsTutorLoading(true)
    setFeedback('Getting a hint from your tutor\u2026')
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 50000)
    try {
      const response = await fetch('http://localhost:8000/api/tutor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          lesson_id: lesson.id,
          lesson_title: lesson.title,
          instructions: lesson.description,
          code,
          test_results: results ?? [],
          previous_hints: previousHints,
          hint_level: hintLevel,
          session_id: 'default',
          solution_requested: false,
        }),
      })
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`)
      }
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
      setFeedback(
        'AI tutoring is unavailable right now. Deterministic tests are still available.'
      )
    } finally {
      clearTimeout(timeoutId)
      setIsTutorLoading(false)
    }
  }, [lesson, aiEnabled, aiAvailable, code, results, previousHints, hintLevel])

  // ── Tab key & Ctrl+Enter handler ───────────────────────────────────────────
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

  // ── Session notes ──────────────────────────────────────────────────────────
  const addNote = useCallback(() => {
    const trimmed = noteInput.trim()
    if (!trimmed) return
    setSessionNotes((n) => [...n, trimmed])
    setNoteInput('')
  }, [noteInput])

  const goToNextLesson = useCallback(async () => {
    const next = lessons.find((l) => l.status === 'current')
    if (next) await loadLesson(next)
  }, [lessons, loadLesson])

  // ── Derived ────────────────────────────────────────────────────────────────
  const completedCount = lessons.filter((l) => l.status === 'completed').length
  const progressPct = lessons.length ? (completedCount / lessons.length) * 100 : 0
  const allPassed = results !== null && results.length > 0 && results.every((r) => r.passed || !r.required)
  const failedRequired = results?.filter((r) => !r.passed && r.required) ?? []
  const hintDisabled = !aiEnabled || !aiAvailable || !lesson || isTutorLoading || isRunning

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <main className="app-shell">
      <header className="topbar" role="banner">
        <div className="brand-mark" aria-hidden="true"><span>p</span></div>
        <div className="brand-copy">
          <strong>patchwork</strong>
          <small>local coding tutor</small>
        </div>
        <div className="topbar-status" aria-live="polite">
          <span className={`status-dot ${aiAvailable ? 'on' : ''}`} aria-hidden="true" />
          {aiAvailable ? 'Ollama ready' : 'Ollama offline'}
        </div>
        <button
          className={`ai-toggle ${aiEnabled ? 'active' : ''}`}
          aria-pressed={aiEnabled}
          aria-label={aiEnabled ? 'AI tutor on — click to pause' : 'AI tutor off — click to enable'}
          onClick={() => setAiEnabled((e) => !e)}
        >
          {aiEnabled ? '◉ AI on' : '◯ AI off'}
        </button>
        <div className="avatar" aria-hidden="true">AM</div>
      </header>

      {backendError && (
        <div className="backend-error-banner" role="alert">
          <span aria-hidden="true">⚠️</span>
          <span>
            Backend unavailable — run <code>uvicorn backend.main:app --reload</code> then{' '}
            <button onClick={() => window.location.reload()} className="inline-link">Try again</button>
          </span>
        </div>
      )}

      <div className="workspace">
        {/* Lesson nav */}
        <aside className="lesson-nav" aria-label="Course navigation">
          <div className="eyebrow">Python foundations</div>
          <h1>Build your<br /><em>thinking.</em></h1>
          <p className="nav-intro">A quiet place to practice, make mistakes, and understand why.</p>

          <div className="progress-label">
            <span>Course progress</span>
            <strong>{completedCount} / {lessons.length}</strong>
          </div>
          <div
            className="progress-track"
            role="progressbar"
            aria-valuenow={completedCount}
            aria-valuemin={0}
            aria-valuemax={lessons.length}
            aria-label="Course progress"
          >
            <span style={{ width: `${progressPct}%` }} />
          </div>

          <nav aria-label="Lessons">
            {lessons.map((item) => {
              const isActive = lesson?.id === item.id
              const statusLabel =
                item.status === 'current' ? (isActive ? 'Current lesson' : 'Available')
                : item.status === 'completed' ? 'Completed'
                : 'Locked'
              return (
                <button
                  key={item.id}
                  id={`lesson-nav-${item.id}`}
                  className={`lesson-item ${item.status}${isActive ? ' active' : ''}`}
                  onClick={() => loadLesson(item)}
                  disabled={item.status === 'locked' || isLoadingLesson}
                  aria-current={isActive ? 'page' : undefined}
                  aria-label={`${item.title} — ${statusLabel}`}
                  title={item.status === 'locked' ? 'Complete earlier lessons to unlock' : ''}
                >
                  <span className="lesson-number" aria-hidden="true">
                    {item.status === 'completed' ? '✓' : String(item.order).padStart(2, '0')}
                  </span>
                  <span className="lesson-detail">
                    <strong>{item.title}</strong>
                    <small>{statusLabel}</small>
                  </span>
                  <span className="lesson-meta">
                    {item.status === 'locked' ? '🔒' : `${item.duration_minutes}m`}
                  </span>
                </button>
              )
            })}
          </nav>

          <div className="privacy-note">
            <span aria-hidden="true">⏁</span>
            <div>
              <strong>Runs on your machine</strong>
              <small>Your code stays here. Always.</small>
            </div>
          </div>
        </aside>

        {/* Lesson view */}
        <section className="lesson-view" aria-label="Lesson content">
          {isLoadingLesson ? (
            <div className="loading-state" role="status" aria-label="Loading lesson">
              <div className="loading-spinner" aria-hidden="true" />
              <p>Loading lesson…</p>
            </div>
          ) : (
            <>
              <div className="lesson-heading">
                <div>
                  <div className="eyebrow warm">
                    Lesson {lesson?.order ?? '—'} <span aria-hidden="true">•</span> {lesson?.difficulty ?? ''}
                  </div>
                  <h2>{lesson?.title ?? 'Loading lesson'}</h2>
                </div>
                <span className="lesson-time" aria-label={`${lesson?.duration_minutes} minute lesson`}>
                  ◷ {lesson?.duration_minutes ?? '—'} min
                </span>
              </div>

              {showCompletion && (
                <div className="completion-banner" role="status" aria-live="polite">
                  <div className="completion-content">
                    <span className="completion-icon" aria-hidden="true">🎉</span>
                    <div>
                      <strong>Lesson Complete!</strong>
                      <p>Great work! The next lesson is now unlocked.</p>
                    </div>
                  </div>
                  <button className="next-lesson-button" onClick={goToNextLesson} disabled={isLoadingLesson}>
                    Next Lesson →
                  </button>
                </div>
              )}

              {lesson ? <div className="instruction">
                <span className="step-tag">YOUR TURN</span>
                <p>{lesson.description}</p>
              </div> : <div className="lesson-empty-state" role="status">
                <strong>No lesson is available yet.</strong>
                <p>Check that the local lesson service is running, then try again.</p>
                <button className="secondary-button" onClick={() => window.location.reload()}>Try again</button>
              </div>}

              <div className="editor-card">
                <div className="editor-top">
                  <span><i className="file-dot" aria-hidden="true" />exercise.py</span>
                  <span className="editor-label">Python 3.12</span>
                  <span className="line-count" aria-label={`${(code ?? '').split('\n').length} lines`}>
                    {(code ?? '').split('\n').length} lines
                  </span>
                </div>
                <div className="editor-body">
                  <LineNumbers code={code} contentRef={gutterContentRef} />
                  <textarea
                    ref={editorRef}
                    spellCheck={false}
                    aria-label="Code editor — use Ctrl+Enter to run"
                    aria-multiline="true"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    onScroll={(e) => syncLineNumbers(e.currentTarget.scrollTop)}
                    disabled={!lesson || isRunning}
                    placeholder={isLoadingLesson ? 'Loading…' : 'Write your Python code here…'}
                    onKeyDown={handleEditorKeyDown}
                    autoCapitalize="off"
                    autoCorrect="off"
                    autoComplete="off"
                  />
                </div>
              </div>

              <div className="action-row">
                <button
                  id="run-tests-button"
                  className="run-button"
                  onClick={runTests}
                  disabled={!lesson || isRunning || isLoadingLesson}
                  aria-label="Run code and evaluate tests (Ctrl+Enter)"
                >
                  {isRunning ? (
                    <><span className="spinner" aria-hidden="true" />Running…</>
                  ) : (
                    <><span aria-hidden="true">▶</span>Run tests</>
                  )}
                </button>
                <span className="shortcut" aria-hidden="true">Ctrl <b>↵</b></span>
                <button
                  className="reset-button"
                  onClick={() => {
                    if (lesson) {
                      setCode(lesson.starter_code)
                      setResults(null)
                      setShowCompletion(false)
                      setFeedback('Starter code restored.')
                    }
                  }}
                  disabled={!lesson || isRunning || isLoadingLesson}
                  aria-label="Reset code to starter"
                >
                  Reset code
                </button>
              </div>

              {results && (
                <div
                  ref={resultsRef}
                  className={`test-results${allPassed ? ' all-passed' : ''}`}
                  aria-live="polite"
                  role="region"
                  aria-label="Test results"
                >
                  <div className="result-title">
                    <span>Local sandbox</span>
                    <span className={results.length === 0 ? 'badge warning' : allPassed ? 'badge success' : 'badge error'}>
                      {results.length === 0
                        ? 'No test results returned'
                        : allPassed
                        ? `All ${results.length} tests passed`
                        : `${failedRequired.length} of ${results.filter(r => r.required).length} required failed`}
                    </span>
                  </div>
                  {results.length === 0 && (
                    <p className="results-empty-message">The sandbox did not return individual tests. Try running your code again.</p>
                  )}
                  {results.map((r) => (
                    <div
                      key={r.name}
                      className={`result-row${!r.passed && r.required ? ' error' : r.passed ? ' passed' : ' optional-fail'}`}
                    >
                      <span className={r.passed ? 'check' : 'cross'} aria-label={r.passed ? 'Passed' : 'Failed'} role="img">
                        {r.passed ? '✓' : '×'}
                      </span>
                      <span className="result-name">{r.name}</span>
                      {!r.required && <span className="optional-badge">opt</span>}
                      <small className="result-detail">{r.error ?? r.description}</small>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </section>

        {/* Feedback panel */}
        <aside className="feedback-panel" aria-label="Tutor feedback">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">Your guide</div>
              <h3>Feedback</h3>
            </div>
            <span className="spark" aria-hidden="true">✦</span>
          </div>

          <div className="feedback-box" aria-live="polite" role="status" aria-label="Tutor feedback">
            <div className="tutor-avatar" aria-hidden="true">p</div>
            <p>{isTutorLoading ? 'Thinking…' : feedback}</p>
          </div>

          <div className="hint-heading">
            <span>Hint ladder</span>
            <small>{getHintLabel(hintLevel)}</small>
          </div>
          <div
            className="hint-track"
            role="progressbar"
            aria-valuenow={hintLevel - 1}
            aria-valuemin={0}
            aria-valuemax={4}
            aria-label={`Hint level ${hintLevel - 1} of 4`}
          >
            {[1, 2, 3, 4].map((level) => (
              <span key={level} className={level < hintLevel ? 'active' : ''} />
            ))}
          </div>

          <button
            id="hint-button"
            className="hint-button"
            onClick={askTutor}
            disabled={hintDisabled}
            aria-label={
              !aiAvailable ? 'AI tutor unavailable'
              : !aiEnabled ? 'AI tutor is paused'
              : `Request a hint — ${getHintButtonText(hintLevel)}`
            }
          >
            <span aria-hidden="true">✦</span>
            {isTutorLoading ? 'Getting hint…'
              : !aiEnabled ? 'AI is paused'
              : aiAvailable ? getHintButtonText(hintLevel)
              : 'AI unavailable'}
          </button>

          {!aiAvailable && (
            <p className="ai-unavailable-note">
              Start Ollama locally to enable AI hints. Tests always work offline.
            </p>
          )}

          <p className="hint-policy">
            Hints start conceptual and become more direct only when you need them. The tutor never runs your code.
          </p>

          <div className="session-notes">
            <div className="eyebrow">Session notes</div>
            {sessionNotes.length > 0 && (
              <ul className="notes-list">
                {sessionNotes.map((note, i) => <li key={i}>{note}</li>)}
              </ul>
            )}
            <div className="note-input-row">
              <input
                type="text"
                className="note-input"
                placeholder="Add a note…"
                value={noteInput}
                onChange={(e) => setNoteInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addNote() } }}
                aria-label="Session note"
              />
              <button
                className="add-note-button"
                onClick={addNote}
                disabled={!noteInput.trim()}
                aria-label="Add note"
              >+</button>
            </div>
          </div>
        </aside>
      </div>
    </main>
  )
}

export default App
