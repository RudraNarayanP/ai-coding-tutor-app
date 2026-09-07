import { useCallback, useEffect, useRef, useState } from 'react'
import { PatchworkCharacter } from './components/PatchworkCharacters'
import { getGamificationState, recordActivity, activateXpBoost } from './utils/gamification'
import { playPatchworkSound } from './utils/audio'

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

// ─── App Component ────────────────────────────────────────────────────────────
function App() {
  const [activeTab, setActiveTab] = useState<'learn' | 'characters' | 'leaderboards' | 'quests' | 'profile'>('learn')
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
  const [charSubTab, setCharSubTab] = useState<'syntax' | 'keywords' | 'types' | 'operators'>('syntax')

  // Gamification state
  const [gamification, setGamification] = useState(getGamificationState())
  const [consecutiveCorrect, setConsecutiveCorrect] = useState(0)
  const [charState, setCharState] = useState<'idle' | 'happy' | 'celebrate' | 'thinking' | 'confused' | 'encouraging'>('idle')
  const [charSpeech, setCharSpeech] = useState<string | undefined>('Let\'s learn together!')

  const triggerXpGain = useCallback((amount: number) => {
    if (amount > 0) {
      const { state, effectiveXp } = recordActivity(amount)
      setGamification(state)
      setXpGainPopup(effectiveXp)
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

  // Save Sound Preference
  const toggleSound = useCallback(() => {
    setSoundEnabled((prev) => {
      const next = !prev
      localStorage.setItem('patchwork_sound_enabled', String(next))
      return next
    })
  }, [])

  // Save Draft Code
  useEffect(() => {
    if (lesson?.id && code !== undefined) {
      localStorage.setItem(`patchwork_code_${lesson.id}`, code)
    }
  }, [lesson?.id, code])

  // Load Course & Lessons Data
  const loadCourseData = useCallback(async (lang: string) => {
    setIsLoadingLesson(true)
    try {
      const coursesRes = await fetch('/api/courses')
      if (coursesRes.ok) {
        setCourses((await coursesRes.json()) as CourseSummary[])
      }

      await fetch('/api/courses/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: lang }),
      })

      const summariesResponse = await fetch(`/api/lessons?language=${encodeURIComponent(lang)}`)
      if (!summariesResponse.ok) throw new Error('Lesson service unavailable')
      const summariesRaw = await summariesResponse.json()
      const summaries: LessonSummary[] = Array.isArray(summariesRaw) ? summariesRaw : []
      if (summaries.length === 0) throw new Error('No lessons available')
      setLessons(summaries)

      const completedIds = summaries.filter((l) => l.status === 'completed').map((l) => l.id)
      localStorage.setItem(`patchwork_completed_lessons_${lang}`, JSON.stringify(completedIds))

      const lastActiveId = localStorage.getItem(`patchwork_last_active_lesson_${lang}`)
      const targetSummary =
        (lastActiveId && summaries.find((l) => l.id === lastActiveId && l.status !== 'locked')) ||
        summaries.find((l) => l.status === 'current') ||
        summaries[0]

      const lessonResponse = await fetch(`/api/lessons/${targetSummary.id}`)
      if (!lessonResponse.ok) throw new Error('Lesson unavailable')
      const selected = (await lessonResponse.json()) as Lesson
      setLesson(selected)

      const progRes = await fetch(`/api/progression?language=${encodeURIComponent(lang)}`)
      if (progRes.ok) {
        const prog = await progRes.json()
        setXp(prog.xp || 0)
        setLevel(prog.level || 1)
      }

      const draftCode = localStorage.getItem(`patchwork_code_${selected.id}`)
      setCode(draftCode !== null ? draftCode : selected.starter_code ?? '')
      localStorage.setItem(`patchwork_last_active_lesson_${lang}`, selected.id)

      setResults(null)
      setShowCompletion(false)
      setActiveSubLessonIndex(0)
      setActiveExerciseIndex(0)
      setExerciseInput({})
      setCharState('idle')
      setCharSpeech(`Welcome to ${selected.title}!`)
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

  // AI Providers Health Polling
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

  // Navigate to Lesson
  const loadLesson = useCallback(
    async (item: LessonSummary) => {
      if (item.status === 'locked') {
        setFeedback('Complete earlier lessons to unlock this one.')
        setCharState('thinking')
        setCharSpeech('Complete previous lessons first!')
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
        setCharState('idle')
        setCharSpeech(`Let's explore ${selected.title}!`)
        setFeedback('Run your code or answer the question to continue.')
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

  // Run Code in Sandbox
  const runTests = useCallback(async () => {
    if (!lesson) return
    setIsRunning(true)
    setFeedback('Checking your code in the sandbox…')
    setCharState('thinking')
    setCharSpeech('Running tests...')
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

      playPatchworkSound(passedAllRequired ? 'success' : 'error', soundEnabled)

      if (execution.completed) {
        setShowCompletion(true)
        setCharState('celebrate')
        setCharSpeech('🎉 Lesson Mastered! Outstanding job!')
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
        setCharState('happy')
        setCharSpeech('✓ Excellent code!')
        setFeedback('✓ All required checks passed. You are on the right track!')
      } else {
        setCharState('encouraging')
        setCharSpeech('Almost there! Check the hint below.')
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
        setLessons(Array.isArray(summariesRaw) ? summariesRaw : [])
      }
      setTimeout(scrollToResults, 100)
    } catch {
      setFeedback('The sandbox is unavailable. Your code was not graded.')
    } finally {
      setIsRunning(false)
    }
  }, [lesson, code, soundEnabled, scrollToResults, xp, selectedLanguage, triggerXpGain])

  // Ask Tutor for Hint
  const askTutor = useCallback(async () => {
    if (!lesson || !aiEnabled) return
    setIsTutorLoading(true)
    setCharState('thinking')
    setCharSpeech('Consulting tutor AI...')
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
      setCharState('encouraging')
      setCharSpeech('Here is a hint!')
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

  // View Solution
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

  // Submit Interactive Exercise
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

        playPatchworkSound(result.passed ? 'success' : 'error', soundEnabled)

        if (result.passed) {
          const nextConsecutive = consecutiveCorrect + 1
          setConsecutiveCorrect(nextConsecutive)

          if (nextConsecutive === 3) {
            setCharState('celebrate')
            setCharSpeech('🔥 3 in a row! You\'re cooking!')
            playPatchworkSound('streak_milestone', soundEnabled)
          } else if (nextConsecutive === 5) {
            setCharState('celebrate')
            setCharSpeech('⚡ 5 IN A ROW! UNSTOPPABLE!')
            playPatchworkSound('streak_milestone', soundEnabled)
          } else {
            setCharState('happy')
            setCharSpeech('Nice answer! Keep going!')
          }

          if (result.xp_awarded > 0) {
            triggerXpGain(result.xp_awarded)
          }
          setXp(result.total_xp || xp)
          setLevel(result.level || level)
          setFeedback(`✓ ${result.feedback} ${result.xp_awarded > 0 ? `+${result.xp_awarded} XP!` : ''}`)

          const summariesResponse = await fetch(`/api/lessons?language=${encodeURIComponent(selectedLanguage)}`)
          if (summariesResponse.ok) {
            const summariesRaw = await summariesResponse.json()
            setLessons(Array.isArray(summariesRaw) ? summariesRaw : [])
          }
        } else {
          setConsecutiveCorrect(0)
          setCharState('encouraging')
          setCharSpeech('Good try! Review and try again.')
          setFeedback(`Not quite: ${result.feedback}`)
        }
      } catch {
        setFeedback('Failed to submit exercise. Please try again.')
      } finally {
        setIsRunning(false)
      }
    },
    [lesson, code, exerciseInput, soundEnabled, triggerXpGain, xp, level, selectedLanguage, consecutiveCorrect]
  )

  // Test Out Submit
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
        playPatchworkSound('checkpoint_complete', soundEnabled)
        setCharState('celebrate')
        setCharSpeech('🏆 TEST OUT PASSED! UNLOCKED NEXT UNIT!')
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
        playPatchworkSound('error', soundEnabled)
        setCharState('encouraging')
        setCharSpeech('Keep practicing! You\'ll get it next time.')
      }
    } catch {
      setFeedback('Failed to evaluate mastery exam.')
    } finally {
      setIsRunning(false)
    }
  }, [lesson, testOutSubmissions, soundEnabled, triggerXpGain, xp, level, selectedLanguage])

  // Keyboard shortcuts
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

  const safeLessons = Array.isArray(lessons) ? lessons : []
  const completedCount = safeLessons.filter((l) => l.status === 'completed').length
  const progressPct = safeLessons.length ? (completedCount / safeLessons.length) * 100 : 0
  const allPassed = results !== null && results.length > 0 && results.every((r) => r.passed || !r.required)
  const failedRequired = results?.filter((r) => !r.passed && r.required) ?? []
  const hintDisabled = !aiEnabled || !isAiAvailable || !lesson || isTutorLoading || isRunning

  // Course title display
  const coursePathTitle = selectedLanguage === 'cpp' ? 'C++ Path' : selectedLanguage === 'java' ? 'Java Path' : 'Python Path'

  // Characters / Syntax Cards per Language
  const syntaxCards = selectedLanguage === 'cpp'
    ? [
        { symbol: '#include', romaji: 'Header Include', level: 80, desc: 'Includes external libraries' },
        { symbol: 'std::cout', romaji: 'Standard Output', level: 90, desc: 'Prints text to console stream' },
        { symbol: 'int main()', romaji: 'Main Entrypoint', level: 100, desc: 'Program start function' },
        { symbol: 'std::string', romaji: 'String Type', level: 60, desc: 'Sequence of characters' },
        { symbol: 'if / else', romaji: 'Branch Control', level: 85, desc: 'Conditional execution' },
        { symbol: 'for loop', romaji: 'Iteration Loop', level: 70, desc: 'Repeats execution over range' },
      ]
    : selectedLanguage === 'java'
    ? [
        { symbol: 'class', romaji: 'Class Declaration', level: 90, desc: 'Defines blueprint for objects' },
        { symbol: 'public static', romaji: 'Main Modifier', level: 85, desc: 'Global accessible method' },
        { symbol: 'System.out', romaji: 'Console Output', level: 95, desc: 'Prints to standard output' },
        { symbol: 'String', romaji: 'Object String', level: 80, desc: 'Text datatype in Java' },
        { symbol: 'int / boolean', romaji: 'Primitive Types', level: 100, desc: 'Basic data values' },
        { symbol: 'new Keyword', romaji: 'Instantiate', level: 60, desc: 'Creates new object instance' },
      ]
    : [
        { symbol: 'def', romaji: 'Function Def', level: 100, desc: 'Defines a named function' },
        { symbol: 'print()', romaji: 'Standard Output', level: 100, desc: 'Prints values to stdout' },
        { symbol: 'if / else', romaji: 'Conditionals', level: 90, desc: 'Branches on boolean test' },
        { symbol: 'for ... in', romaji: 'Sequence Loop', level: 85, desc: 'Iterates through iterable' },
        { symbol: 'class', romaji: 'Object Class', level: 75, desc: 'Defines OOP custom class' },
        { symbol: 'import', romaji: 'Module Import', level: 80, desc: 'Imports Python library' },
      ]

  return (
    <div className="duo-layout">
      {/* ─── Left Sidebar Navigation Bar ─────────────────────────────────── */}
      <aside className="duo-nav-sidebar" aria-label="Main Navigation">
        <div className="duo-logo-area">
          <div className="duo-logo-text">patchwork</div>
        </div>

        <nav className="duo-nav-menu" aria-label="App Navigation Tabs">
          <button
            className={`duo-nav-item ${activeTab === 'learn' ? 'active' : ''}`}
            onClick={() => setActiveTab('learn')}
          >
            <span className="duo-nav-icon">🏠</span>
            <span>LEARN</span>
          </button>

          <button
            className={`duo-nav-item ${activeTab === 'characters' ? 'active' : ''}`}
            onClick={() => setActiveTab('characters')}
          >
            <span className="duo-nav-icon">🔤</span>
            <span>CHARACTERS</span>
          </button>

          <button
            className={`duo-nav-item ${activeTab === 'leaderboards' ? 'active' : ''}`}
            onClick={() => setActiveTab('leaderboards')}
          >
            <span className="duo-nav-icon">🛡️</span>
            <span>LEADERBOARDS</span>
          </button>

          <button
            className={`duo-nav-item ${activeTab === 'quests' ? 'active' : ''}`}
            onClick={() => setActiveTab('quests')}
          >
            <span className="duo-nav-icon">🎯</span>
            <span>QUESTS</span>
          </button>

          <button
            className={`duo-nav-item ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('profile')}
          >
            <span className="duo-nav-icon">👤</span>
            <span>PROFILE</span>
          </button>
        </nav>

        {/* Sidebar Footer Controls */}
        <div style={{ borderTop: '2px solid var(--line)', paddingTop: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="duo-button duo-button-secondary"
              style={{ padding: '6px 12px', fontSize: '12px', flex: 1 }}
              aria-label={soundEnabled ? 'Mute audio feedback' : 'Unmute audio feedback'}
              onClick={toggleSound}
            >
              {soundEnabled ? '🔊 Sound' : '🔇 Sound'}
            </button>
            <button
              className="duo-button duo-button-secondary"
              style={{ padding: '6px 12px', fontSize: '12px', flex: 1 }}
              aria-label="AI tutor on"
              onClick={() => setAiEnabled((e) => !e)}
            >
              {aiEnabled ? 'AI On' : 'AI Off'}
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
            <select
              value={selectedProvider}
              onChange={(e) => handleProviderChange(e.target.value)}
              aria-label="Select AI Provider"
              style={{
                width: '100%',
                padding: '4px 8px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                fontSize: '12px',
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
          </div>

          <div style={{ fontSize: '11px', color: '#64748b', textAlign: 'center' }}>
            {isAiAvailable ? 'Ollama ready' : 'Ollama unavailable'}
          </div>
        </div>
      </aside>

      {/* ─── Main Viewport Area ─────────────────────────────────────────── */}
      <div className="duo-main-viewport">
        {/* Top Sticky Header */}
        <header className="duo-top-header" role="banner">
          <div className="duo-header-left">
            {/* Language Switcher Tabs / Dropdown */}
            <div className="duo-course-selector" role="tablist" aria-label="Course language selector" style={{ display: 'flex', gap: '6px' }}>
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
                  style={{
                    padding: '6px 12px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: 800,
                    border: '2px solid',
                    borderColor: selectedLanguage === lang ? 'var(--blue-dark)' : 'var(--line)',
                    background: selectedLanguage === lang ? '#ddf4ff' : '#fff',
                    color: selectedLanguage === lang ? 'var(--blue-dark)' : '#777',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>

            <div style={{ fontWeight: 900, fontSize: '15px', color: 'var(--ink)' }}>
              {coursePathTitle}
            </div>
          </div>

          {/* Course Progress Bar */}
          <div style={{ flex: 1, maxWidth: '280px', margin: '0 24px' }}>
            <div
              className="duo-progress-bar-bg"
              role="progressbar"
              aria-valuenow={completedCount}
              aria-valuemin={0}
              aria-valuemax={safeLessons.length}
              aria-label="Course progress"
              style={{ height: '14px', background: '#e5e5e5', borderRadius: '999px', overflow: 'hidden' }}
            >
              <div
                className="duo-progress-bar-fill"
                style={{ width: `${progressPct}%`, height: '100%', background: 'var(--green)', borderRadius: '999px', transition: 'width 0.4s ease' }}
              />
            </div>
          </div>

          {/* Top Stat Pills */}
          <div className="duo-header-stats">
            <div className="duo-stat-pill streak" title="Daily streak">
              <span>🔥</span>
              <span>{gamification.streakCount || 1}</span>
            </div>

            <div className="duo-stat-pill gems" title="Gems">
              <span>💎</span>
              <span>500</span>
            </div>

            <div className="duo-stat-pill xp" title="Total XP" aria-label={`XP: ${xp}, Level: ${level}`}>
              <span>⭐</span>
              <span>{xp} XP</span>
              {xpGainPopup !== null && (
                <div className="xp-float-anim">+{xpGainPopup} XP!</div>
              )}
            </div>

            <div className="duo-stat-pill hearts" title="Hearts / Lives">
              <span>❤️</span>
              <span>5</span>
            </div>
          </div>
        </header>

        {backendError && (
          <div className="backend-error-banner" role="alert" style={{ background: '#fee2e2', color: '#991b1b', padding: '10px 24px', fontWeight: 700, fontSize: '14px' }}>
            <span>⚠️ Backend unavailable — run <code>uvicorn backend.main:app --reload</code></span>
          </div>
        )}

        {/* ─── TAB 1: LEARN PATH VIEW ──────────────────────────────────── */}
        {activeTab === 'learn' && (
          <div className="duo-page-container">
            <div className="duo-learn-view">
              {/* Section & Unit Banner Header */}
              <div className="duo-unit-banner">
                <div className="duo-unit-info">
                  <span className="duo-unit-subtitle">SECTION 1, UNIT 1</span>
                  <span className="duo-unit-title">Variables, Logic & Functions</span>
                </div>
                <button className="duo-guidebook-btn">
                  📖 GUIDEBOOK
                </button>
              </div>

              {/* Character Mascot Speech Header */}
              <div style={{ marginBottom: '24px', width: '100%' }}>
                <PatchworkCharacter name="patch" state={charState} speech={charSpeech} />
              </div>

              {/* Winding Snake Skill Path Nodes */}
              <div className="duo-path-tree">
                {safeLessons.map((item, idx) => {
                  const isActive = lesson?.id === item.id
                  const statusLabel =
                    item.status === 'current'
                      ? isActive
                        ? 'Current lesson'
                        : 'Available'
                      : item.status === 'completed'
                      ? 'Completed'
                      : 'Locked'

                  // Horizontal offset for serpentine path curve
                  const positions = ['node-pos-center', 'node-pos-left-1', 'node-pos-left-2', 'node-pos-left-1', 'node-pos-center', 'node-pos-right-1', 'node-pos-right-2', 'node-pos-right-1']
                  const posClass = positions[idx % positions.length]

                  const iconSymbol =
                    item.status === 'completed'
                      ? '✓'
                      : item.type === 'challenge'
                      ? '⚡'
                      : item.type === 'practice'
                      ? '🔄'
                      : item.type === 'checkpoint'
                      ? '🏆'
                      : '⭐'

                  return (
                    <div key={item.id} className={`duo-path-row ${posClass}`}>
                      <button
                        id={`lesson-node-${item.id}`}
                        className={`duo-path-circle-btn ${item.status}`}
                        onClick={() => loadLesson(item)}
                        disabled={item.status === 'locked' || isLoadingLesson}
                        title={item.title}
                        aria-label={item.title}
                      >
                        {/* Active floating START dialog */}
                        {isActive && item.status !== 'locked' && (
                          <div className="duo-start-dialog">
                            START
                          </div>
                        )}
                        <span>{iconSymbol}</span>
                      </button>
                    </div>
                  )
                })}

                {/* Treasure Chest Node at path end */}
                <div className="duo-path-row node-pos-center">
                  <div className="duo-path-circle-btn chest" title="Unit Reward Chest">
                    📦
                  </div>
                </div>
              </div>

              {/* Full Navigation List for Vitest Accessibility & Sidebar Navigation */}
              <div style={{ width: '100%', marginTop: '32px', paddingTop: '24px', borderTop: '2px solid var(--line)' }}>
                <h3 style={{ fontSize: '14px', fontWeight: 800, color: '#777', textTransform: uppercaseText('Course Lessons') }}>
                  ALL LESSONS
                </h3>
                <nav className="duo-path-list" aria-label="Lessons" style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
                  {safeLessons.map((item) => {
                    const isActive = lesson?.id === item.id
                    const statusLabel =
                      item.status === 'current'
                        ? isActive
                          ? 'Current lesson'
                          : 'Available'
                        : item.status === 'completed'
                        ? 'Completed'
                        : 'Locked'

                    return (
                      <button
                        key={item.id}
                        id={`lesson-nav-${item.id}`}
                        className={`duo-nav-item ${isActive ? 'active' : ''}`}
                        onClick={() => loadLesson(item)}
                        disabled={item.status === 'locked' || isLoadingLesson}
                        aria-current={isActive ? 'page' : undefined}
                        aria-label={`${item.title} — ${statusLabel}`}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '12px 16px',
                          borderRadius: '12px',
                          border: '2px solid',
                          borderColor: isActive ? 'var(--blue-dark)' : 'var(--line)',
                          background: isActive ? '#ddf4ff' : '#ffffff',
                          fontWeight: 800,
                          fontSize: '15px',
                          cursor: item.status === 'locked' ? 'not-allowed' : 'pointer',
                          opacity: item.status === 'locked' ? 0.6 : 1,
                        }}
                      >
                        <span style={{ color: isActive ? 'var(--blue-dark)' : 'var(--ink)' }}>{item.title}</span>
                        <span style={{ fontSize: '13px', color: '#777', textTransform: 'uppercase' }}>{statusLabel}</span>
                      </button>
                    )
                  })}
                </nav>
              </div>

              {/* ─── Exercise Workspace Stage ───────────────────────────────── */}
              {isLoadingLesson ? (
                <div className="duo-card" style={{ textAlign: 'center', padding: '48px', width: '100%', marginTop: '32px' }} role="status" aria-label="Loading lesson">
                  <h2>Loading exercise…</h2>
                </div>
              ) : lesson ? (
                <div className="duo-exercise-stage" style={{ width: '100%', marginTop: '32px' }}>
                  <main className="duo-card" aria-label="Lesson content">
                    <div className="duo-card-header">
                      <span className={`duo-type-badge duo-type-${lesson.type || 'learn'}`}>
                        {(lesson.type || 'learn').toUpperCase()}
                      </span>
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
                        >
                          ⚡ Test Out
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

                    {/* Active Exercise */}
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
                          <div className="exercise-interactive-box">
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
                              style={{ marginTop: '16px', padding: '12px 24px' }}
                              onClick={() => submitSubLessonExercise(currentEx, currentSub?.id)}
                              disabled={!selectedVal || isRunning}
                            >
                              Check Answer ✓
                            </button>
                          </div>
                        )
                      }

                      // Default Code Editor
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
                              aria-label="Code editor"
                            />
                          </div>
                        </div>
                      )
                    })()}
                  </main>

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
                        <div key={r.name} className="result-row" style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '14px', fontWeight: 700 }}>
                          <span role="img" aria-label={r.passed ? 'Passed' : 'Failed'}>{r.passed ? '✓' : '×'}</span>
                          <span>{r.name}</span>
                          {!r.required && (
                            <span className="opt" style={{ fontSize: '10px', background: 'rgba(0,0,0,0.1)', padding: '2px 6px', borderRadius: '4px' }}>opt</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Tutor Coach Box */}
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
                      <p className="ai-unavailable-note" style={{ marginTop: '8px', fontSize: '13px', color: '#64748b' }}>
                        Selected provider is unconfigured. Tests always work offline.
                      </p>
                    )}
                  </aside>

                  {/* Lesson Completion Overlay */}
                  {showCompletion && (
                    <div className="duo-feedback-panel success">
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

                  {/* Session Notes */}
                  <div className="session-notes" style={{ marginTop: '16px' }}>
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
                        style={{ flex: 1, padding: '10px 14px', borderRadius: '12px', border: '2px solid var(--line)', fontWeight: 700 }}
                      />
                      <button onClick={addNote} aria-label="Add note" className="duo-button duo-button-primary" style={{ padding: '10px 20px' }}>+</button>
                    </div>
                    {sessionNotes.length > 0 && (
                      <ul style={{ marginTop: '12px', paddingLeft: '20px', fontWeight: 700 }}>
                        {sessionNotes.map((note, i) => (
                          <li key={i}>{note}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* ─── TAB 2: CHARACTERS / SYNTAX VIEW ──────────────────────────── */}
        {activeTab === 'characters' && (
          <div className="duo-page-container">
            <div className="duo-characters-view">
              <div className="duo-char-header">
                <h1 className="duo-char-title">Learn the Syntax & Symbols</h1>
                <p className="duo-char-subtitle">Get to know the core keywords, operators, and functions in {coursePathTitle}</p>
              </div>

              {/* Script / Syntax Sub-tabs */}
              <div className="duo-char-tabs">
                {[
                  { id: 'syntax', label: 'Syntax' },
                  { id: 'keywords', label: 'Keywords' },
                  { id: 'types', label: 'Data Types' },
                  { id: 'operators', label: 'Operators' },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    className={`duo-char-tab-btn ${charSubTab === tab.id ? 'active' : ''}`}
                    onClick={() => setCharSubTab(tab.id as any)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Character Cards Grid */}
              <div className="duo-char-grid">
                {syntaxCards.map((card, i) => (
                  <div key={i} className="duo-char-card">
                    <div className="duo-char-symbol">{card.symbol}</div>
                    <div className="duo-char-romaji">{card.romaji}</div>
                    <p style={{ fontSize: '11px', color: '#777', textAlign: 'center', margin: '4px 0' }}>{card.desc}</p>
                    <div className="duo-char-level-bar">
                      <div className="duo-char-level-fill" style={{ width: `${card.level}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB 3: LEADERBOARDS VIEW ─────────────────────────────────── */}
        {activeTab === 'leaderboards' && (
          <div className="duo-page-container">
            <div className="duo-leaderboard-view">
              <div className="duo-league-banner">
                <div className="duo-league-shield">🛡️</div>
                <div className="duo-league-details">
                  <h2>Bronze League</h2>
                  <p>Top 20 advance to the next league • 4 days left</p>
                </div>
              </div>

              <div className="duo-rank-list">
                {[
                  { rank: 1, name: 'Duolingo Code Star', xp: 450, self: false },
                  { rank: 2, name: 'PyNinja', xp: 380, self: false },
                  { rank: 3, name: 'AlgoQueen', xp: 310, self: false },
                  { rank: 4, name: 'You (Learner)', xp: xp || 120, self: true },
                  { rank: 5, name: 'DevGuru', xp: 95, self: false },
                  { rank: 6, name: 'StackOverflowBot', xp: 80, self: false },
                  { rank: 7, name: 'ByteWizard', xp: 60, self: false },
                  { rank: 8, name: 'LogicMaster', xp: 45, self: false },
                ].map((user) => (
                  <div key={user.rank} className={`duo-rank-item ${user.self ? 'user-self' : ''}`}>
                    <div className={`duo-rank-num ${user.rank <= 3 ? `top-${user.rank}` : ''}`}>
                      {user.rank}
                    </div>
                    <div className="duo-user-avatar-circle">
                      {user.name.charAt(0)}
                    </div>
                    <div className="duo-rank-name">{user.name}</div>
                    <div className="duo-rank-xp">{user.xp} XP</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB 4: QUESTS VIEW ───────────────────────────────────────── */}
        {activeTab === 'quests' && (
          <div className="duo-page-container">
            <div className="duo-quests-view">
              <div className="duo-quest-card">
                <div className="duo-quest-header">
                  <h2 className="duo-quest-title">Daily Quests</h2>
                  <span style={{ fontSize: '14px', fontWeight: 800, color: 'var(--blue-dark)' }}>2 HOURS LEFT</span>
                </div>

                <div className="duo-quest-item">
                  <div className="duo-quest-icon">⚡</div>
                  <div className="duo-quest-body">
                    <div className="duo-quest-name">Earn 20 XP</div>
                    <div className="duo-quest-progress-bg">
                      <div className="duo-quest-progress-fill" style={{ width: `${Math.min(100, (xp / 20) * 100)}%` }} />
                    </div>
                  </div>
                  <div style={{ fontWeight: 900, color: 'var(--yellow-dark)' }}>+10 💎</div>
                </div>

                <div className="duo-quest-item">
                  <div className="duo-quest-icon">📘</div>
                  <div className="duo-quest-body">
                    <div className="duo-quest-name">Complete 2 lessons</div>
                    <div className="duo-quest-progress-bg">
                      <div className="duo-quest-progress-fill" style={{ width: `${Math.min(100, (completedCount / 2) * 100)}%` }} />
                    </div>
                  </div>
                  <div style={{ fontWeight: 900, color: 'var(--yellow-dark)' }}>+15 💎</div>
                </div>

                <div className="duo-quest-item">
                  <div className="duo-quest-icon">🎯</div>
                  <div className="duo-quest-body">
                    <div className="duo-quest-name">Score 80%+ on an exercise</div>
                    <div className="duo-quest-progress-bg">
                      <div className="duo-quest-progress-fill" style={{ width: '100%' }} />
                    </div>
                  </div>
                  <div style={{ fontWeight: 900, color: 'var(--green-dark)' }}>✓ Done</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB 5: PROFILE VIEW ──────────────────────────────────────── */}
        {activeTab === 'profile' && (
          <div className="duo-page-container">
            <div className="duo-profile-view">
              <div className="duo-profile-header">
                <div className="duo-profile-avatar-large">P</div>
                <div className="duo-profile-meta">
                  <h1>Patchwork Learner</h1>
                  <p className="duo-profile-handle">@patchwork_coder • Joined Sept 2026</p>
                </div>
              </div>

              {/* Statistics Grid */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <h2 style={{ fontSize: '20px', fontWeight: 900 }}>Statistics</h2>
                <div className="duo-stats-grid">
                  <div className="duo-stat-card">
                    <div className="duo-stat-card-icon">🔥</div>
                    <div>
                      <div className="duo-stat-card-val">{gamification.streakCount || 1}</div>
                      <div className="duo-stat-card-lbl">Day Streak</div>
                    </div>
                  </div>

                  <div className="duo-stat-card">
                    <div className="duo-stat-card-icon">⚡</div>
                    <div>
                      <div className="duo-stat-card-val">{xp} XP</div>
                      <div className="duo-stat-card-lbl">Total XP</div>
                    </div>
                  </div>

                  <div className="duo-stat-card">
                    <div className="duo-stat-card-icon">🛡️</div>
                    <div>
                      <div className="duo-stat-card-val">Bronze</div>
                      <div className="duo-stat-card-lbl">Current League</div>
                    </div>
                  </div>

                  <div className="duo-stat-card">
                    <div className="duo-stat-card-icon">🏆</div>
                    <div>
                      <div className="duo-stat-card-val">2</div>
                      <div className="duo-stat-card-lbl">Top 3 Finishes</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="duo-friends-card">
                <h2 style={{ fontSize: '20px', fontWeight: 900 }}>Friend Updates</h2>
                <p style={{ color: '#777', fontWeight: 600 }}>Connect with friends to compare XP and study together!</p>
              </div>
            </div>
          </div>
        )}

        {/* ─── Bottom Footer Bar ──────────────────────────────────────── */}
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
              disabled={!lesson || isRunning}
              aria-label="View Solution"
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

      {/* Test-Out Modal */}
      {showTestOutModal && lesson && (
        <div className="modal-overlay" role="dialog" aria-label="Mastery Exam Modal">
          <div className="modal-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ fontSize: '22px', fontWeight: 900 }}>⚡ Mastery Exam: {lesson.title}</h2>
              <button onClick={() => setShowTestOutModal(false)} style={{ fontSize: '20px', fontWeight: 900, background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
            </div>
            <p style={{ color: '#777', marginBottom: '20px', fontWeight: 700 }}>Pass with 80%+ score to test out of this lesson and earn +100 XP!</p>

            {testOutResult ? (
              <div className={`duo-feedback-panel ${testOutResult.passed ? 'success' : 'error'}`}>
                <h3>{testOutResult.passed ? '🎉 Congratulations! You Mastered This Concept!' : 'Keep Practicing!'}</h3>
                <p>Score: {testOutResult.score_pct}% ({testOutResult.passed_count} / {testOutResult.total_questions} correct)</p>
                <button className="duo-button duo-button-primary" style={{ marginTop: '16px' }} onClick={() => setShowTestOutModal(false)}>Close</button>
              </div>
            ) : (
              <div>
                {(lesson.mastery_exam && lesson.mastery_exam.length > 0
                  ? lesson.mastery_exam
                  : lesson.sublessons?.flatMap((s) => s.exercises) || []
                ).map((ex, idx) => (
                  <div key={ex.id} style={{ marginBottom: '20px', padding: '12px', border: '2px solid var(--line)', borderRadius: '12px' }}>
                    <h4 style={{ fontWeight: 800, marginBottom: '8px' }}>Question {idx + 1}: {ex.question || ex.title}</h4>
                    {ex.options && ex.options.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {ex.options.map((opt) => (
                          <label key={opt} style={{ display: 'flex', gap: '8px', alignItems: 'center', cursor: 'pointer', fontWeight: 700 }}>
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
                        style={{ width: '100%', padding: '10px 14px', border: '2px solid var(--line)', borderRadius: '8px', fontWeight: 700 }}
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

                <button className="duo-button duo-button-primary" style={{ width: '100%', marginTop: '16px' }} onClick={handleTestOutSubmit} disabled={isRunning}>
                  {isRunning ? 'Evaluating Exam…' : 'Submit Mastery Exam'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function uppercaseText(str: string) {
  return str.toUpperCase()
}

export default App
