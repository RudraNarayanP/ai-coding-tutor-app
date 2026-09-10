 import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PatchworkCharacter } from './components/PatchworkCharacters'
import { GuidebookPanel } from './components/GuidebookPanel'
import { CreatePage } from './components/CreatePage'
import Settings from './components/Settings'
import ExercisePanel from './components/ExercisePanel'
import { CodeEditor } from './components/CodeEditor'
import { api, type ExerciseResult, type LessonProgress, type TestOutResult } from './api'
import {
  getGamificationState,
  recordActivity,
  activateXpBoost,
  getHearts,
loseHeart,
  restoreHearts,
  setUnlimitedHearts as applyUnlimitedHearts,
  saveGameState,
  restoreGameState,
  getDailyProgress,
  xpForLevel,
  levelFromXp,
} from './utils/gamification'
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
  pairs?: { left: string; right: string }[]
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

// ─── Line Numbers Component ───────────────────────────────────────────────────
function LineNumbers({ code }: { code: string }) {
  const contentRef = useRef<HTMLDivElement>(null)
  const lines = code.split('\n')

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
  const [activeTab, setActiveTab] = useState<'learn' | 'create' | 'leaderboards' | 'quests' | 'profile'>('learn')
  const [isGuidebookOpen, setIsGuidebookOpen] = useState(false)
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
  const [sessionNotes, setSessionNotes] = useState<string[]>([])
  const [noteInput, setNoteInput] = useState('')
  const [backendError, setBackendError] = useState(false)
  const [xp, setXp] = useState(0)
  const [level, setLevel] = useState(1)
  const [xpGainPopup, setXpGainPopup] = useState<number | null>(null)
  const [exerciseInput, setExerciseInput] = useState<any>({})
  const [showTestOutModal, setShowTestOutModal] = useState(false)
  const [testOutSubmissions, setTestOutSubmissions] = useState<Record<string, any>>({})
  const [testOutResult, setTestOutResult] = useState<any>(null)
  const [charSubTab, setCharSubTab] = useState<'syntax' | 'keywords' | 'types' | 'operators'>('syntax')

  // Gamification & Hearts State
  const [showOutofHeartsModal, setShowOutofHeartsModal] = useState(false)
  const [leaderboardData, setLeaderboardData] = useState<any[] | null>(null)

  const fetchLeaderboard = useCallback(async () => {
    try {
      const res = await fetch('/api/leaderboard')
      if (res.ok) {
        const data = await res.json()
        setLeaderboardData(data.leaderboard || [])
      }
    } catch {
      // fallback
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'leaderboards') {
      fetchLeaderboard()
    }
  }, [activeTab, fetchLeaderboard, xp])

  // Custom Course Generation State
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [materialType, setMaterialType] = useState<'youtube_url' | 'transcript' | 'file_upload'>('youtube_url')
  const [materialInput, setMaterialInput] = useState('')
  const [customTitle, setCustomTitle] = useState('')
  const [isGeneratingCourse, setIsGeneratingCourse] = useState(false)

  // Focused Lesson Mode State
  const [isLessonActive, setIsLessonActive] = useState(false)

  // Gamification state
  const [gamification, setGamification] = useState(getGamificationState())
  const [consecutiveCorrect, setConsecutiveCorrect] = useState(0)
  const [charState, setCharState] = useState<'idle' | 'happy' | 'celebrate' | 'thinking' | 'confused' | 'encouraging'>('idle')
  const [charSpeech, setCharSpeech] = useState<string | undefined>('Let\'s learn together!')

  // ─── Core learning-loop state ──────────────────────────────────────────────
  // The backend is the single authoritative source for persisted progress.
  // `lessonProgress` mirrors GET /api/lessons/{id}/progress. The "current
  // exercise" is DERIVED from it (first exercise not yet completed) — we never
  // store an exercise index, so the UI can never desync from real progress.
  const [lessonProgress, setLessonProgress] = useState<LessonProgress | null>(null)
  // Ephemeral per-exercise interaction state (frontend-owned):
  //   answering  → learner is composing an answer
  //   checking   → submission in flight (buttons locked, no double submits)
  //   correct    → positive feedback + CONTINUE
  //   incorrect  → negative feedback + TRY AGAIN
  type ExercisePhase = 'answering' | 'checking' | 'correct' | 'incorrect'
  const [exercisePhase, setExercisePhase] = useState<ExercisePhase>('answering')
  const [exerciseFeedback, setExerciseFeedback] = useState<{
    passed: boolean
    feedback: string
    explanation?: string
    xpAwarded: number
    attempts: number
  } | null>(null)
  // Lesson-complete celebration (ephemeral; completion itself is persisted by the backend)
  const [celebration, setCelebration] = useState<{ xpEarned: number; nextLessonId: string | null } | null>(null)

  // Hearts (Duolingo-style) + Settings modal
  const [hearts, setHearts] = useState<number>(() => getHearts())
  const [unlimitedHearts, setUnlimitedHearts] = useState<boolean>(
    () => getGamificationState().unlimitedHearts
  )
  const [showSettings, setShowSettings] = useState(false)

  const triggerXpGain = useCallback((amount: number) => {
    if (amount > 0) {
      setXpGainPopup(amount)
      setXp((prev) => {
        const nextXp = prev + amount
        const nextLevel = levelFromXp(nextXp)
        setLevel(nextLevel)
        saveGameState({ xp: nextXp, level: nextLevel })
        return nextXp
      })
      setTimeout(() => setXpGainPopup(null), 2000)
    }
  }, [])

  const editorRef = useRef<HTMLTextAreaElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  // ─── Derived lesson progression (single source of truth: backend) ───────────
  // Canonical exercise order = sublessons flattened in curriculum order.
  const allExercises = useMemo(() => {
    if (!lesson?.sublessons) return []
    return lesson.sublessons.flatMap((sub) =>
      sub.exercises.map((ex) => ({ ...ex, sublessonId: sub.id, sublessonTitle: sub.title }))
    )
  }, [lesson])

  const completedExerciseIds = useMemo(
    () => new Set(lessonProgress?.completed_exercise_ids ?? []),
    [lessonProgress]
  )

  // The current exercise is the FIRST exercise not yet completed.
  const currentExerciseIndex = useMemo(
    () => allExercises.findIndex((ex) => !completedExerciseIds.has(ex.id)),
    [allExercises, completedExerciseIds]
  )
  const currentExercise = currentExerciseIndex >= 0 ? allExercises[currentExerciseIndex] : null

  // Lesson complete = lesson has exercises AND every one of them is completed.
  const lessonHasExercises = allExercises.length > 0
  const lessonComplete = lessonHasExercises && currentExercise === null

  const exercisePosition = lessonHasExercises && currentExerciseIndex >= 0 ? currentExerciseIndex + 1 : 0
  const exerciseTotal = allExercises.length
  const completedExerciseCount = useMemo(
    () => allExercises.filter((ex) => completedExerciseIds.has(ex.id)).length,
    [allExercises, completedExerciseIds]
  )

  // Fetch the authoritative progress for the open lesson.
  const fetchLessonProgress = useCallback(async (lessonId: string) => {
    const prog = await api.lessonProgress(lessonId)
    if (prog) setLessonProgress(prog)
    return prog
  }, [])

  // Reset the ephemeral interaction state whenever the current exercise changes
  // (next exercise after CONTINUE, retry after TRY AGAIN, or a brand-new lesson).
  // This guarantees stale answers/feedback can never leak between exercises.
  useEffect(() => {
    setExercisePhase('answering')
    setExerciseFeedback(null)
  }, [currentExercise?.id])

  // ─── Fetch Courses ──────────────────────────────────────────────────────────
  const fetchCourses = useCallback(async () => {
    try {
      const res = await fetch('/api/courses')
      if (res.ok) {
        const data = await res.json()
        setCourses(data)
      }
    } catch {
      // ignore
    }
  }, [])

  // ─── Select AI Provider ────────────────────────────────────────────────────
  const handleProviderSelection = async (prov: string) => {
    setSelectedProvider(prov)
    try {
      await fetch('/api/ai/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: prov }),
      })
      fetchProviders()
    } catch {
      // ignore
    }
  }

  // ─── Fetch Provider Status ─────────────────────────────────────────────────
  const fetchProviders = useCallback(async () => {
    try {
      const res = await fetch('/api/ai/providers')
      if (res.ok) {
        const data: ProvidersOverview = await res.json()
        setProvidersOverview(data)
        if (data.current_provider) {
          setSelectedProvider(data.current_provider)
        }
      }
    } catch {
      // ignore
    }
  }, [])

  // ─── Fetch Progression State for Active Language ──────────────────────────────
  const fetchProgression = useCallback(async () => {
    try {
      const res = await fetch(`/api/progression?language=${encodeURIComponent(selectedLanguage)}`)
      if (res.ok) {
        const data = await res.json()
        setXp(data.xp || 0)
        setLevel(data.level || Math.floor((data.xp || 0) / 100) + 1)
      }
    } catch {
      // ignore
    }
  }, [selectedLanguage])

  // ─── Load Lessons for Language ──────────────────────────────────────────────
  // Landing on the HOME page is intentional: lessons are only opened when the
  // learner clicks a node, never implicitly on load or course switch.
  const fetchLessons = useCallback(async () => {
    try {
      const res = await fetch('/api/lessons')
      if (!res.ok) {
        setBackendError(true)
        return
      }
      const data: LessonSummary[] = await res.json()
      setLessons(data)
      setBackendError(false)
// Note: DO NOT auto-open a lesson here. The course map (home) is shown
      // so the learner can choose Unit 1, Unit 2, etc. themselves.
    } catch {
      setBackendError(true)
    }
  }, [])

  // ─── Select Language Course Track ───────────────────────────────────────────
  const handleCourseChange = async (lang: string) => {
    setSelectedLanguage(lang)
    localStorage.setItem('patchwork_active_language', lang)
    setIsLessonActive(false)
    try {
      await fetch('/api/courses/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: lang }),
      })
    } catch {
      // fallback
    }
    // Always land back on the home / course map after switching tracks.
    setLesson(null)
    setIsLessonActive(false)
    setCelebration(null)
    fetchLessons()
  }

  // ─── Generate Custom AI Course ──────────────────────────────────────────────
  const handleGenerateCourse = async () => {
    if (!materialInput.trim() && !customTitle.trim()) return
    setIsGeneratingCourse(true)
    try {
      const res = await fetch('/api/courses/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          material_type: materialType,
          content: materialInput,
          title: customTitle,
        }),
      })

      if (res.ok) {
        const newCourse = await res.json()
        await fetchCourses()
        await handleCourseChange(newCourse.id)
        setShowCreateModal(false)
        setMaterialInput('')
        setCustomTitle('')
      }
    } catch {
      // fallback
    } finally {
      setIsGeneratingCourse(false)
    }
  }

  // ─── Load Detailed Lesson ───────────────────────────────────────────────────
  const loadLesson = async (summary: LessonSummary, openWorkspace = false) => {
    setIsLoadingLesson(true)
    setResults(null)
    setFeedback('Run your code to get immediate feedback from the local sandbox.')
    setHintLevel(1)
    setPreviousHints([])
    setExerciseInput({})
    setCharState('idle')
    setLessonProgress(null)
    setExercisePhase('answering')
    setExerciseFeedback(null)
    setCelebration(null)

    try {
      const [res, prog] = await Promise.all([
        fetch(`/api/lessons/${summary.id}`),
        api.lessonProgress(summary.id),
      ])
      if (!res.ok) throw new Error('Lesson fetch failed')
      const data: Lesson = await res.json()
      setLesson(data)
      if (prog) setLessonProgress(prog)

      const draftKey = `patchwork_code_${data.id}`
      const savedDraft = localStorage.getItem(draftKey)
      setCode(savedDraft !== null ? savedDraft : data.starter_code || '')
setIsLessonActive(true)
      saveGameState({ currentLessonId: data.id })
    } catch {
      setLesson({
        id: summary.id,
        title: summary.title,
        description: 'Practice programming concepts.',
        order: summary.order,
        difficulty: summary.difficulty,
        duration_minutes: summary.duration_minutes,
        starter_code: '# Write your solution here\n',
      })
      setCode('# Write your solution here\n')
setIsLessonActive(true)
      saveGameState({ currentLessonId: summary.id })
    } finally {
      setIsLoadingLesson(false)
    }
  }

  useEffect(() => {
    // Restore persisted game state (XP, level, hearts) from previous sessions
    const saved = restoreGameState()
    if (saved) {
      if (typeof saved.xp === 'number') setXp(saved.xp)
      if (typeof saved.level === 'number') setLevel(saved.level)
      if (typeof saved.hearts === 'number') setHearts(saved.hearts)
      if (typeof saved.unlimitedHearts === 'boolean') setUnlimitedHearts(saved.unlimitedHearts)
    }
    fetchCourses()
    fetchProviders()
    fetchLessons()
    fetchProgression()
  }, [fetchCourses, fetchProviders, fetchLessons, fetchProgression])

  // Persist hearts/unlimited setting whenever they change
  useEffect(() => {
    saveGameState({ hearts, unlimitedHearts })
  }, [hearts, unlimitedHearts])

  // Save code drafts
  useEffect(() => {
    if (lesson?.id) {
      localStorage.setItem(`patchwork_code_${lesson.id}`, code)
    }
  }, [code, lesson])

  // ─── Run Code & Tests ───────────────────────────────────────────────────────
  const runTests = useCallback(async () => {
    if (!lesson) return
    setIsRunning(true)
    setResults(null)
    setCharState('thinking')
    setCharSpeech('Testing your code against strict test cases…')

    try {
      const res = await fetch(`/api/lessons/${lesson.id}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })

      if (!res.ok) throw new Error('Sandbox error')
      const data = await res.json()
      setResults(data.tests || [])

      const allPassed = data.passed || (data.tests && data.tests.every((t: TestResult) => !t.required || t.passed))

      if (allPassed) {
        playPatchworkSound('success', soundEnabled)
        setCharState('celebrate')
        setCharSpeech('Outstanding job! All checks passed perfectly!')
        setConsecutiveCorrect((prev) => prev + 1)

        const activity = recordActivity(15)
        setGamification(activity.state)
        triggerXpGain(15)

// Lesson-level code lesson completed. Show the celebration screen.
        const nextId =
          data.next_lesson_id ||
          (() => {
            const idx = lessons.findIndex((l) => l.id === lesson?.id)
            return idx >= 0 && idx < lessons.length - 1 ? lessons[idx + 1].id : null
          })()
        setCelebration({ xpEarned: 15, nextLessonId: nextId ?? null })
      } else {
        playPatchworkSound('error', soundEnabled)
        setCharState('confused')
        setCharSpeech('Some test checks failed. Take a look at the details below!')
        setConsecutiveCorrect(0)

// Duolingo-style: every mistake costs one heart.
        const heartState = loseHeart()
        setHearts(heartState.hearts)
        if (heartState.hearts <= 0 && !heartState.unlimitedHearts) {
          setCharSpeech('Out of hearts! Enable Unlimited Hearts in Settings or review the guidebook and try again.')
        }
      }
    } catch {
      setFeedback('Error connecting to code execution sandbox.')
      setCharState('confused')
    } finally {
      setIsRunning(false)
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, [lesson, code, soundEnabled, triggerXpGain, lessons])

  // ─── Ask AI Tutor ──────────────────────────────────────────────────────────
  const askTutor = async () => {
    if (!lesson || !aiEnabled) return
    setIsTutorLoading(true)
    setCharState('thinking')

    try {
      const res = await fetch('/api/tutor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lesson_id: lesson.id,
          code,
          hint_level: hintLevel,
          previous_hints: previousHints,
          provider: selectedProvider,
        }),
      })

      if (res.ok) {
        const data = await res.json()
        setFeedback(data.message)
        setHintLevel((prev) => prev + 1)
        if (data.message) {
          setPreviousHints((prev) => [...prev, data.message])
          setCharSpeech(data.message)
        }
        setCharState('encouraging')
      } else {
        setFeedback('AI tutor service is currently offline.')
      }
    } catch {
      setFeedback('Failed to reach AI tutor service.')
    } finally {
      setIsTutorLoading(false)
    }
  }

  // ─── View Canonical Solution ───────────────────────────────────────────────
  const askSolution = async () => {
    if (!lesson) return
    try {
      const res = await fetch(`/api/lessons/${lesson.id}/solution`)
      if (res.ok) {
        const data = await res.json()
        setCode(data.solution_code || '')
        setFeedback('Canonical solution inserted into editor.')
        setCharState('happy')
        setCharSpeech('Here is the canonical solution for this challenge!')
      }
    } catch {
      // ignore
    }
  }

  // ─── Submit Interactive Sublesson Exercise ──────────────────────────────────
  const submitSubLessonExercise = async (ex: Exercise & { sublessonId?: string }) => {
    if (!lesson) return
    // Hard guard: submissions are only valid from the 'answering' phase.
    // This makes double-clicks and stale submissions impossible.
    if (exercisePhase !== 'answering') return
    if (completedExerciseIds.has(ex.id)) return // already graded — never re-award XP

    const inputState = exerciseInput[ex.id] || {}
    const exType = (ex.type || 'code').toLowerCase().trim()
    let payload: Record<string, any> = {}

    if (['mcq', 'true_false', 'output_prediction', 'debugging', 'identify_error'].includes(exType)) {
      payload = { answer: inputState.answer || '' }
    } else if (['fill_blank', 'code_completion'].includes(exType)) {
      payload = { answers: inputState.answers || (inputState.answer ? [inputState.answer] : []) }
    } else if (exType === 'select_multiple') {
      payload = { answers: inputState.answers || inputState.selected || [] }
    } else if (exType === 'ordering') {
      payload = { order: inputState.order || inputState.answers || [] }
    } else if (exType === 'matching') {
      payload = { pairs: inputState.pairs || [] }
    } else if (exType === 'code') {
      payload = { code: inputState.code || code }
    } else {
      payload = { answer: inputState.answer || '' }
    }

    setExercisePhase('checking')
    try {
      const res = await api.submitExercise(lesson.id, ex.id, ex.sublessonId, payload)
      if (!res.ok) throw new Error('Submission failed')
      const data: ExerciseResult = await res.json()

      // Sync authoritative progress from the grading response itself.
      if (data.progress) {
        setLessonProgress((prev) =>
          prev
            ? {
                ...prev,
                completed_exercise_ids: Array.from(
                  new Set([...prev.completed_exercise_ids, ...(data.passed ? [ex.id] : [])])
                ),
                attempt_counts: { ...prev.attempt_counts, [ex.id]: data.attempt_count ?? 1 },
                last_results: { ...prev.last_results, [ex.id]: data.passed ? 'correct' : 'incorrect' },
                progress: data.progress ?? prev.progress,
                lesson_completed: data.lesson_completed ?? prev.lesson_completed,
                next_action: data.lesson_completed ? 'lesson_complete' : 'answer',
                next_lesson_id: data.next_lesson_id ?? prev.next_lesson_id,
              }
            : prev
        )
      }

      if (data.passed) {
        playPatchworkSound('success', soundEnabled)
        setCharState('happy')
        setCharSpeech(data.feedback || 'Correct answer!')
        setExercisePhase('correct')
        setExerciseFeedback({
          passed: true,
          feedback: data.feedback || 'Correct!',
          explanation: data.explanation || undefined,
          xpAwarded: data.xp_awarded || 0,
          attempts: data.attempt_count || 1,
        })
        if (data.xp_awarded) {
          triggerXpGain(data.xp_awarded)
        }
        fetchLessons()
      } else {
        playPatchworkSound('error', soundEnabled)
        setCharState('confused')
        setCharSpeech(data.feedback || data.explanation || 'Not quite right. Try again!')
setExercisePhase('incorrect')
        setExerciseFeedback({
          passed: false,
          feedback: data.feedback || 'Not quite right.',
          explanation: data.explanation || undefined,
          xpAwarded: 0,
          attempts: data.attempt_count || 1,
        })

        // Wrong answers cost one heart too.
        const heartState = loseHeart()
        setHearts(heartState.hearts)
        if (heartState.hearts <= 0 && !heartState.unlimitedHearts) {
          setCharSpeech('Out of hearts! Enable Unlimited Hearts in Settings or review the guidebook and try again.')
        }
      }
    } catch {
      playPatchworkSound('error', soundEnabled)
      setFeedback('Failed to submit exercise to grading server.')
      setExercisePhase('answering')
    }
  }

  // ─── Primary CTA: CONTINUE (after a correct answer) ─────────────────────────
  // The backend has already persisted completion; the derived progression now
  // points at the next exercise automatically. We only clear ephemeral state.
  const continueToNextExercise = () => {
    const wasLessonComplete = lessonComplete
    const earnedXp = exerciseFeedback?.xpAwarded ?? 0
    setExerciseInput((prev: any) => {
      if (!currentExercise) return prev
      const next = { ...prev }
      delete next[currentExercise.id]
      return next
    })
    setExercisePhase('answering')
    setExerciseFeedback(null)

    if (wasLessonComplete) {
      const nextId =
        lessonProgress?.next_lesson_id ||
        (() => {
          const idx = lessons.findIndex((l) => l.id === lesson?.id)
          return idx >= 0 && idx < lessons.length - 1 ? lessons[idx + 1].id : null
        })()
      setCelebration({ xpEarned: earnedXp, nextLessonId: nextId ?? null })
    }
  }

  // ─── Primary CTA: TRY AGAIN (after an incorrect answer) ─────────────────────
  const retryCurrentExercise = () => {
    if (!currentExercise) return
    setExerciseInput((prev: any) => {
      const next = { ...prev }
      delete next[currentExercise.id]
      return next
    })
    setExercisePhase('answering')
    setExerciseFeedback(null)
    setCharState('encouraging')
    setCharSpeech('Take another look — you\'ve got this!')
  }

  // ─── Run Test Out Exam ──────────────────────────────────────────────────────
  const handleRunTestOut = async () => {
    if (!lesson) return
    try {
      const res = await api.testOut(lesson.id, testOutSubmissions)
      if (res.ok) {
        const data: TestOutResult = await res.json()
        setTestOutResult(data)
        if (data.passed) {
          playPatchworkSound('success', soundEnabled)
          triggerXpGain(data.xp_awarded || 100)
          setCharState('celebrate')
          setCharSpeech('Test out passed! You mastered this unit!')
          fetchLessons()
        } else {
          playPatchworkSound('error', soundEnabled)
          setCharState('confused')
          setCharSpeech(data.error || 'Test out attempt did not reach passing score. Practice the material and try again!')
        }
      }
    } catch {
      // fallback
    }
  }

  // ─── Next Lesson Navigation ─────────────────────────────────────────────────
  const goToNextLesson = () => {
    const nextId = celebration?.nextLessonId
    if (nextId) {
      const nextSummary = lessons.find((l) => l.id === nextId)
      if (nextSummary) {
        setCelebration(null)
        loadLesson(nextSummary, true)
        return
      }
    }
    // No next lesson — return to the course map.
    setCelebration(null)
    setIsLessonActive(false)
    setLesson(null)
  }

  // ─── Add Note ──────────────────────────────────────────────────────────────
  const addNote = () => {
    if (noteInput.trim()) {
      setSessionNotes((prev) => [...prev, noteInput.trim()])
      setNoteInput('')
    }
  }

  // ─── Sound & AI Toggles ────────────────────────────────────────────────────
  const toggleSound = () => {
    const next = !soundEnabled
    setSoundEnabled(next)
    localStorage.setItem('patchwork_sound_enabled', String(next))
  }

  const handleEditorKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault()
      const textarea = e.currentTarget
      const start = textarea.selectionStart
      const end = textarea.selectionEnd
      const newCode = code.substring(0, start) + '    ' + code.substring(end)
      setCode(newCode)
      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + 4
      }, 0)
    } else if ((e.ctrlKey || e.shiftKey) && e.key === 'Enter') {
      e.preventDefault()
      runTests()
    }
  }

  // Calculate Course Progress
  const safeLessons = Array.isArray(lessons) ? lessons : []
  const completedCount = safeLessons.filter((l) => l.status === 'completed').length
  const progressPct = safeLessons.length ? (completedCount / safeLessons.length) * 100 : 0

  const isAiAvailable = providersOverview?.providers?.some((p) => p.is_current && p.available) ?? false
  const currentProviderStatus = providersOverview?.providers?.find((p) => p.is_current)
  const hintDisabled = isRunning || !aiEnabled || !isAiAvailable

  const failedRequired = results ? results.filter((r) => r.required && !r.passed) : []
  const allPassed = results ? results.length > 0 && failedRequired.length === 0 : false

  // Language Track Display Name
  const coursePathTitle = selectedLanguage === 'cpp' ? 'C++ Path' : selectedLanguage === 'java' ? 'Java Path' : 'Python Path'

  // Strict daily progression (Day N of the course)
  const dailyProgress = getDailyProgress()

  // Group lessons by Unit
  const unitsMap = new Map<string, { id: string; title: string; lessons: LessonSummary[] }>()
  safeLessons.forEach((item, idx) => {
    const unitId = item.unit_id || `unit-${Math.floor(idx / 4) + 1}`
    const unitTitle = item.unit_title || `Unit ${Math.floor(idx / 4) + 1} — ${selectedLanguage.toUpperCase()} Essentials`
    if (!unitsMap.has(unitId)) {
      unitsMap.set(unitId, { id: unitId, title: unitTitle, lessons: [] })
    }
    unitsMap.get(unitId)!.lessons.push(item)
  })
  const unitGroups = Array.from(unitsMap.values())

  return (
    <div className="duo-layout">
      {/* ─── Left Sidebar Navigation Bar ─────────────────────────────────── */}
      <aside className="duo-nav-sidebar" aria-label="Main Navigation">
        <div className="duo-logo-area">
          <div className="duo-logo-text">patchwork</div>
        </div>

        <nav className="duo-nav-menu" aria-label="App Navigation Tabs">
          <button
            className={`duo-nav-item ${activeTab === 'learn' && !isLessonActive ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('learn')
              setIsLessonActive(false)
            }}
          >
            <span className="duo-nav-icon">🏠</span>
            <span>LEARN</span>
          </button>

          <button
            className={`duo-nav-item ${activeTab === 'create' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('create')
              setIsLessonActive(false)
            }}
          >
            <span className="duo-nav-icon">✨</span>
            <span>CREATE</span>
          </button>

          <button
            className={`duo-nav-item ${activeTab === 'leaderboards' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('leaderboards')
              setIsLessonActive(false)
            }}
          >
            <span className="duo-nav-icon">🛡️</span>
            <span>LEADERBOARDS</span>
          </button>

          <button
            className={`duo-nav-item ${activeTab === 'quests' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('quests')
              setIsLessonActive(false)
            }}
          >
            <span className="duo-nav-icon">🎯</span>
            <span>QUESTS</span>
          </button>

          <button
            className={`duo-nav-item ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('profile')
              setIsLessonActive(false)
            }}
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
              aria-label={aiEnabled ? 'AI tutor on' : 'AI tutor off'}
              onClick={() => setAiEnabled(!aiEnabled)}
            >
              {aiEnabled ? 'AI On' : 'AI Off'}
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
            <select
              value={selectedProvider}
              onChange={(e) => handleProviderSelection(e.target.value)}
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

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="duo-button duo-button-secondary"
              style={{ padding: '6px 12px', fontSize: '12px', flex: 1 }}
              onClick={() => setShowSettings(true)}
            >
              ⚙️ Settings
            </button>
          </div>

          <div style={{ fontSize: '11px', color: '#64748b', textAlign: 'center' }}>
            {isAiAvailable ? 'Ollama ready' : 'Ollama unavailable'}
          </div>
        </div>
      </aside>

      {/* ─── Main Viewport Area ─────────────────────────────────────────── */}
      <div className="duo-main-viewport">
        {/* Top Sticky Header Bar */}
        <header className="duo-top-header" role="banner">
          <div className="duo-header-left">
            <div className="duo-course-selector" role="tablist" aria-label="Course language selector" style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              {courses.map((c) => (
                <button
                  key={c.id}
                  role="tab"
                  aria-selected={selectedLanguage === c.language || selectedLanguage === c.id}
                  className={`duo-course-btn ${selectedLanguage === c.language || selectedLanguage === c.id ? 'active' : ''}`}
                  onClick={() => handleCourseChange(c.language || c.id)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: 800,
                    border: '2px solid',
                    borderColor: (selectedLanguage === c.language || selectedLanguage === c.id) ? 'var(--blue-dark)' : 'var(--line)',
                    background: (selectedLanguage === c.language || selectedLanguage === c.id) ? '#ddf4ff' : '#fff',
                    color: (selectedLanguage === c.language || selectedLanguage === c.id) ? 'var(--blue-dark)' : '#777',
                  }}
                >
                  {c.title.replace(' Foundations', '').replace(' Path', '')}
                </button>
              ))}

              <button
                className="duo-button duo-button-primary"
                onClick={() => setShowCreateModal(true)}
                style={{ padding: '6px 12px', fontSize: '12px', marginLeft: '4px' }}
                aria-label="Create Custom Course"
              >
                + Create Course
              </button>
            </div>

            <div style={{ fontWeight: 900, fontSize: '15px', color: 'var(--ink)' }}>
              {coursePathTitle}
            </div>
          </div>

          {/* Progress bar */}
          <div style={{ flex: 1, maxWidth: '200px', margin: '0 16px' }}>
            <div
              className="duo-progress-bar-bg"
              role="progressbar"
              aria-valuenow={completedCount}
              aria-valuemin={0}
              aria-valuemax={safeLessons.length}
              aria-label="Course progress"
              style={{ height: '12px', background: '#e5e5e5', borderRadius: '999px', overflow: 'hidden' }}
            >
              <div
                className="duo-progress-bar-fill"
                style={{ width: `${progressPct}%`, height: '100%', background: 'var(--green)', borderRadius: '999px' }}
              />
            </div>
          </div>

          <div className="duo-header-stats">
<div className="duo-stat-pill streak" title="Daily streak"><span>🔥 {gamification.streakCount || 0}</span></div>
            <div className="duo-stat-pill gems" title="Gems"><span>💎 {gamification.dailyXp || 0}</span></div>
            <div className="duo-stat-pill xp" title="Total XP" aria-label={`XP: ${xp}, Level: ${level}`}><span>⭐ {xp} XP</span></div>
            <div className="duo-stat-pill hearts" title="Hearts"><span>❤️ {unlimitedHearts ? '∞' : hearts}</span></div>
          </div>
        </header>

        {backendError && (
          <div className="backend-error-banner" role="alert" style={{ background: '#fee2e2', color: '#991b1b', padding: '10px 24px', fontWeight: 700, fontSize: '14px' }}>
            <span>⚠️ Backend unavailable — run <code>uvicorn backend.main:app --reload</code></span>
          </div>
        )}

        {/* ─── TAB 1: LEARN PATH VIEW (COURSE MAP OR FOCUSED LESSON) ──────────────────── */}
        {activeTab === 'learn' && (
          <div className="duo-page-container">
            {isLoadingLesson && (
              <div role="status" aria-label="Loading lesson" style={{ position: "fixed", top: "12px", right: "24px", background: "var(--yellow)", color: "#000", padding: "8px 16px", borderRadius: "20px", fontWeight: 900, zIndex: 9999 }}>
                Loading lesson…
              </div>
            )}
            {isLessonActive && lesson ? (
              /* ─── FOCUSED LESSON WORKSPACE ────────────────────────────── */
              <div className="duo-exercise-stage">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                  <button
                    className="duo-button duo-button-secondary"
                    onClick={() => setIsLessonActive(false)}
                    style={{ padding: '8px 16px', fontSize: '14px' }}
                  >
                    ← Back to Map
                  </button>
                  <div style={{ fontWeight: 900, fontSize: '18px', color: 'var(--ink)' }}>
                    {lesson.title}
                  </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <button
                        className="duo-button duo-button-secondary"
                        onClick={() => setIsGuidebookOpen(true)}
                        style={{ padding: '6px 12px', fontSize: '13px' }}
                      >
                        📖 Guidebook
                      </button>
                      <div className="duo-type-badge duo-type-practice">
                        +15 XP
                      </div>
                  </div>
                </div>

                <main className="duo-card" aria-label="Lesson content">
                  <div className="duo-card-header">
                    <span className={`duo-type-badge duo-type-${lesson.type || 'practice'}`}>
                      {(lesson.type || 'practice').toUpperCase()}
                    </span>
                    <span className="duo-difficulty-badge">
                      {lesson.difficulty.toUpperCase()} • {lesson.duration_minutes} MINS
                    </span>
                  </div>

                  <h2 className="duo-lesson-title">{lesson.title}</h2>
                  <p className="duo-instruction">{lesson.description}</p>

                  {/* Character Mascot Coach */}
                  <div style={{ marginBottom: '20px' }}>
                    <PatchworkCharacter name="patch" state={charState} speech={charSpeech} />
                  </div>

                  {/* Interactive Exercise — phase-driven learning loop */}
                  {lessonHasExercises && !lessonComplete && currentExercise ? (
                    <ExercisePanel
                      exercise={currentExercise}
                      exerciseInput={exerciseInput}
                      exercisePhase={exercisePhase}
                      exerciseFeedback={exerciseFeedback}
                      exercisePosition={exercisePosition}
                      exerciseTotal={exerciseTotal}
                      completedExerciseCount={completedExerciseCount}
                      onInputChange={setExerciseInput}
                      onSubmit={() => submitSubLessonExercise({ ...currentExercise, sublessonId: currentExercise.sublessonId })}
                      onContinue={continueToNextExercise}
                      onRetry={retryCurrentExercise}
                      onRunCode={runTests}
                      isRunningCode={isRunning}
                    />
                  ) : (
                    <CodeEditor value={code} onChange={setCode} filename="exercise.py" onKeyDown={handleEditorKeyDown} />
                  )}
                </main>

                {/* Immediate Test Results */}
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
                    {results.map((r) => (
                      <div key={r.name} style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '14px', fontWeight: 700 }}>
                        <span role="img" aria-label={r.passed ? 'Passed' : 'Failed'}>{r.passed ? '✓' : '×'}</span>
                        <span>{r.name}</span>
                        {!r.required && <span style={{ fontSize: '10px', background: 'rgba(0,0,0,0.1)', padding: '2px 6px', borderRadius: '4px' }}>opt</span>}
                      </div>
                    ))}
                  </div>
                )}

                {/* Tutor Coach Box */}
                <aside aria-label="Tutor feedback">
                  <div className="duo-tutor-box" role="status" aria-label="Tutor feedback">
                    <div className="duo-tutor-avatar">P</div>
                    <div>
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

                {/* Lesson-Complete Celebration */}
                {celebration && (
                  <div className="duo-feedback-panel success" role="status">
                    <div className="duo-feedback-title">
                      <span>🎉 Lesson Complete!</span>
                    </div>
                    <p style={{ fontWeight: 700, marginBottom: '8px' }}>
                      Awesome work! You completed every exercise in this lesson.
                    </p>
                    {celebration.xpEarned > 0 && (
                      <p style={{ fontWeight: 700, color: '#16a34a', marginBottom: '16px' }}>
                        +{celebration.xpEarned} XP earned
                      </p>
                    )}
                    <div style={{ display: 'flex', gap: '12px' }}>
                      {celebration.nextLessonId ? (
                        <button className="duo-button duo-button-primary" onClick={goToNextLesson}>
                          Next Lesson →
                        </button>
                      ) : null}
                      <button
                        className="duo-button duo-button-secondary"
                        onClick={() => {
                          setCelebration(null)
                          setIsLessonActive(false)
                          setLesson(null)
                        }}
                      >
                        Back to Course
                      </button>
                    </div>
                  </div>
                )}

                {/* Session Notes */}
                <div style={{ marginTop: '16px' }}>
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

                {/* Course Navigation Bar in Focused Lesson View */}
                <div className="duo-sidebar-lessons-nav" style={{ marginTop: '24px' }}>
                  <h3 style={{ fontSize: '13px', fontWeight: 800, color: 'var(--ink-soft)', textTransform: 'uppercase', marginBottom: '8px' }}>Course Navigation</h3>
                  <nav aria-label="Lessons" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {safeLessons.map((item) => {
                      const isActive = lesson?.id === item.id
                      let statusLabel = 'Available'
                      if (item.status === 'completed') statusLabel = 'Completed'
                      else if (item.status === 'locked') statusLabel = 'Locked'
                      else if (item.status === 'current' || isActive) statusLabel = 'Current lesson'

                      return (
                        <button
                          key={item.id}
                          id={`lesson-nav-${item.id}`}
                          className={`duo-nav-item ${isActive ? 'active' : ''}`}
                          onClick={() => loadLesson(item, true)}
                          disabled={item.status === 'locked' || isLoadingLesson}
                          aria-current={isActive ? 'page' : undefined}
                          aria-label={`${item.title} — ${statusLabel}`}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '8px 12px',
                            fontSize: '13px',
                            fontWeight: 800,
                            borderRadius: '8px',
                            border: '2px solid',
                            borderColor: isActive ? 'var(--blue-dark)' : 'var(--line)',
                            background: isActive ? '#ddf4ff' : '#fff',
                            cursor: item.status === 'locked' ? 'not-allowed' : 'pointer'
                          }}
                        >
                          <span>{item.title}</span>
                          <span style={{ fontSize: '11px', opacity: 0.7 }}>{statusLabel}</span>
                        </button>
                      )
                    })}
                  </nav>
                </div>
              </div>
            ) : (
              /* ─── COURSE MAP VIEW (COMPACT UNITS) ────────────────────────── */
              <>
                <div className="duo-center-column">
                  {/* Strict daily progression hero card */}
                  <div className="duo-widget-card" style={{ width: '100%', marginBottom: '24px' }}>
                    <div className="duo-widget-title">
                      <span>📅 Day {dailyProgress.currentDay} — Daily Progress</span>
                      <span className="duo-widget-link">{selectedLanguage.toUpperCase()} TRACK</span>
                    </div>
                    <div className="duo-quest-progress-bg">
                      <div className="duo-quest-progress-fill" style={{ width: `${progressPct}%` }} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', fontSize: '12px', fontWeight: 700 }}>
                      <span>{completedCount} of {safeLessons.length} lessons done</span>
                      <span>{Math.round(progressPct)}%</span>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', marginTop: '12px', fontSize: '13px', fontWeight: 800 }}>
                      <span>🔥 Streak: {gamification.streakCount || 0} days</span>
                      <span>❤️ {unlimitedHearts ? '∞' : hearts} hearts</span>
                      <span>⭐ {xp} XP • Level {level}</span>
                    </div>
                  </div>

                  {unitGroups.map((unit, uIdx) => (
                    <div key={unit.id} className="duo-widget-card" style={{ width: '100%', marginBottom: '32px' }}>
                      <div className="duo-unit-banner" style={{ background: uIdx % 2 === 0 ? 'var(--green)' : 'var(--blue)', boxShadow: uIdx % 2 === 0 ? '0 6px 0 var(--green-dark)' : '0 6px 0 var(--blue-dark)' }}>
                        <div className="duo-unit-info">
                          <span className="duo-unit-subtitle">UNIT {uIdx + 1}</span>
                          <span className="duo-unit-title">{unit.title}</span>
                        </div>
                        <button className="duo-guidebook-btn" onClick={() => setIsGuidebookOpen(true)}>📖 GUIDEBOOK</button>
                      </div>

                      {/* Serpentine Node Path inside Unit */}
                      <div className="duo-path-tree">
                        {unit.lessons.map((item, idx) => {
                          const isActive = lesson?.id === item.id
                          const positions = ['node-pos-center', 'node-pos-left-1', 'node-pos-right-1', 'node-pos-center']
                          const posClass = positions[idx % positions.length]

                          const iconSymbol =
                            item.status === 'completed'
                              ? '✓'
                              : item.type === 'challenge'
                              ? '⚡'
                              : item.type === 'checkpoint'
                              ? '🏆'
                              : '⭐'

                          return (
                            <div key={item.id} className={`duo-path-row ${posClass}`} style={{ margin: '8px 0' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                                <button
                                  id={`lesson-node-${item.id}`}
                                  className={`duo-path-circle-btn ${item.status}`}
                                  onClick={() => loadLesson(item, true)}
                                  disabled={item.status === 'locked' || isLoadingLesson}
                                  title={item.title}
                                  aria-label={item.title}
                                >
                                  {isActive && item.status !== 'locked' && (
                                    <div className="duo-start-dialog">START</div>
                                  )}
                                  <span>{iconSymbol}</span>
                                </button>
                                <div style={{ display: 'flex', flexDirection: 'column' }}>
                                  <span style={{ fontWeight: 900, fontSize: '15px', color: 'var(--ink)' }}>{item.title}</span>
                                  <span style={{ fontWeight: 700, fontSize: '12px', color: 'var(--ink-soft)', textTransform: 'uppercase' }}>
                                    {item.status} • {item.duration_minutes} MINS
                                  </span>
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Right Sidebar Widgets */}
                <aside className="duo-right-sidebar" aria-label="Course stats and quests">
                  <div className="duo-widget-card">
                    <div className="duo-widget-title">
                      <span>Active Track</span>
                      <span className="duo-widget-link">{selectedLanguage.toUpperCase()} TRACK</span>
                    </div>
                    <div className="duo-course-tabs" aria-label="Course track selector">
                      {[
                        { lang: 'python', label: 'Python' },
                        { lang: 'java', label: 'Java' },
                        { lang: 'cpp', label: 'C++' },
                      ].map(({ lang, label }) => (
                        <button
                          key={lang}
                          className={`duo-course-tab ${selectedLanguage === lang ? 'active' : ''}`}
                          onClick={() => handleCourseChange(lang)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="duo-widget-card">
                    <div className="duo-widget-title">
                      <span>Daily Quests</span>
                      <button className="duo-widget-link" onClick={() => setActiveTab('quests')}>VIEW ALL</button>
                    </div>
                    <div className="duo-quest-item">
                      <span className="duo-quest-icon">⚡</span>
                      <div className="duo-quest-body">
                        <div className="duo-quest-name">Earn {gamification.dailyGoal || 30} XP</div>
                        <div className="duo-quest-progress-bg">
                          <div className="duo-quest-progress-fill" style={{ width: '50%' }} />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="duo-widget-card">
                    <div className="duo-widget-title">
                      <span>Bronze League</span>
                      <button className="duo-widget-link" onClick={() => setActiveTab('leaderboards')}>VIEW</button>
                    </div>
                    <p style={{ fontSize: '14px', color: 'var(--ink-soft)', fontWeight: 600 }}>
                      Top 5 learners advance to Silver League on Sunday!
                    </p>
                  </div>

                  {/* Navigation Element inside Right Sidebar */}
                  <div className="duo-sidebar-lessons-nav" style={{ marginTop: '12px' }}>
                    <h3 style={{ fontSize: '13px', fontWeight: 800, color: 'var(--ink-soft)', textTransform: 'uppercase', marginBottom: '8px' }}>Course Navigation</h3>
                    <nav aria-label="Lessons" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {safeLessons.map((item) => {
                        const isActive = lesson?.id === item.id
                        let statusLabel = 'Available'
                        if (item.status === 'completed') statusLabel = 'Completed'
                        else if (item.status === 'locked') statusLabel = 'Locked'
                        else if (item.status === 'current' || isActive) statusLabel = 'Current lesson'

                        return (
                          <button
                            key={item.id}
                            id={`lesson-nav-${item.id}`}
                            className={`duo-nav-item ${isActive ? 'active' : ''}`}
                            onClick={() => loadLesson(item, true)}
                            disabled={item.status === 'locked' || isLoadingLesson}
                            aria-current={isActive ? 'page' : undefined}
                            aria-label={`${item.title} — ${statusLabel}`}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              padding: '8px 12px',
                              fontSize: '13px',
                              fontWeight: 800,
                              borderRadius: '8px',
                              border: '2px solid',
                              borderColor: isActive ? 'var(--blue-dark)' : 'var(--line)',
                              background: isActive ? '#ddf4ff' : '#fff',
                              cursor: item.status === 'locked' ? 'not-allowed' : 'pointer'
                            }}
                          >
                            <span>{item.title}</span>
                            <span style={{ fontSize: '11px', opacity: 0.7 }}>{statusLabel}</span>
                          </button>
                        )
                      })}
                    </nav>
                  </div>
                </aside>
              </>
            )}
          </div>
        )}

        {/* ─── TAB 2: CREATE AI COURSE VIEW ──────────────────────────── */}
        {activeTab === 'create' && (
          <CreatePage
            onCourseReady={async (cid) => {
              await fetchCourses()
              await handleCourseChange(cid)
              setActiveTab('learn')
              setIsLessonActive(false)
            }}
          />
        )}

        {/* ─── Modal: Material Ingestion & Custom Course Creation ─────────── */}
        {showCreateModal && (
          <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
            <div className="modal-card" onClick={(e) => e.stopPropagation()}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h2 style={{ fontSize: '20px', fontWeight: 900 }}>Create Custom Patchwork Course</h2>
                <button onClick={() => setShowCreateModal(false)} style={{ fontSize: '20px', fontWeight: 900, cursor: 'pointer' }}>×</button>
              </div>

              <p style={{ fontSize: '14px', color: 'var(--ink-soft)', marginBottom: '16px', fontWeight: 700 }}>
                Paste a YouTube URL / Playlist, Transcript / Notes, or upload material. Patchwork will automatically extract concepts and generate an interactive curriculum.
              </p>

              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                {[
                  { type: 'youtube_url', label: 'YouTube URL / Playlist' },
                  { type: 'transcript', label: 'Transcript / Notes' },
                  { type: 'file_upload', label: 'Upload Material' },
                ].map(({ type, label }) => (
                  <button
                    key={type}
                    onClick={() => setMaterialType(type as any)}
                    className={`duo-button ${materialType === type ? 'duo-button-primary' : 'duo-button-secondary'}`}
                    style={{ padding: '8px 12px', fontSize: '12px', flex: 1 }}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px' }}>
                <input
                  type="text"
                  placeholder="Course Title (e.g. Master React Fast)"
                  value={customTitle}
                  onChange={(e) => setCustomTitle(e.target.value)}
                  style={{ padding: '10px 14px', borderRadius: '10px', border: '2px solid var(--line)', fontWeight: 700 }}
                />

                {materialType === 'youtube_url' ? (
                  <input
                    type="text"
                    placeholder="https://www.youtube.com/watch?v=... or playlist URL"
                    value={materialInput}
                    onChange={(e) => setMaterialInput(e.target.value)}
                    style={{ padding: '10px 14px', borderRadius: '10px', border: '2px solid var(--line)', fontWeight: 700 }}
                  />
                ) : (
                  <textarea
                    rows={5}
                    placeholder="Paste transcripts, study notes, or raw material content here..."
                    value={materialInput}
                    onChange={(e) => setMaterialInput(e.target.value)}
                    style={{ padding: '10px 14px', borderRadius: '10px', border: '2px solid var(--line)', fontWeight: 700, fontFamily: 'inherit' }}
                  />
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button
                  className="duo-button duo-button-secondary"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
                <button
                  className="duo-button duo-button-primary"
                  onClick={handleGenerateCourse}
                  disabled={isGeneratingCourse || (!materialInput.trim() && !customTitle.trim())}
                >
                  {isGeneratingCourse ? 'Analyzing & Generating…' : 'Generate Course ✨'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB 3: LEADERBOARDS VIEW ──────────────────────────────────── */}
        {activeTab === 'leaderboards' && (
          <div className="duo-page-container">
            {isLoadingLesson && (
              <div role="status" aria-label="Loading lesson" style={{ position: "fixed", top: "12px", right: "24px", background: "var(--yellow)", color: "#000", padding: "8px 16px", borderRadius: "20px", fontWeight: 900, zIndex: 9999 }}>
                Loading lesson…
              </div>
            )}
            <div className="duo-leaderboard-view">
              <div className="duo-league-banner">
                <div className="duo-league-shield">🛡️</div>
                <div className="duo-league-details">
<h2>{xp >= 500 ? 'Silver League' : xp >= 200 ? 'Bronze League' : 'Copper League'}</h2>
                  <p>Rank up by earning XP. Level {level} • {xp} XP — {xpForLevel(level + 1) - xp} XP to Level {level + 1}</p>
                </div>
              </div>

              {/* Real server-backed leaderboard */}
              <div className="duo-rank-list">
                {(leaderboardData || [
                  { rank: 1, name: 'You (Patchwork Learner)', xp, is_user: true },
                  { rank: 2, name: 'Alex Coder', xp: Math.max(0, xp - 20), is_user: false },
                  { rank: 3, name: 'DevSamurai', xp: Math.max(0, xp - 50), is_user: false },
                ]).map((entry: any, idx: number) => (
                  <div key={entry.name || idx} className={`duo-rank-item ${entry.is_user ? 'user-self' : ''}`}>
                    <div className={`duo-rank-num top-${entry.rank || idx + 1}`}>{entry.rank || idx + 1}</div>
                    <div className="duo-user-avatar-circle">{(entry.name || 'P')[0]}</div>
                    <div className="duo-rank-name">{entry.name}</div>
                    <div className="duo-rank-xp">{entry.xp} XP</div>
                  </div>
                ))}
              </div>

              <div className="duo-widget-card" style={{ marginTop: '16px' }}>
                <div className="duo-widget-title">
                  <span>📊 Your Stats</span>
                  <span className="duo-widget-link">TRACK: {selectedLanguage.toUpperCase()}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px', fontSize: '14px', fontWeight: 800 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>🔥 Day Streak</span>
                    <span>{gamification.streakCount || 0} days</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>📅 Current Day</span>
                    <span>Day {dailyProgress.currentDay}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>⚡ XP Today</span>
                    <span>{gamification.dailyXp} / {gamification.dailyGoal}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>⭐ Total XP</span>
                    <span>{xp}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>🏅 Level</span>
                    <span>{level}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>❤️ Hearts</span>
                    <span>{unlimitedHearts ? '∞ (Unlimited)' : `${hearts} / ${gamification.maxHearts || 5}`}</span>
                  </div>
                </div>
                <div style={{ marginTop: '12px', fontSize: '12px', color: 'var(--ink-soft)', fontWeight: 600 }}>
                  Keep a daily streak going — complete lessons each day to keep your 🔥 alive.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB 4: QUESTS VIEW ────────────────────────────────────────── */}
        {activeTab === 'quests' && (
          <div className="duo-page-container">
            {isLoadingLesson && (
              <div role="status" aria-label="Loading lesson" style={{ position: "fixed", top: "12px", right: "24px", background: "var(--yellow)", color: "#000", padding: "8px 16px", borderRadius: "20px", fontWeight: 900, zIndex: 9999 }}>
                Loading lesson…
              </div>
            )}
            <div className="duo-quests-view">
              <div className="duo-quest-card">
                <h2 style={{ fontSize: '22px', fontWeight: 900 }}>Daily Quests</h2>
                <div className="duo-quest-item">
                  <div className="duo-quest-icon">⚡</div>
                  <div className="duo-quest-body">
                    <div className="duo-quest-name">Earn {gamification.dailyGoal || 30} XP</div>
                    <div className="duo-quest-progress-bg">
                      <div className="duo-quest-progress-fill" style={{ width: `${Math.min(100, (xp / (gamification.dailyGoal || 30)) * 100)}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB 5: PROFILE VIEW ───────────────────────────────────────── */}
        {activeTab === 'profile' && (
          <div className="duo-page-container">
            {isLoadingLesson && (
              <div role="status" aria-label="Loading lesson" style={{ position: "fixed", top: "12px", right: "24px", background: "var(--yellow)", color: "#000", padding: "8px 16px", borderRadius: "20px", fontWeight: 900, zIndex: 9999 }}>
                Loading lesson…
              </div>
            )}
            <div className="duo-profile-view">
              <div className="duo-profile-header">
                <div className="duo-profile-avatar-large">P</div>
                <div className="duo-profile-meta">
                  <h1>Patchwork Learner</h1>
                  <p className="duo-profile-handle">@patchwork_coder • Joined Sept 2026</p>
                </div>
              </div>

              <div className="duo-stats-grid">
                <div className="duo-stat-card">
                  <div className="duo-stat-card-icon">🔥</div>
                  <div>
                    <div className="duo-stat-card-val">{gamification.streakCount || 0}</div>
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
                  <div className="duo-stat-card-icon">❤️</div>
                  <div>
                    <div className="duo-stat-card-val">{unlimitedHearts ? '∞' : hearts}</div>
                    <div className="duo-stat-card-lbl">Hearts</div>
                  </div>
                </div>
                <div className="duo-stat-card">
                  <div className="duo-stat-card-icon">📅</div>
                  <div>
                    <div className="duo-stat-card-val">{dailyProgress.currentDay}</div>
                    <div className="duo-stat-card-lbl">Current Day</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── Bottom Footer Action Bar (only rendered inside active lesson workspace) ──────────────────────────────────── */}
        {isLessonActive && lesson && (
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
        )}
      </div>

      {showOutofHeartsModal && (
        <div className="modal-overlay" onClick={() => setShowOutofHeartsModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()} style={{ textAlign: 'center', maxWidth: '400px' }}>
            <div style={{ fontSize: '48px', marginBottom: '12px' }}>💔</div>
            <h2 style={{ fontSize: '22px', fontWeight: 900, marginBottom: '12px' }}>You are Out of Hearts!</h2>
            <p style={{ fontSize: '14px', color: 'var(--ink-soft)', marginBottom: '20px', fontWeight: 700 }}>
              Practice past material or refill hearts to keep learning, or turn on Unlimited Hearts in Settings!
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <button
                className="duo-button duo-button-primary"
                onClick={() => {
                  setHearts(5)
                  saveGameState({ hearts: 5 })
                  setShowOutofHeartsModal(false)
                }}
              >
                Refill 5 Hearts ❤️
              </button>
              <button
                className="duo-button duo-button-secondary"
                onClick={() => {
                  setUnlimitedHearts(true)
                  setShowOutofHeartsModal(false)
                }}
              >
                Enable Unlimited Hearts ∞
              </button>
            </div>
          </div>
        </div>
      )}

      <GuidebookPanel
        isOpen={isGuidebookOpen}
        onClose={() => setIsGuidebookOpen(false)}
        language={selectedLanguage}
        conceptTitle={lesson?.concept_title}
      />

      {/* ─── Settings Modal (providers + gameplay) ─────────────────────────── */}
      <Settings
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
        backendUrl=""
        onBackendUrlChange={() => {}}
        unlimitedHearts={unlimitedHearts}
        hearts={hearts}
        onToggleUnlimitedHearts={(value) => {
          const next = applyUnlimitedHearts(value)
          setUnlimitedHearts(next.unlimitedHearts)
          setHearts(next.hearts)
        }}
        onRestoreHearts={() => {
          const next = restoreHearts(1)
          setHearts(next.hearts)
        }}
        gamification={{
          xp,
          level,
          streak: gamification.streakCount || 0,
          currentDay: dailyProgress.currentDay,
          dailyXp: gamification.dailyXp || 0,
          dailyGoal: gamification.dailyGoal || 30,
        }}
      />
    </div>
  )
}

export default App
