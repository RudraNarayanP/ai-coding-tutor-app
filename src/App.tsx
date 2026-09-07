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
  type?: 'learn' | 'practice' | 'checkpoint' | 'challenge'
  section_id?: string
  section_title?: string
  unit_id?: string
  unit_title?: string
  concept_id?: string
  concept_title?: string
  test_out_eligible?: boolean
}

type Exercise = {
  id: string
  title?: string
  type: string
  question?: string
  options?: string[]
  correct_answer?: string | string[] | Record<string, string>
  blanks?: string[]
  starter_code?: string
  solution_code?: string
  hints?: string[]
  xp_reward?: number
  explanation?: string
}

type SubLesson = {
  id: string
  title: string
  description?: string
  order: number
  exercises: Exercise[]
}

type Lesson = {
  id: string
  title: string
  description: string
  order: number
  difficulty: string
  duration_minutes: number
  starter_code: string
  type?: 'learn' | 'practice' | 'checkpoint' | 'challenge'
  section_id?: string
  section_title?: string
  unit_id?: string
  unit_title?: string
  concept_id?: string
  concept_title?: string
  test_out_eligible?: boolean
  concepts?: string[]
  prerequisites?: string[]
  learning_objectives?: string[]
  sublessons?: SubLesson[]
  mastery_exam?: Exercise[]
  xp_reward?: number
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

type CourseSummary = {
  id: string
  title: string
  language: string
  lesson_count: number
  completed_count: number
}

type ProvidersOverview = {
  current_provider: string
  fallback_provider: string | null
  providers: ProviderStatus[]
}

// ─── Line Numbers ─────────────────────────────────────────────────────────────
function LineNumbers({
  code,
  contentRef,
}: {
  code: string
  contentRef?: React.RefObject<HTMLDivElement | null>
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

// ─── Audio Helper ──────────────────────────────────────────────────────────────
function playFeedbackSound(type: 'success' | 'error', enabled: boolean) {
  if (!enabled) return
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    if (!AudioCtx) return
    const ctx = new AudioCtx()
    if (ctx.state === 'suspended') {
      ctx.resume()
    }
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
    } else {
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
    }
  } catch {
    // AudioContext silently handled
  }
}

// ─── App Component ────────────────────────────────────────────────────────────
function App() {
  const [courses, setCourses] = useState<CourseSummary[]>([])
  const [selectedLanguage, setSelectedLanguage] = useState<string>(() => {
    return localStorage.getItem('patchwork_active_language') || 'python'
  })
  const [lessons, setLessons] = useState<LessonSummary[]>([])
  const [lesson, setLesson] = useState<Lesson | null>(null)
  const [code, setCode] = useState('')
  const [results, setResults] = useState<TestResult[] | null>(null)
  const [hintLevel, setHintLevel] = useState(1)
  const [feedback, setFeedback] = useState(
    'Run your code to get immediate feedback from the local sandbox.'
  )
  const [aiEnabled, setAiEnabled] = useState(true)
  const [soundEnabled, setSoundEnabled] = useState<boolean>(() => {
    const saved = localStorage.getItem('patchwork_sound_enabled')
    return saved !== null ? saved === 'true' : true
  })
  const [providersOverview, setProvidersOverview] = useState<ProvidersOverview | null>(null)
  const [selectedProvider, setSelectedProvider] = useState<string>('ollama')
  const [previousHints, setPreviousHints] = useState<string[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [isLoadingLesson, setIsLoadingLesson] = useState(false)
  const [isTutorLoading, setIsTutorLoading] = useState(false)
  const [showCompletion, setShowCompletion] = useState(false)
  const [sessionNotes, setSessionNotes] = useState<string[]>([])
  const [noteInput, setNoteInput] = useState('')
  const [backendError, setBackendError] = useState(false)
  const [xp, setXp] = useState(0)
  const [level, setLevel] = useState(1)
  const [xpGainPopup, setXpGainPopup] = useState<number | null>(null)
  const [activeSubLessonIndex, setActiveSubLessonIndex] = useState(0)
  const [activeExerciseIndex, setActiveExerciseIndex] = useState(0)
  const [exerciseInput, setExerciseInput] = useState<any>({})
  const [showTestOutModal, setShowTestOutModal] = useState(false)
  const [testOutSubmissions, setTestOutSubmissions] = useState<Record<string, any>>({})
  const [testOutResult, setTestOutResult] = useState<any>(null)

  const triggerXpGain = useCallback((amount: number) => {
    if (amount > 0) {
      setXpGainPopup(amount)
      setTimeout(() => setXpGainPopup(null), 1500)
    }
  }, [])

  const resultsRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<HTMLTextAreaElement>(null)
  const gutterContentRef = useRef<HTMLDivElement>(null)

  const currentProviderStatus = providersOverview?.providers?.find((p) => p.provider === selectedProvider)
  const isAiAvailable = currentProviderStatus?.available ?? false

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

  // ── Save Sound Preference ─────────────────────────────────────────────────
  const toggleSound = useCallback(() => {
    setSoundEnabled((prev) => {
      const next = !prev
      localStorage.setItem('patchwork_sound_enabled', String(next))
      return next
    })
  }, [])

  // ── Save Draft Code to localStorage ────────────────────────────────────────
  useEffect(() => {
    if (lesson?.id && code !== undefined) {
      localStorage.setItem(`patchwork_code_${lesson.id}`, code)
    }
  }, [lesson?.id, code])

  // ── Load Course & Lessons Data ──────────────────────────────────────────────
  const loadCourseData = useCallback(async (lang: string) => {
    setIsLoadingLesson(true)
    try {
      // 1. Fetch available courses
      const coursesRes = await fetch('/api/courses')
      if (coursesRes.ok) {
        const coursesData = (await coursesRes.json()) as CourseSummary[]
        setCourses(coursesData)
      }

      // 2. Select course on backend
      await fetch('/api/courses/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: lang }),
      })

      // 3. Fetch lessons for selected language
      const summariesResponse = await fetch(`/api/lessons?language=${encodeURIComponent(lang)}`)
      if (!summariesResponse.ok) throw new Error('Lesson service unavailable')
      const summariesRaw = await summariesResponse.json()
      const summaries: LessonSummary[] = Array.isArray(summariesRaw) ? summariesRaw : []
      if (summaries.length === 0) throw new Error('No lessons available')
      setLessons(summaries)

      const completedIds = summaries.filter((l) => l.status === 'completed').map((l) => l.id)
      localStorage.setItem(`patchwork_completed_lessons_${lang}`, JSON.stringify(completedIds))

      // Restore last active lesson if unlocked, otherwise current lesson
      const lastActiveId = localStorage.getItem(`patchwork_last_active_lesson_${lang}`)
      const targetSummary =
        (lastActiveId && summaries.find((l) => l.id === lastActiveId && l.status !== 'locked')) ||
        summaries.find((l) => l.status === 'current') ||
        summaries[0]

      const lessonResponse = await fetch(`/api/lessons/${targetSummary.id}`)
      if (!lessonResponse.ok) throw new Error('Lesson unavailable')
      const selected = (await lessonResponse.json()) as Lesson
      setLesson(selected)

      // Fetch progression (XP & level)
      const progRes = await fetch(`/api/progression?language=${encodeURIComponent(lang)}`)
      if (progRes.ok) {
        const prog = await progRes.json()
        setXp(prog.xp || 0)
        setLevel(prog.level || 1)
      }

      // Restore draft code if available, else starter_code
      const draftCode = localStorage.getItem(`patchwork_code_${selected.id}`)
      setCode(draftCode !== null ? draftCode : selected.starter_code ?? '')
      localStorage.setItem(`patchwork_last_active_lesson_${lang}`, selected.id)

      setResults(null)
      setShowCompletion(false)
      setActiveSubLessonIndex(0)
      setActiveExerciseIndex(0)
      setExerciseInput({})
      requestAnimationFrame(resetEditorScroll)
      setBackendError(false)
    } catch {
      setBackendError(true)
      setFeedback('The lesson service is unavailable. Start the local backend to continue.')
    } finally {
      setIsLoadingLesson(false)
    }
  }, [resetEditorScroll])

  useEffect(() => {
    loadCourseData(selectedLanguage)
  }, [selectedLanguage, loadCourseData])

  const handleCourseChange = async (lang: string) => {
    if (lang === selectedLanguage) return
    setSelectedLanguage(lang)
    localStorage.setItem('patchwork_active_language', lang)
  }

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
      // Ignore selection errors
    }
  }

  // ── Navigate to Lesson ──────────────────────────────────────────────────────
  const loadLesson = useCallback(
    async (item: LessonSummary) => {
      if (item.status === 'locked') {
        setFeedback('Complete earlier lessons to unlock this one.')
        return
      }
      setIsLoadingLesson(true)
      try {
        const response = await fetch(`/api/lessons/${item.id}`)
        if (!response.ok) throw new Error('Lesson unavailable')
        const selected = (await response.json()) as Lesson
        setLesson(selected)

        const draftCode = localStorage.getItem(`patchwork_code_${selected.id}`)
        setCode(draftCode !== null ? draftCode : selected.starter_code ?? '')
        localStorage.setItem('patchwork_last_active_lesson', selected.id)

        setResults(null)
        setPreviousHints([])
        setHintLevel(1)
        setShowCompletion(false)
        setSessionNotes([])
        setNoteInput('')
        setFeedback('Run your code to get immediate feedback from the local sandbox.')
        setTimeout(() => {
          resetEditorScroll()
          editorRef.current?.focus()
        }, 50)
      } catch {
        setFeedback('Failed to load lesson. Please try again.')
      } finally {
        setIsLoadingLesson(false)
      }
    },
    [resetEditorScroll]
  )

  // ── Run Code in Sandbox ────────────────────────────────────────────────────
  const runTests = useCallback(async () => {
    if (!lesson) return
    setIsRunning(true)
    setFeedback('Checking your code in the sandbox…')
    try {
      const response = await fetch(`/api/lessons/${lesson.id}/run`, {
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

      const passedAllRequired =
        execution.tests.length > 0 &&
        execution.tests.every((t) => t.passed || !t.required)

      playFeedbackSound(passedAllRequired ? 'success' : 'error', soundEnabled)

      if (execution.completed) {
        setShowCompletion(true)
        setFeedback('🎉 Great! Everything works. Next lesson is unlocked!')
        const progRes = await fetch(`/api/progression?language=${encodeURIComponent(selectedLanguage)}`)
        if (progRes.ok) {
          const prog = await progRes.json()
          if (prog.xp > xp) {
            triggerXpGain(prog.xp - xp)
          }
          setXp(prog.xp || 0)
          setLevel(prog.level || 1)
        }
      } else if (execution.passed) {
        setFeedback('✓ All required checks passed. You are on the right track!')
      } else {
        const failed = execution.tests.filter((t) => !t.passed && t.required)
        setFeedback(
          failed.length > 0
            ? `Not quite. ${failed.length} check${failed.length > 1 ? 's' : ''} failed. Check the details above.`
            : 'Some checks failed. Review your code and try again.'
        )
      }

      const summariesResponse = await fetch(`/api/lessons?language=${encodeURIComponent(selectedLanguage)}`)
      if (summariesResponse.ok) {
        const summariesRaw = await summariesResponse.json()
        const summaries: LessonSummary[] = Array.isArray(summariesRaw) ? summariesRaw : []
        setLessons(summaries)
        const completedIds = summaries.filter((l) => l.status === 'completed').map((l) => l.id)
        localStorage.setItem(`patchwork_completed_lessons_${selectedLanguage}`, JSON.stringify(completedIds))
      }
      const coursesRes = await fetch('/api/courses')
      if (coursesRes.ok) {
        setCourses((await coursesRes.json()) as CourseSummary[])
      }
      setTimeout(scrollToResults, 100)
    } catch {
      setFeedback('The sandbox is unavailable. Your code was not graded.')
    } finally {
      setIsRunning(false)
    }
  }, [lesson, code, soundEnabled, scrollToResults])

  // ── Ask Tutor for Hint ─────────────────────────────────────────────────────
  const askTutor = useCallback(async () => {
    if (!lesson || !aiEnabled) return
    setIsTutorLoading(true)
    setFeedback('Getting a hint from your tutor…')
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 50000)
    try {
      const response = await fetch('/api/tutor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          lesson_id: lesson.id,
          lesson_title: lesson.title,
          unit_title: lesson.unit_title ?? '',
          concept_title: lesson.concept_title ?? '',
          prerequisites: lesson.prerequisites ?? [],
          instructions: lesson.description,
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
      setFeedback('AI tutoring is unavailable right now. Deterministic tests are still available.')
    } finally {
      clearTimeout(timeoutId)
      setIsTutorLoading(false)
    }
  }, [lesson, aiEnabled, code, results, previousHints, hintLevel])

  // ── View Solution ──────────────────────────────────────────────────────────
  const askSolution = useCallback(async () => {
    if (!lesson) return
    setIsLoadingLesson(true)
    setFeedback('Inserting solution into editor…')
    try {
      const response = await fetch(`/api/lessons/${lesson.id}/solution`)
      if (!response.ok) throw new Error('Solution unavailable')
      const data = (await response.json()) as { solution_code: string }
      if (data.solution_code) {
        setCode(data.solution_code)
        setFeedback('💡 Solution inserted into editor! Click "Run code" to verify.')
      } else {
        setFeedback('Solution unavailable for this exercise.')
      }
    } catch {
      setFeedback('Solution unavailable right now. Try reviewing starter code.')
    } finally {
      setIsLoadingLesson(false)
    }
  }, [lesson])

  // ── Exercise Submission Handler (MCQ, Fill Blank, Code Completion, etc.) ────
  const submitSubLessonExercise = useCallback(
    async (exercise: Exercise, sublessonId?: string) => {
      if (!lesson) return
      setIsRunning(true)
      setFeedback('Grading exercise…')
      try {
        const payload = exercise.type === 'code' ? { code } : exerciseInput[exercise.id] || {}
        const response = await fetch(`/api/lessons/${lesson.id}/submit-exercise`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            exercise_id: exercise.id,
            sublesson_id: sublessonId,
            payload,
          }),
        })
        if (!response.ok) throw new Error('Grading failed')
        const result = await response.json()

        playFeedbackSound(result.passed ? 'success' : 'error', soundEnabled)

        if (result.passed) {
          if (result.xp_awarded > 0) {
            triggerXpGain(result.xp_awarded)
          }
          setXp(result.total_xp || xp)
          setLevel(result.level || level)
          setFeedback(`✓ ${result.feedback} ${result.xp_awarded > 0 ? `+${result.xp_awarded} XP!` : ''}`)

          // Refresh lesson & progression summaries
          const summariesResponse = await fetch(`/api/lessons?language=${encodeURIComponent(selectedLanguage)}`)
          if (summariesResponse.ok) {
            const summariesRaw = await summariesResponse.json()
            setLessons(Array.isArray(summariesRaw) ? summariesRaw : [])
          }
        } else {
          setFeedback(`Not quite: ${result.feedback}`)
        }
      } catch {
        setFeedback('Failed to submit exercise. Please try again.')
      } finally {
        setIsRunning(false)
      }
    },
    [lesson, code, exerciseInput, soundEnabled, triggerXpGain, xp, level, selectedLanguage]
  )

  // ── Test-Out Mastery Exam Handler ───────────────────────────────────────────
  const handleTestOutSubmit = useCallback(async () => {
    if (!lesson) return
    setIsRunning(true)
    try {
      const res = await fetch(`/api/lessons/${lesson.id}/test-out`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ submissions: testOutSubmissions }),
      })
      if (!res.ok) throw new Error('Test out failed')
      const data = await res.json()
      setTestOutResult(data)
      if (data.passed) {
        playFeedbackSound('success', soundEnabled)
        if (data.xp_awarded > 0) {
          triggerXpGain(data.xp_awarded)
        }
        setXp(data.total_xp || xp)
        setLevel(data.level || level)

        const summariesResponse = await fetch(`/api/lessons?language=${encodeURIComponent(selectedLanguage)}`)
        if (summariesResponse.ok) {
          const summariesRaw = await summariesResponse.json()
          setLessons(Array.isArray(summariesRaw) ? summariesRaw : [])
        }
      } else {
        playFeedbackSound('error', soundEnabled)
      }
    } catch {
      setFeedback('Failed to evaluate mastery exam.')
    } finally {
      setIsRunning(false)
    }
  }, [lesson, testOutSubmissions, soundEnabled, triggerXpGain, xp, level, selectedLanguage])

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  const handleEditorKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.shiftKey || e.ctrlKey) && e.key === 'Enter') {
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

  const goToNextLesson = useCallback(async () => {
    const next = lessons.find((l) => l.status === 'current')
    if (next) await loadLesson(next)
  }, [lessons, loadLesson])

  // Group lessons by Section -> Unit
  const sectionsMap = new Map<
    string,
    { id: string; title: string; units: Map<string, { id: string; title: string; lessons: LessonSummary[] }> }
  >()
  const safeLessons = Array.isArray(lessons) ? lessons : []

  safeLessons.forEach((item) => {
    const secId = item.section_id || 'section-1'
    const secTitle = item.section_title || 'Section 1: Foundations'
    const uid = item.unit_id || 'unit-1'
    const utitle = item.unit_title || 'Unit 1'

    if (!sectionsMap.has(secId)) {
      sectionsMap.set(secId, { id: secId, title: secTitle, units: new Map() })
    }
    const secObj = sectionsMap.get(secId)!
    if (!secObj.units.has(uid)) {
      secObj.units.set(uid, { id: uid, title: utitle, lessons: [] })
    }
    secObj.units.get(uid)!.lessons.push(item)
  })

  const sectionGroupList = Array.from(sectionsMap.values()).map((sec) => ({
    id: sec.id,
    title: sec.title,
    units: Array.from(sec.units.values()),
  }))

  // Derived state
  const completedCount = safeLessons.filter((l) => l.status === 'completed').length
  const progressPct = safeLessons.length ? (completedCount / safeLessons.length) * 100 : 0
  const allPassed = results !== null && results.length > 0 && results.every((r) => r.passed || !r.required)
  const failedRequired = results?.filter((r) => !r.passed && r.required) ?? []
  const hintDisabled = !aiEnabled || !isAiAvailable || !lesson || isTutorLoading || isRunning

  return (
    <div className="duo-app">
      {/* Duolingo-style Top Header */}
      <header className="duo-header" role="banner">
        <div className="duo-brand">
          <div className="duo-logo-icon">p</div>
          <span>patchwork</span>
        </div>

        <div className="duo-header-progress">
          <div
            className="duo-progress-bar-bg"
            role="progressbar"
            aria-valuenow={completedCount}
            aria-valuemin={0}
            aria-valuemax={lessons.length}
            aria-label="Course progress"
          >
            <div className="duo-progress-bar-fill" style={{ width: `${progressPct}%` }} />
          </div>
        </div>

        <div className="duo-header-right">
          {/* XP & Level Badge */}
          <div className="duo-xp-badge" aria-label={`XP: ${xp}, Level: ${level}`}>
            <span>⚡ {xp} XP</span>
            <span style={{ fontSize: '12px', opacity: 0.8, marginLeft: '4px' }}>Lvl {level}</span>
            {xpGainPopup !== null && (
              <div className="xp-float-anim">+{xpGainPopup} XP!</div>
            )}
          </div>

          {/* AI Provider & Model Selector */}
          <div className="duo-provider-selector" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <select
              value={selectedProvider}
              onChange={(e) => handleProviderChange(e.target.value)}
              aria-label="Select AI Provider"
              style={{
                padding: '4px 8px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                fontSize: '13px',
                fontWeight: 700,
                background: '#fff',
              }}
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
            className="duo-button duo-button-secondary"
            style={{ padding: '6px 14px', fontSize: '13px' }}
            aria-label={soundEnabled ? 'Mute audio feedback' : 'Unmute audio feedback'}
            onClick={toggleSound}
            title={soundEnabled ? 'Mute audio' : 'Unmute audio'}
          >
            {soundEnabled ? '🔊 Sound' : '🔇 Sound'}
          </button>

          <button
            className="duo-button duo-button-secondary"
            style={{ padding: '6px 14px', fontSize: '13px' }}
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

      {/* Main Learning Workspace */}
      <div className="duo-main-container">
        {/* Left Side Skill Tree Path */}
        <aside className="duo-sidebar" aria-label="Course navigation">
          {/* Course Language Switcher Tabs */}
          <div className="duo-course-selector" role="tablist" aria-label="Course language selector">
            {[
              { lang: 'python', label: 'Python' },
              { lang: 'java', label: 'Java' },
              { lang: 'cpp', label: 'C++' },
            ].map(({ lang, label }) => (
              <button
                key={lang}
                role="tab"
                aria-selected={selectedLanguage === lang}
                className={`duo-course-btn ${selectedLanguage === lang ? 'active' : ''}`}
                onClick={() => handleCourseChange(lang)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="duo-sidebar-title">
            {selectedLanguage === 'cpp' ? 'C++' : selectedLanguage === 'java' ? 'Java' : 'Python'} Path
          </div>

          <nav className="duo-path-list" aria-label="Lessons">
            {sectionGroupList.map((secGroup) => {
              const secTotal = secGroup.units.flatMap((u) => u.lessons).length
              const secDone = secGroup.units.flatMap((u) => u.lessons).filter((l) => l.status === 'completed').length

              return (
                <div key={secGroup.id} className="duo-section-block">
                  <div className="duo-section-banner">
                    <span className="duo-section-title">{secGroup.title}</span>
                    <span className="duo-section-progress">{secDone} / {secTotal}</span>
                  </div>

                  {secGroup.units.map((unitGroup) => (
                    <div key={unitGroup.id} className="duo-unit-block">
                      <div className="duo-unit-header">
                        <span className="duo-unit-title">{unitGroup.title}</span>
                      </div>
                      <div className="duo-unit-node-group">
                        {unitGroup.lessons.map((item) => {
                          const isActive = lesson?.id === item.id
                          const statusLabel =
                            item.status === 'current'
                              ? isActive
                                ? 'Current lesson'
                                : 'Available'
                              : item.status === 'completed'
                              ? 'Completed'
                              : 'Locked'

                          const iconSymbol =
                            item.status === 'completed'
                              ? '✓'
                              : item.type === 'challenge'
                              ? '⚡'
                              : item.type === 'practice'
                              ? '🔄'
                              : item.type === 'checkpoint'
                              ? '🏆'
                              : '📘'

                          return (
                            <button
                              key={item.id}
                              id={`lesson-nav-${item.id}`}
                              className={`duo-path-node ${item.status} ${item.type || 'learn'}${
                                isActive ? ' active' : ''
                              }`}
                              onClick={() => loadLesson(item)}
                              disabled={item.status === 'locked' || isLoadingLesson}
                              aria-current={isActive ? 'page' : undefined}
                              aria-label={`${item.title} — ${statusLabel}`}
                              title={item.title}
                            >
                              <span className="duo-node-icon">{iconSymbol}</span>
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )
            })}
          </nav>
        </aside>

        {/* Center Stage: Interactive Learning Moment */}
        <main className="duo-stage" aria-label="Lesson content">
          {isLoadingLesson ? (
            <div
              className="duo-card"
              style={{ textAlign: 'center', padding: '48px' }}
              role="status"
              aria-label="Loading lesson"
            >
              <h2>Loading exercise…</h2>
            </div>
          ) : lesson ? (
            <>
              {/* Lesson Question Card */}
              <div className="duo-card">
                <div className="duo-card-header">
                  <div className="duo-badge-group">
                    <span className={`duo-type-badge duo-type-${lesson.type || 'learn'}`}>
                      {(lesson.type || 'learn').toUpperCase()}
                    </span>
                    {lesson.section_title && (
                      <span className="duo-section-badge">{lesson.section_title}</span>
                    )}
                    {lesson.unit_title && (
                      <span className="duo-unit-badge">{lesson.unit_title}</span>
                    )}
                  </div>
                  <span className="duo-difficulty-badge">{lesson.difficulty}</span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h2 className="duo-lesson-title">{lesson.title}</h2>
                  {lesson.test_out_eligible && (
                    <button
                      className="duo-test-out-btn"
                      onClick={() => {
                        setTestOutSubmissions({})
                        setTestOutResult(null)
                        setShowTestOutModal(true)
                      }}
                      title="Jump ahead by taking the mastery exam"
                    >
                      ⚡ Test Out / Jump Ahead
                    </button>
                  )}
                </div>

                <p className="duo-instruction">{lesson.description}</p>

                {/* Sublesson Stepper */}
                {lesson.sublessons && lesson.sublessons.length > 0 && (
                  <div className="duo-sublesson-stepper" role="tablist" aria-label="Sublessons">
                    {lesson.sublessons.map((sub, sIdx) => (
                      <button
                        key={sub.id}
                        role="tab"
                        aria-selected={activeSubLessonIndex === sIdx}
                        className={`duo-step-item ${activeSubLessonIndex === sIdx ? 'active' : ''}`}
                        onClick={() => {
                          setActiveSubLessonIndex(sIdx)
                          setActiveExerciseIndex(0)
                        }}
                      >
                        Step {sIdx + 1}: {sub.title}
                      </button>
                    ))}
                  </div>
                )}

                {/* Render Active Exercise or Default Code Editor */}
                {(() => {
                  const currentSub = lesson.sublessons?.[activeSubLessonIndex]
                  const currentEx = currentSub?.exercises?.[activeExerciseIndex] || {
                    id: `${lesson.id}-ex-default`,
                    type: 'code',
                    question: lesson.description,
                  }

                  const exType = (currentEx.type || 'code').toLowerCase().trim() || 'code'

                  if (exType === 'mcq' || exType === 'true_false') {
                    const opts = currentEx.options && currentEx.options.length > 0
                      ? currentEx.options
                      : ['True', 'False']
                    const selectedVal = exerciseInput[currentEx.id]?.answer || ''

                    return (
                      <div className="exercise-interactive-box" style={{ margin: '16px 0' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: 800, marginBottom: '12px' }}>
                          {currentEx.question || currentEx.title || 'Choose the correct answer:'}
                        </h3>
                        <div className="exercise-options-grid">
                          {opts.map((opt) => (
                            <button
                              key={opt}
                              className={`exercise-option-btn ${selectedVal === opt ? 'selected' : ''}`}
                              onClick={() =>
                                setExerciseInput((prev: any) => ({
                                  ...prev,
                                  [currentEx.id]: { ...prev[currentEx.id], answer: opt },
                                }))
                              }
                            >
                              {opt}
                            </button>
                          ))}
                        </div>
                        <button
                          className="duo-button duo-button-primary"
                          style={{ marginTop: '16px', padding: '10px 20px', fontSize: '14px' }}
                          onClick={() => submitSubLessonExercise(currentEx, currentSub?.id)}
                          disabled={!selectedVal || isRunning}
                        >
                          Check Answer ✓
                        </button>
                      </div>
                    )
                  }

                  if (exType === 'fill_blank' || exType === 'code_completion' || exType === 'output_prediction') {
                    const val = exerciseInput[currentEx.id]?.answers?.[0] || exerciseInput[currentEx.id]?.answer || ''

                    return (
                      <div className="exercise-interactive-box" style={{ margin: '16px 0' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: 800, marginBottom: '12px' }}>
                          {currentEx.question || currentEx.title || 'Fill in the answer:'}
                        </h3>
                        {currentEx.starter_code && (
                          <pre style={{ background: '#1e293b', color: '#f1f5f9', padding: '12px', borderRadius: '8px', fontFamily: 'var(--font-mono)', fontSize: '14px', marginBottom: '12px' }}>
                            {currentEx.starter_code}
                          </pre>
                        )}
                        <div className="fill-blank-container">
                          <input
                            type="text"
                            className="fill-blank-input"
                            placeholder="Type your answer here…"
                            value={val}
                            onChange={(e) => {
                              const inputVal = e.target.value
                              setExerciseInput((prev: any) => ({
                                ...prev,
                                [currentEx.id]: { answer: inputVal, answers: [inputVal] },
                              }))
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                submitSubLessonExercise(currentEx, currentSub?.id)
                              }
                            }}
                          />
                        </div>
                        <button
                          className="duo-button duo-button-primary"
                          style={{ marginTop: '12px', padding: '10px 20px', fontSize: '14px' }}
                          onClick={() => submitSubLessonExercise(currentEx, currentSub?.id)}
                          disabled={!val || isRunning}
                        >
                          Check Answer ✓
                        </button>
                      </div>
                    )
                  }

                  // Default Code Editor Renderer
                  return (
                    <div className="duo-editor-container">
                      <div className="duo-editor-top">
                        <span>{selectedLanguage === 'java' ? 'Solution.java' : selectedLanguage === 'cpp' ? 'solution.cpp' : 'exercise.py'}</span>
                        <span>{selectedLanguage === 'java' ? 'Java 21' : selectedLanguage === 'cpp' ? 'C++ 20' : 'Python 3.12'}</span>
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
                          placeholder="Write your code here… (Press Shift+Enter or Ctrl+Enter to run)"
                          aria-label="Code editor — use Shift+Enter or Ctrl+Enter to run"
                        />
                      </div>
                    </div>
                  )
                })()}
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
                        ? `All ${results.length} tests passed`
                        : `${failedRequired.length} of ${results.filter((r) => r.required).length} required failed`}
                    </span>
                  </div>
                  <div className="duo-feedback-msg">
                    {allPassed ? (
                      <p>All checks passed. You master this concept!</p>
                    ) : (
                      <p>
                        {failedRequired.length} required check{failedRequired.length > 1 ? 's' : ''} failed. Review your code and run again.
                      </p>
                    )}
                  </div>
                  {results.map((r) => (
                    <div
                      key={r.name}
                      className="result-row"
                      style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '13px' }}
                    >
                      <span role="img" aria-label={r.passed ? 'Passed' : 'Failed'}>
                        {r.passed ? '✓' : '×'}
                      </span>
                      <span>{r.name}</span>
                      {!r.required && (
                        <span
                          className="opt"
                          style={{
                            fontSize: '10px',
                            background: 'rgba(0,0,0,0.1)',
                            padding: '1px 4px',
                            borderRadius: '3px',
                          }}
                        >
                          opt
                        </span>
                      )}
                    </div>
                  ))}
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
                        : feedback ?? (isAiAvailable ? 'Run your code or ask for a hint!' : currentProviderStatus?.reason || 'Provider unavailable.')}
                    </div>
                  </div>
                </div>
                {!isAiAvailable && (
                  <p className="ai-unavailable-note" style={{ marginTop: '8px', fontSize: '13px', color: '#64748b' }}>
                    {currentProviderStatus?.reason || 'Selected provider is unconfigured.'} Tests always work offline.
                  </p>
                )}
              </aside>

              {/* Celebratory Completion Overlay */}
              {showCompletion && (
                <div className="duo-feedback-panel success" style={{ marginTop: '16px' }}>
                  <div className="duo-feedback-title">
                    <span>🎉 Lesson Complete!</span>
                  </div>
                  <div className="duo-feedback-msg">
                    <p>Awesome work! You completed this exercise and unlocked the next step.</p>
                  </div>
                  <button className="duo-button duo-button-primary" onClick={goToNextLesson}>
                    Next Lesson →
                  </button>
                </div>
              )}

              {/* Session Notes Section */}
              <div className="session-notes" style={{ marginTop: '24px' }}>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="text"
                    placeholder="Add a note…"
                    value={noteInput}
                    onChange={(e) => setNoteInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addNote()
                      }
                    }}
                    aria-label="Session note"
                    style={{ flex: 1, padding: '8px 12px', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                  />
                  <button
                    onClick={addNote}
                    aria-label="Add note"
                    style={{ padding: '8px 16px', background: '#58cc02', color: '#fff', borderRadius: '8px', fontWeight: 800 }}
                  >
                    +
                  </button>
                </div>
                {sessionNotes.length > 0 && (
                  <ul style={{ marginTop: '12px', paddingLeft: '20px' }}>
                    {sessionNotes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          ) : null}
        </main>
      </div>

      {/* Test-Out Mastery Exam Modal */}
      {showTestOutModal && lesson && (
        <div className="modal-overlay" role="dialog" aria-label="Mastery Exam Modal">
          <div className="modal-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ fontSize: '22px', fontWeight: 800 }}>⚡ Mastery Exam: {lesson.title}</h2>
              <button
                onClick={() => setShowTestOutModal(false)}
                style={{ fontSize: '20px', fontWeight: 800, background: 'none', border: 'none', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>
            <p style={{ color: '#4a4e69', marginBottom: '20px' }}>
              Pass with 80%+ score to test out of this lesson and earn +100 XP!
            </p>

            {testOutResult ? (
              <div className={`duo-feedback-panel ${testOutResult.passed ? 'success' : 'error'}`}>
                <h3>{testOutResult.passed ? '🎉 Congratulations! You Mastered This Concept!' : 'Keep Practicing!'}</h3>
                <p>Score: {testOutResult.score_pct}% ({testOutResult.passed_count} / {testOutResult.total_questions} correct)</p>
                {testOutResult.passed ? (
                  <p style={{ fontWeight: 800 }}>+100 XP Earned! Next lessons unlocked.</p>
                ) : (
                  <div>
                    <p>Recommended areas to review:</p>
                    <ul>
                      {testOutResult.weak_areas?.map((wa: string, i: number) => (
                        <li key={i}>{wa}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <button
                  className="duo-button duo-button-primary"
                  style={{ marginTop: '16px' }}
                  onClick={() => setShowTestOutModal(false)}
                >
                  Close
                </button>
              </div>
            ) : (
              <div>
                {(lesson.mastery_exam && lesson.mastery_exam.length > 0
                  ? lesson.mastery_exam
                  : lesson.sublessons?.flatMap((s) => s.exercises) || []
                ).map((ex, idx) => (
                  <div key={ex.id} style={{ marginBottom: '20px', padding: '12px', border: '1px solid #cbd5e1', borderRadius: '8px' }}>
                    <h4 style={{ fontWeight: 800, marginBottom: '8px' }}>
                      Question {idx + 1}: {ex.question || ex.title}
                    </h4>
                    {ex.options && ex.options.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {ex.options.map((opt) => (
                          <label key={opt} style={{ display: 'flex', gap: '8px', alignItems: 'center', cursor: 'pointer' }}>
                            <input
                              type="radio"
                              name={`exam-${ex.id}`}
                              value={opt}
                              checked={testOutSubmissions[ex.id]?.answer === opt}
                              onChange={() =>
                                setTestOutSubmissions((prev) => ({
                                  ...prev,
                                  [ex.id]: { answer: opt },
                                }))
                              }
                            />
                            <span>{opt}</span>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <input
                        type="text"
                        placeholder="Your answer…"
                        style={{ width: '100%', padding: '8px 12px', border: '1px solid #cbd5e1', borderRadius: '6px' }}
                        value={testOutSubmissions[ex.id]?.answer || ''}
                        onChange={(e) => {
                          const val = e.target.value
                          setTestOutSubmissions((prev) => ({
                            ...prev,
                            [ex.id]: { answer: val, answers: [val] },
                          }))
                        }}
                      />
                    )}
                  </div>
                ))}

                <button
                  className="duo-button duo-button-primary"
                  style={{ width: '100%', marginTop: '16px' }}
                  onClick={handleTestOutSubmit}
                  disabled={isRunning}
                >
                  {isRunning ? 'Evaluating Exam…' : 'Submit Mastery Exam'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Bottom Sticky Action Bar */}
      <footer className="duo-footer-bar">
        <div className="duo-footer-left" style={{ display: 'flex', gap: '12px' }}>
          <button
            id="hint-button"
            className="duo-button duo-button-secondary"
            onClick={askTutor}
            disabled={hintDisabled}
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
            id="solution-button"
            className="duo-button duo-button-secondary duo-button-solution"
            onClick={askSolution}
            disabled={!lesson || isRunning || isLoadingLesson}
            aria-label="View Solution"
            title="Insert official solution into code editor"
          >
            View Solution 💡
          </button>
        </div>

        <button
          id="run-tests-button"
          className="duo-button duo-button-primary"
          onClick={runTests}
          disabled={isRunning || isLoadingLesson}
          aria-label="Run code"
        >
          {isRunning ? 'Running…' : 'Run code'}
        </button>
      </footer>
    </div>
  )
}

export default App
