import { safeGetItem, safeSetItem, codeDraftKey, readCodeDraft, writeCodeDraft } from './utils/storage'
import { widgetFor } from './utils/exerciseTypes'
 import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { GuidebookPanel } from './components/GuidebookPanel'
import { CreatePage } from './components/CreatePage'
import Settings from './components/Settings'
import ExercisePanel from './components/ExercisePanel'
import ExerciseWorkspace from './components/ExerciseWorkspace'
import { TutorActions } from './components/TutorActions'
import { api, type ExerciseResult, type LeaderboardEntry, type LessonProgress, type Material, type MaterialCompletionResult, type MistakeItem, type HeartStatus, type TestOutResult, type UserProfile } from './api'
import { LearnPath } from './components/duo/LearnPath'
import { PracticeHub } from './components/duo/PracticeHub'
import { QuestsPage } from './components/duo/QuestsPage'
import { CoursesPage } from './components/duo/CoursesPage'
import { coursePathTitle as buildCoursePathTitle } from './components/duo/courseDisplay'
import {
  getGamificationState,
  recordActivity,
  getHearts,
  restoreHearts,
  setUnlimitedHearts as applyUnlimitedHearts,
  saveGameState,
  restoreGameState,
  getDailyProgress,
  levelFromXp,
} from './utils/gamification'
import { playPatchworkSound } from './utils/audio'
import {
  allBlanksFilled,
  assembleFillBlankCode,
  buildFillBlankTemplate,
  extractAnswersFromEdited,
  isFillBlankCodeComplete,
} from './utils/assembleFillBlankCode'

// ─── Types ────────────────────────────────────────────────────────────────────
type TestResult = {
  name: string
  passed: boolean
  required: boolean
  description: string
  error: string | null
}

const CODE_EXERCISE_TYPES = ['code', 'tiny_coding', 'identify_mistake']
const FILL_EXERCISE_TYPES = ['fill_blank', 'code_completion']

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
  xp_reward?: number
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

// File extensions used by the sandbox for each course track (python-based
// tracks — DSA, ML, AI, Fullstack — execute plain Python).
const LANGUAGE_FILE_EXT: Record<string, string> = {
  python: 'py', py: 'py', dsa: 'py', ml: 'py', 'ml-math': 'py', ai: 'py',
  fullstack: 'py', javascript: 'js', typescript: 'ts', java: 'java',
  cpp: 'cpp', 'c++': 'cpp', sql: 'sql',
}

/** Neutral editor prompt; anything else in `feedback` is tutor output. */
const DEFAULT_FEEDBACK = 'Run your code to get immediate feedback from the local sandbox.'

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
  source?: { name: string; url: string; license?: string } | null
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
  const [activeTab, setActiveTab] = useState<'learn' | 'practice' | 'quests' | 'courses' | 'create' | 'leaderboards' | 'profile'>('learn')
  const [isGuidebookOpen, setIsGuidebookOpen] = useState(false)
  const [courses, setCourses] = useState<CourseSummary[]>([])
  const [selectedLanguage, setSelectedLanguage] = useState<string>(() => {
    return safeGetItem('patchwork_active_language') || 'python'
  })
  const [lessons, setLessons] = useState<LessonSummary[]>([])
  const [lesson, setLesson] = useState<Lesson | null>(null)
  const [code, setCode] = useState('')
  const [results, setResults] = useState<TestResult[] | null>(null)
  const [hintLevel, setHintLevel] = useState(1)
  const [feedback, setFeedback] = useState(DEFAULT_FEEDBACK)
  const [aiEnabled, setAiEnabled] = useState(true)
  const [soundEnabled, setSoundEnabled] = useState<boolean>(() => {
    const saved = safeGetItem('patchwork_sound_enabled')
    return saved !== null ? saved === 'true' : true
  })
  const [providersOverview, setProvidersOverview] = useState<ProvidersOverview | null>(null)
  const [selectedProvider, setSelectedProvider] = useState<string>('ollama')
  const [previousHints, setPreviousHints] = useState<string[]>([])
  const [tutorSource, setTutorSource] = useState<'ai' | 'ai_repaired' | 'offline' | null>(null)
  const [tutorLevel, setTutorLevel] = useState(1)
  // The full answer is a deliberate, two-tap act of giving up — never a
  // lightbulb-shaped surprise — and it is always reversible.
  const [answerArmed, setAnswerArmed] = useState(false)
  const [restoreSnapshot, setRestoreSnapshot] = useState<
    | { kind: 'lesson'; code: string }
    | { kind: 'exercise'; exerciseId: string; value: Record<string, any> }
    | null
  >(null)
  const [isRunning, setIsRunning] = useState(false)
  const [isLoadingLesson, setIsLoadingLesson] = useState(false)
  const [isTutorLoading, setIsTutorLoading] = useState(false)
  const [sessionNotes, setSessionNotes] = useState<string[]>([])
  const [noteInput, setNoteInput] = useState('')
  const [backendError, setBackendError] = useState(false)
  const [xp, setXp] = useState(0)
  const [level, setLevel] = useState(1)
  const [leaderboardEntries, setLeaderboardEntries] = useState<LeaderboardEntry[]>([])
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null)
  const [xpGainPopup, setXpGainPopup] = useState<number | null>(null)
  const [exerciseInput, setExerciseInput] = useState<any>({})
  const [showTestOutModal, setShowTestOutModal] = useState(false)
  const [testOutSubmissions, setTestOutSubmissions] = useState<Record<string, any>>({})
  const [testOutResult, setTestOutResult] = useState<any>(null)
  const [charSubTab, setCharSubTab] = useState<'syntax' | 'keywords' | 'types' | 'operators'>('syntax')

  // Gamification & Hearts State
  const [showOutofHeartsModal, setShowOutofHeartsModal] = useState(false)

  // Custom Course Generation State
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [materialType, setMaterialType] = useState<'youtube_url' | 'transcript' | 'file_upload'>('youtube_url')
  const [materialInput, setMaterialInput] = useState('')
  const [customTitle, setCustomTitle] = useState('')
  const [isGeneratingCourse, setIsGeneratingCourse] = useState(false)

  // Focused Lesson Mode State
  const [isLessonActive, setIsLessonActive] = useState(false)

  // Materials state
  const [materials, setMaterials] = useState<Material[]>([])
  const [completedMaterialIds, setCompletedMaterialIds] = useState<string[]>([])

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
  const [celebration, setCelebration] = useState<{
    xpEarned: number
    nextLessonId: string | null
    mistakeFree?: boolean
    boss?: boolean
  } | null>(null)
  // Flow-state tracking for the current lesson visit (combo/perfect detection).
  const visitMistakesRef = useRef(0)

  // Hearts. The server owns the pool (see backend/hearts.py); these are a
  // mirror for rendering, so editing localStorage can no longer buy infinite
  // attempts. `applyHearts` is the only writer, and every grading response
  // carries the authoritative status.
  const [hearts, setHearts] = useState<number>(() => getHearts())
  const [maxHearts, setMaxHearts] = useState<number>(5)
  const [secondsToNextHeart, setSecondsToNextHeart] = useState<number>(0)
  const [unlimitedHearts, setUnlimitedHearts] = useState<boolean>(
    () => getGamificationState().unlimitedHearts
  )
  const [showSettings, setShowSettings] = useState(false)

  const applyHearts = useCallback((status?: HeartStatus | null) => {
    if (!status) return
    setHearts(status.hearts)
    setMaxHearts(status.max_hearts)
    setUnlimitedHearts(status.unlimited)
    setSecondsToNextHeart(status.seconds_to_next_heart)
    // Keep the localStorage mirror so a cold start still shows the right count
    // before the first response arrives.
    saveGameState({ hearts: status.hearts, unlimitedHearts: status.unlimited })
  }, [])

  useEffect(() => {
    api.hearts().then(applyHearts)
  }, [applyHearts])

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
  // The server owns the mistake queue; this mirrors only the items that are
  // due right now, which is what makes a parked step reappear without also
  // holding a lesson hostage to its recall timer.
  const [mistakes, setMistakes] = useState<MistakeItem[]>([])

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

  // The current exercise is the first one still owed: a step that is due for
  // re-review comes before an untouched one. Without this, "Review your
  // misses" opened the lesson and skipped straight past the exercise it was
  // meant to re-serve, because that exercise was already in
  // completed_exercise_ids.
  const dueReviewIds = useMemo(() => {
    if (!lesson?.id) return new Set<string>()
    return new Set(
      mistakes.filter((item) => item.lesson_id === lesson.id).map((item) => item.exercise_id)
    )
  }, [mistakes, lesson?.id])

  const currentExerciseIndex = useMemo(() => {
    const reviewIndex = allExercises.findIndex((ex) => dueReviewIds.has(ex.id))
    if (reviewIndex >= 0) return reviewIndex
    return allExercises.findIndex((ex) => !completedExerciseIds.has(ex.id))
  }, [allExercises, completedExerciseIds, dueReviewIds])
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
  const currentExerciseIsCode = useMemo(() => {
    if (!currentExercise) return false
    return CODE_EXERCISE_TYPES.includes((currentExercise.type || 'code').toLowerCase().trim())
  }, [currentExercise])
  const currentExerciseIsFill = useMemo(() => {
    if (!currentExercise) return false
    return FILL_EXERCISE_TYPES.includes((currentExercise.type || '').toLowerCase().trim())
  }, [currentExercise])
  const showLessonRunCode = !lessonHasExercises || lessonComplete || currentExerciseIsCode

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
    api.materials(selectedLanguage).then((data) => {
      if (data) setMaterials(data)
    })
  }, [selectedLanguage])

  const refreshMistakes = useCallback(() => {
    api
      .mistakes(selectedLanguage)
      .then((data) => setMistakes(Array.isArray(data?.due) ? data.due : []))
      .catch(() => setMistakes([]))
  }, [selectedLanguage])

  useEffect(() => {
    refreshMistakes()
    // The queue is time-based: an item parked for a recall gap becomes due
    // while the learner is doing something else. Re-poll whenever the Practice
    // hub is opened, or "Review your misses" silently never reappears.
  }, [refreshMistakes, lesson?.id, activeTab])

  const handleCompleteMaterial = async (id: string, user_answer?: string): Promise<MaterialCompletionResult | null> => {
    const res = await api.completeMaterial(id, user_answer)
    if (res && res.passed) {
      if (res.xp_awarded > 0) {
        setXp((prev) => prev + res.xp_awarded)
        saveGameState({ xp: xp + res.xp_awarded })
        playPatchworkSound('success')
      }
      setCompletedMaterialIds((prev) => Array.from(new Set([...prev, id])))
    }
    return res
  }

  useEffect(() => {
    setExercisePhase('answering')
    setExerciseFeedback(null)
  }, [currentExercise?.id])

  // ─── Fetch Leaderboard ──────────────────────────────────────────────────────
  const fetchLeaderboard = useCallback(async () => {
    try {
      const data = await api.leaderboard()
      if (Array.isArray(data)) {
        setLeaderboardEntries(data)
      }
    } catch (err) {
      console.error('API request failed:', err)
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'leaderboards') {
      fetchLeaderboard()
    }
  }, [activeTab, xp, fetchLeaderboard])

  // ─── Fetch Courses ──────────────────────────────────────────────────────────
  const fetchCourses = useCallback(async () => {
    try {
      const res = await fetch('/api/courses')
      if (res.ok) {
        const data = await res.json()
        setCourses(data)
      }
    } catch (err) {
      console.error('API request failed:', err)
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
    } catch (err) {
      console.error('API request failed:', err)
    }
  }

  // ─── Fetch Provider Status ─────────────────────────────────────────────────
  const fetchProviders = useCallback(async () => {
    const maxAttempts = 5
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        const res = await fetch('/api/ai/providers')
        if (res.ok) {
          const data: ProvidersOverview = await res.json()
          setProvidersOverview(data)
          if (data.current_provider) {
            setSelectedProvider(data.current_provider)
          }
          return
        }
      } catch (err) {
        if (attempt === maxAttempts) {
          console.error('API request failed:', err)
        }
      }
      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 1500))
      }
    }
  }, [])

  // ─── Fetch Progression State for Active Language ──────────────────────────────
  const fetchUserProfile = useCallback(async () => {
    try {
      const data = await api.userProfile()
      if (data) setUserProfile(data)
    } catch (err) {
      console.error('API request failed:', err)
    }
  }, [])

  const fetchProgression = useCallback(async () => {
    try {
      const res = await fetch(`/api/progression?language=${encodeURIComponent(selectedLanguage)}`)
      if (res.ok) {
        const data = await res.json()
        setXp(data.xp || 0)
        setLevel(data.level || Math.floor((data.xp || 0) / 100) + 1)
      }
    } catch (err) {
      console.error('API request failed:', err)
    }
  }, [selectedLanguage])

  // ─── Load Lessons for Language ──────────────────────────────────────────────
  // Landing on the HOME page is intentional: lessons are only opened when the
  // learner clicks a node, never implicitly on load or course switch.
  const fetchLessons = useCallback(async (lang?: string) => {
    try {
      const res = await fetch(`/api/lessons?language=${encodeURIComponent(lang || selectedLanguage)}`)
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
  }, [selectedLanguage])

  // ─── Select Language Course Track ───────────────────────────────────────────
  const handleCourseChange = async (lang: string) => {
    setSelectedLanguage(lang)
    safeSetItem('patchwork_active_language', lang)
    setLesson(null)
    setIsLessonActive(false)
    setCelebration(null)
    setActiveTab('learn')
    try {
      await fetch('/api/courses/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: lang }),
      })
    } catch (err) {
      console.error('Operation failed:', err)
    }
    fetchLessons(lang)
    fetchProgression()
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
    } catch (err) {
      console.error('Operation failed:', err)
    } finally {
      setIsGeneratingCourse(false)
    }
  }

  // ─── Load Detailed Lesson ───────────────────────────────────────────────────
  const loadLesson = async (summary: LessonSummary, openWorkspace = false) => {
    setIsLoadingLesson(true)
    setResults(null)
    setFeedback(DEFAULT_FEEDBACK)
    setHintLevel(1)
    setPreviousHints([])
    setTutorSource(null)
    setAnswerArmed(false)
    setRestoreSnapshot(null)
    setExerciseInput({})
    setCharState('idle')
    setLessonProgress(null)
    setExercisePhase('answering')
    setExerciseFeedback(null)
    setCelebration(null)
    visitMistakesRef.current = 0

    try {
      const [res, prog] = await Promise.all([
        fetch(`/api/lessons/${summary.id}`),
        api.lessonProgress(summary.id),
      ])
      if (!res.ok) throw new Error('Lesson fetch failed')
      const data: Lesson = await res.json()
      setLesson(data)
      if (prog) setLessonProgress(prog)

      const starter = data.starter_code || ''
      const savedDraft = readCodeDraft(codeDraftKey(data.id), starter)
      setCode(savedDraft !== null ? savedDraft : starter)
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
      if (typeof saved.hearts === 'number') setHearts(saved.hearts)
      if (typeof saved.unlimitedHearts === 'boolean') setUnlimitedHearts(saved.unlimitedHearts)
    }
    fetchCourses()
    fetchProviders()
    fetchLessons()
    fetchProgression()
    fetchUserProfile()
  }, [fetchCourses, fetchProviders, fetchLessons, fetchProgression, fetchUserProfile])

  // Persist hearts/unlimited setting whenever they change
  useEffect(() => {
    saveGameState({ hearts, unlimitedHearts })
  }, [hearts, unlimitedHearts])

  // Save code drafts, tagged with the starter they were based on so a revised
  // curriculum starter supersedes the stale draft instead of resurfacing it.
  useEffect(() => {
    if (lesson?.id) {
      writeCodeDraft(codeDraftKey(lesson.id), lesson.starter_code || '', code)
    }
  }, [code, lesson])

  const getRunnableCode = useCallback(() => {
    if (currentExercise && (currentExerciseIsCode || currentExerciseIsFill)) {
      const exState = exerciseInput[currentExercise.id] || {}
      if (currentExerciseIsFill) {
        const template = buildFillBlankTemplate(
          currentExercise.starter_code || (currentExercise as any).code || '',
          currentExercise.blanks,
          currentExercise.question
        )
        const edited = exState.code
        if (edited && !edited.includes('___')) return edited
        const answers: string[] = (exState.answers?.length
          ? exState.answers
          : edited
            ? extractAnswersFromEdited(template, edited)
            : exState.answer
              ? [exState.answer]
              : []
        ).map((answer: string) => String(answer ?? '').split('___').join(''))
        return assembleFillBlankCode(template, answers)
      }
      return (
        exState.code ??
        currentExercise.starter_code ??
        (currentExercise as any).code ??
        code
      )
    }
    return code
  }, [currentExerciseIsCode, currentExerciseIsFill, currentExercise, exerciseInput, code])

  // ─── Run Code & Tests ───────────────────────────────────────────────────────
  const runTests = useCallback(async () => {
    if (!lesson) return
    const codeToRun = getRunnableCode()

    if (currentExerciseIsFill && currentExercise) {
      const template = buildFillBlankTemplate(
        currentExercise.starter_code || (currentExercise as any).code || '',
        currentExercise.blanks,
        currentExercise.question
      )
      const exState = exerciseInput[currentExercise.id] || {}
      const edited = exState.code
      const answers: string[] = (exState.answers?.length
        ? exState.answers
        : edited
          ? extractAnswersFromEdited(template, edited)
          : exState.answer
            ? [exState.answer]
            : []
      ).map((answer: string) => String(answer ?? '').split('___').join(''))
      const blanksReady = edited
        ? isFillBlankCodeComplete(template, edited)
        : allBlanksFilled(template, answers)
      if (!blanksReady) {
        setCharState('confused')
        setCharSpeech('Fill in every blank before running your code.')
        setExerciseInput((prev: any) => ({
          ...prev,
          [currentExercise.id]: {
            ...prev[currentExercise.id],
            runOutput: { error: 'Fill in every blank before running.' },
          },
        }))
        return
      }
    }

    setIsRunning(true)
    setResults(null)
    setCharState('thinking')
    setCharSpeech(
      currentExerciseIsFill
        ? 'Running your code…'
        : 'Testing your code against strict test cases…'
    )

    try {
      const runUrl =
        lessonHasExercises && (currentExerciseIsCode || currentExerciseIsFill) && currentExercise
          ? `/api/lessons/${lesson.id}/exercises/${currentExercise.id}/run`
          : `/api/lessons/${lesson.id}/run`

      const res = await fetch(runUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: codeToRun }),
      })

      const data = await res.json().catch(() => ({}))
      if (res.status === 403 && data?.detail?.error === 'out_of_hearts') {
        applyHearts(data.detail.hearts)
        setShowOutofHeartsModal(true)
        setCharState('confused')
        setCharSpeech('Out of hearts! Review your missed steps to earn one back.')
        setExercisePhase('answering')
        return
      }
      if (!res.ok) {
        const detail = data?.detail
        const message =
          (typeof detail === 'object' && detail?.message) ||
          (typeof detail === 'string' ? detail : null) ||
          data?.message ||
          'Code execution failed. Make sure the backend is running.'
        throw new Error(message)
      }

      if (currentExerciseIsFill && currentExercise) {
        const runError = data.error || null
        const runOutput = {
          stdout: data.stdout || '',
          stderr: data.stderr || '',
          error: runError,
        }
        setExerciseInput((prev: any) => ({
          ...prev,
          [currentExercise.id]: {
            ...prev[currentExercise.id],
            runOutput,
          },
        }))
        if (runError) {
          playPatchworkSound('error', soundEnabled)
          setCharState('confused')
          setCharSpeech(runError)
        } else {
          playPatchworkSound('success', soundEnabled)
          setCharState('happy')
          setCharSpeech('Code ran! Check the output, then tap Check Answer to continue.')
          setFeedback('Code ran — tap Check Answer to save progress and continue.')
        }
        return
      }

      setResults(data.tests || [])
      const allPassed =
        data.passed ||
        (data.tests && data.tests.every((t: TestResult) => !t.required || t.passed))

      if (allPassed) {
        if (lessonHasExercises && currentExerciseIsCode && currentExercise) {
          playPatchworkSound('success', soundEnabled)
          setCharState('happy')
          setCharSpeech('All tests passed! Tap Check Answer to save progress and continue.')
          setFeedback('All tests passed — tap Check Answer to continue.')
          return
        }

        const boss = (lesson?.type || '') === 'checkpoint'
        playPatchworkSound(boss ? 'checkpoint_complete' : 'lesson_complete', soundEnabled)
        setCharState('celebrate')
        setCharSpeech('Outstanding job! All checks passed perfectly!')
        setConsecutiveCorrect((prev) => prev + 1)

        const runXp = Number(data.xp_awarded) || 0
        if (runXp > 0) {
          const activity = recordActivity(runXp)
          setGamification(activity.state)
          triggerXpGain(runXp)
        }
        fetchLessons()
        fetchProgression()

        const nextId =
          data.next_lesson_id ||
          (() => {
            const idx = lessons.findIndex((l) => l.id === lesson?.id)
            return idx >= 0 && idx < lessons.length - 1 ? lessons[idx + 1].id : null
          })()
        setCelebration({
          xpEarned: runXp,
          nextLessonId: nextId ?? null,
          mistakeFree: visitMistakesRef.current === 0,
          boss,
        })
      } else {
        playPatchworkSound('error', soundEnabled)
        setCharState('confused')
        setCharSpeech('Some test checks failed. Take a look at the details below!')
        setConsecutiveCorrect(0)
        visitMistakesRef.current += 1

        // The server already deducted for this failed assessment.
        applyHearts(data.hearts)
        if (data.hearts && data.hearts.hearts <= 0 && !data.hearts.unlimited) {
          setShowOutofHeartsModal(true)
        }
      }
    } catch (err) {
      console.error('Error executing code:', err)
      setFeedback(err instanceof Error ? err.message : 'Error connecting to code execution sandbox.')
      setCharState('confused')
    } finally {
      setIsRunning(false)
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, [
    lesson,
    getRunnableCode,
    soundEnabled,
    triggerXpGain,
    lessons,
    lessonHasExercises,
    currentExerciseIsCode,
    currentExerciseIsFill,
    currentExercise,
    exerciseInput,
    fetchLessons,
    fetchProgression,
  ])

  // ─── Ask AI Tutor ──────────────────────────────────────────────────────────
  const askTutor = async () => {
    if (!lesson || !aiEnabled) return
    setIsTutorLoading(true)
    setCharState('thinking')
    setTutorLevel(hintLevel)

    try {
      // The tutor must see whatever the learner is actually staring at: the
      // current exercise's own answer buffer when one is open, otherwise the
      // lesson-level code buffer.
      const activeExercise = currentExercise
      const exerciseAnswer = activeExercise
        ? (exerciseInput[activeExercise.id]?.code
            ?? exerciseInput[activeExercise.id]?.answer
            ?? activeExercise.starter_code
            ?? '')
        : ''
      const tutorCode = activeExercise ? String(exerciseAnswer) : code
      const tutorInstructions = activeExercise
        ? String(
            activeExercise.question ||
              activeExercise.title ||
              lesson.description ||
              lesson.title
          )
        : lesson.description ||
          lesson.learning_objectives?.[0] ||
          'Complete the coding exercise using the concepts from this lesson.'

      const res = await fetch('/api/tutor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lesson_id: lesson.id,
          lesson_title: lesson.title,
          unit_title: lesson.unit_title || lesson.section_title || '',
          concept_title: lesson.concept_title || '',
          prerequisites: lesson.prerequisites || [],
          instructions: tutorInstructions.slice(0, 2000),
          learning_objective: lesson.learning_objectives?.[0] || '',
          code: tutorCode,
          test_results: results || [],
          previous_hints: previousHints,
          hint_level: hintLevel,
          session_id: 'default',
          user_id: 'default_user',
        }),
      })

      const data = await res.json().catch(() => null)

      if (res.ok && data?.message && data?.available !== false) {
        const source: 'ai' | 'ai_repaired' | 'offline' =
          data.source === 'offline' ? 'offline' : data.source === 'ai_repaired' ? 'ai_repaired' : 'ai'
        setTutorSource(source)
        setFeedback(data.message)
        // Hints saturate at level 4 instead of running off the scale.
        setHintLevel((prev) => Math.min(4, prev + 1))
        setPreviousHints((prev) => [...prev, data.message])
        setCharSpeech(data.message)
        setCharState(source === 'offline' ? 'idle' : 'encouraging')
      } else {
        // Never surface a raw provider error where a hint belongs.
        setTutorSource('offline')
        setHintLevel((prev) => Math.min(4, prev + 1))
        setFeedback(
          'The coach is offline right now. Read the first red check, name the value it wants, ' +
            'then change only the line that produces it.'
        )
        setCharState('confused')
      }
    } catch (err) {
      console.error('Error reaching AI tutor:', err)
      setTutorSource('offline')
      setFeedback(
        'The coach could not be reached. Read the first red check, name the value it wants, ' +
          'then change only the line that produces it.'
      )
      setCharState('confused')
    } finally {
      setIsTutorLoading(false)
    }
  }

  // ─── Show Canonical Answer ─────────────────────────────────────────────────
  // A lightbulb means "hint", so the answer button must not wear one: it asks
  // once, warns, and keeps the learner's own work recoverable afterwards. It
  // targets whichever buffer is on screen — the current step or the lesson.
  const askSolution = async () => {
    if (!lesson) return
    if (!answerArmed) {
      setAnswerArmed(true)
      setTutorSource(null)
      setFeedback(
        'This pastes the complete answer into your editor — it is not a hint. ' +
          'Tap it again to go ahead, or request one more nudge and keep the win.'
      )
      setCharState('thinking')
      setCharSpeech('A nudge keeps the solve yours. Want one more before you give up?')
      return
    }
    setAnswerArmed(false)

    const exercise = currentExercise
    try {
      if (exercise) {
        const res = await fetch(`/api/lessons/${lesson.id}/exercises/${exercise.id}/solution`)
        if (!res.ok) {
          setFeedback('This step has no canonical answer to paste — a nudge will still help.')
          setCharState('thinking')
          return
        }
        const data = await res.json()
        const previous = exerciseInput[exercise.id] || {}
        const type = String(data.type || exercise.type || 'code').toLowerCase()
        const next: Record<string, any> = { ...previous }
        if (type === 'fill_blank' && Array.isArray(data.answers)) {
          const template = buildFillBlankTemplate(
            data.starter_code || exercise.starter_code || '',
            data.blanks || exercise.blanks || [],
            data.question || exercise.question || ''
          )
          next.answers = data.answers
          next.answer = data.answers[0] ?? ''
          next.code = assembleFillBlankCode(template, data.answers)
        } else if (data.solution_code) {
          next.code = data.solution_code
        } else if (typeof data.answer === 'string') {
          next.answer = data.answer
        } else {
          setFeedback('This step has no canonical answer to paste — a nudge will still help.')
          return
        }
        setRestoreSnapshot({ kind: 'exercise', exerciseId: exercise.id, value: previous })
        setExerciseInput((prev: Record<string, any>) => ({ ...prev, [exercise.id]: next }))
        setFeedback(
          'Full answer inserted into this step. Read it, then restore your own attempt and rewrite it.'
        )
        setCharState('idle')
        setCharSpeech('Study it, then restore your own code and write it from scratch.')
        return
      }

      const res = await fetch(`/api/lessons/${lesson.id}/solution`)
      if (res.ok) {
        const data = await res.json()
        setRestoreSnapshot({ kind: 'lesson', code })
        setCode(data.solution_code || '')
        setFeedback(
          'Full answer inserted. Tap "Restore my code" to get your own version back and keep going.'
        )
        setCharState('idle')
        setCharSpeech('Study it, then restore your own code and write it from scratch.')
      }
    } catch (err) {
      console.error('API request failed:', err)
    }
  }

  const restoreAnsweredBuffer = () => {
    if (!restoreSnapshot) return
    if (restoreSnapshot.kind === 'lesson') {
      setCode(restoreSnapshot.code)
    } else {
      const { exerciseId, value } = restoreSnapshot
      setExerciseInput((prev: Record<string, any>) => ({ ...prev, [exerciseId]: value }))
    }
    setRestoreSnapshot(null)
    setFeedback('Your work is back. Run it and take it from there.')
    setCharState('encouraging')
    setCharSpeech('Back to your own work. You have this.')
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

    // Build the submit payload from the shared type registry rather than a
    // second copy of the type lists, so a new backend type cannot arrive here
    // unhandled and quietly submit the wrong shape.
    switch (widgetFor(exType)) {
      case 'fill': {
        const template = buildFillBlankTemplate(
          ex.starter_code || '',
          ex.blanks ?? [],
          ex.question
        )
        const edited = inputState.code
        const answers = (
          edited
            ? extractAnswersFromEdited(template, edited)
            : (inputState.answers || (inputState.answer ? [inputState.answer] : []))
        ).map((a: string) =>
          String(a ?? '').split('___').join('').split('\n')[0].trim()
        )
        payload = { answers, code: edited }
        break
      }
      case 'multi_select':
        payload = { answers: inputState.answers || inputState.selected || [] }
        break
      case 'ordering':
        payload = { order: inputState.order || inputState.answers || [] }
        break
      case 'matching':
        payload = { pairs: inputState.pairs || [] }
        break
      case 'code':
        payload = { code: inputState.code ?? code }
        break
      default:
        payload = { answer: inputState.answer || '' }
    }

    setExercisePhase('checking')
    try {
      const res = await api.submitExercise(lesson.id, ex.id, ex.sublessonId, payload)
      if (res.status === 403) {
        const detail = (await res.json().catch(() => ({})))?.detail
        if (detail?.error === 'out_of_hearts') {
          applyHearts(detail.hearts)
          setShowOutofHeartsModal(true)
          setExercisePhase('answering')
          return
        }
      }
      if (!res.ok) throw new Error('Submission failed')
      const data: ExerciseResult = await res.json()
      // The server just updated the mistake queue from this attempt.
      refreshMistakes()

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
        playPatchworkSound('correct_chime', soundEnabled)
        setConsecutiveCorrect((prev) => {
          const next = prev + 1
          if (next >= 3 && next % 3 === 0) {
            playPatchworkSound('streak_milestone', soundEnabled)
          }
          return next
        })
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
        setConsecutiveCorrect(0)
        visitMistakesRef.current += 1
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

        // A wrong answer is charged by the server; clearing a miss refunds.
        applyHearts(data.hearts)
        if (data.graduated && data.hearts && data.hearts.hearts > 0) {
          setCharSpeech('Cleared from your review list — heart back! ❤️')
        }
        if (data.hearts && data.hearts.hearts <= 0 && !data.hearts.unlimited) {
          setShowOutofHeartsModal(true)
        }
      }
    } catch (err) {
      console.error('Error submitting exercise:', err)
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
      const boss = (lesson?.type || '') === 'checkpoint'
      if (boss) playPatchworkSound('checkpoint_complete', soundEnabled)
      setCelebration({
        xpEarned: earnedXp,
        nextLessonId: nextId ?? null,
        mistakeFree: visitMistakesRef.current === 0,
        boss,
      })
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
    } catch (err) {
      console.error('Operation failed:', err)
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
    safeSetItem('patchwork_sound_enabled', String(next))
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
  const currentProviderStatus = providersOverview?.providers?.find((p) => p?.is_current)
  const hintDisabled = isRunning || !aiEnabled || !isAiAvailable

  const failedRequired = results ? results.filter((r) => r?.required && !r?.passed) : []
  const allPassed = results && results.length > 0 ? failedRequired.length === 0 : false

  // Language Track Display Name
  const coursePathTitle = buildCoursePathTitle(selectedLanguage, courses)
  const profileStreak = userProfile?.streak
  const dailyProgress = getDailyProgress()

  const isCodingType = (ex: Exercise | null | undefined) => {
    if (!ex) return false
    const t = (ex.type || 'code').toLowerCase().trim()
    return CODE_EXERCISE_TYPES.includes(t) || FILL_EXERCISE_TYPES.includes(t)
  }

  const lastCompletedCodingExercise = allExercises.filter(
    (ex) => isCodingType(ex) && completedExerciseIds.has(ex.id)
  ).at(-1) ?? null

  const codingFeedbackActive =
    !currentExercise &&
    (exercisePhase === 'correct' || exercisePhase === 'incorrect') &&
    exerciseFeedback !== null &&
    lastCompletedCodingExercise !== null

  const workspaceExercise = currentExercise ?? (codingFeedbackActive ? lastCompletedCodingExercise : null)

  // Every lesson — with or without exercises — opens the fullscreen workspace.
  const isExerciseWorkspace = isLessonActive && lesson !== null

  // Lessons without an active exercise still get the workspace chrome: the lesson
  // itself is treated as one open-ended code exercise over the shared `code` buffer.
  const lessonWorkspaceExercise = lesson
    ? {
        id: `lesson-${lesson.id}`,
        type: 'code',
        question: lesson.description || lesson.title,
        sublessonTitle: lesson.title,
        starter_code: lesson.starter_code || '',
      }
    : null

  const handleExerciseBack = () => setIsLessonActive(false)

  // ─── One tutor affordance, shared by every workspace surface ───────────────
  // Exercise steps and lesson-level code used to render different chrome, which
  // meant the hint existed in one place only. Both now get the same row and the
  // same hint panel.
  const tutorActionsRow = (
    <div className="ew-footer-actions">
      <TutorActions
        hintDisabled={hintDisabled}
        isTutorLoading={isTutorLoading}
        isAiAvailable={isAiAvailable}
        aiEnabled={aiEnabled}
        answerArmed={answerArmed}
        hasCodeToRestore={restoreSnapshot !== null}
        onHint={askTutor}
        onAnswer={askSolution}
        onRestore={restoreAnsweredBuffer}
        answerDisabled={isRunning}
        buttonClass="ew-btn ew-btn-back"
        answerButtonClass="ew-btn ew-btn-back"
      />
    </div>
  )

  const showTutorPanel =
    isTutorLoading || Boolean(feedback && feedback !== DEFAULT_FEEDBACK)

  const tutorPanel = showTutorPanel ? (
    <aside aria-label="Tutor feedback" className="ew-lesson-tutor">
      <div
        className={`duo-tutor-box${tutorSource === 'offline' ? ' duo-tutor-box--offline' : ''}`}
        role="status"
        aria-label="Tutor feedback"
        data-testid="tutor-box"
        data-source={tutorSource || 'idle'}
      >
        <div className="duo-tutor-avatar">P</div>
        <div className="duo-tutor-body">
          <div className="duo-tutor-name">
            {tutorSource === 'offline' ? 'Coach tip' : 'AI hint'}
            <span className="duo-tutor-meta">
              {tutorSource === 'offline'
                ? 'offline fallback'
                : currentProviderStatus?.name || selectedProvider}
              {' · '}nudge {Math.min(4, Math.max(1, tutorLevel))} of 4
            </span>
          </div>
          <div className="duo-tutor-text">
            {isTutorLoading ? 'Thinking…' : feedback}
          </div>
        </div>
      </div>
    </aside>
  ) : null

  return (
    <div className={`duo-layout${isExerciseWorkspace ? ' duo-layout--exercise-focus' : ''}${activeTab === 'practice' ? ' duo-layout--practice' : ''}`}>
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
            className={`duo-nav-item ${activeTab === 'practice' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('practice')
              setIsLessonActive(false)
            }}
          >
            <span className="duo-nav-icon">💪</span>
            <span>PRACTICE</span>
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
            className={`duo-nav-item ${activeTab === 'courses' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('courses')
              setIsLessonActive(false)
            }}
          >
            <span className="duo-nav-icon">📚</span>
            <span>COURSES</span>
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
                border: '2px solid var(--line)',
                fontSize: '12px',
                fontWeight: 700,
                background: 'var(--input-bg)',
                color: 'var(--ink)',
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

          <div style={{ fontSize: '11px', color: 'var(--muted)', textAlign: 'center' }}>
            {isAiAvailable
              ? `${currentProviderStatus?.name || 'AI provider'} ready`
              : `${currentProviderStatus?.name || 'AI provider'} unavailable (Selected provider is unconfigured or offline)`}
          </div>
        </div>
      </aside>

      {/* ─── Main Viewport Area ─────────────────────────────────────────── */}
      <div className="duo-main-viewport">
        {/* Top Sticky Header Bar (hidden during fullscreen coding exercises) */}
        {!isExerciseWorkspace && activeTab !== 'practice' && (
        <header className="duo-top-header" role="banner">
          <div className="duo-header-left">
            <button
              type="button"
              className="duo-button duo-button-secondary"
              style={{ padding: '6px 12px', fontSize: '12px' }}
              onClick={() => {
                setActiveTab('courses')
                setIsLessonActive(false)
              }}
              aria-label="Open courses"
            >
              {coursePathTitle}
            </button>
          </div>

          <div style={{ flex: 1, maxWidth: '200px', margin: '0 16px' }}>
            <div
              className="duo-progress-bar-bg"
              role="progressbar"
              aria-valuenow={completedCount}
              aria-valuemin={0}
              aria-valuemax={safeLessons.length}
              aria-label="Course progress"
              style={{ height: '12px', background: '#37464f', borderRadius: '999px', overflow: 'hidden' }}
            >
              <div
                className="duo-progress-bar-fill"
                style={{ width: `${progressPct}%`, height: '100%', background: 'var(--green)', borderRadius: '999px' }}
              />
            </div>
          </div>

          <div className="duo-header-stats">
            <div className="duo-stat-pill streak" title="Streak from your server profile">
              <span>🔥 {profileStreak == null ? '—' : profileStreak}</span>
            </div>
            <div className="duo-stat-pill xp" title="Total XP" aria-label={`XP: ${xp}, Level: ${level}`}>
              <span>⭐ {xp} XP</span>
            </div>
            <div
              className="duo-stat-pill hearts"
              title={
                unlimitedHearts
                  ? 'Unlimited hearts'
                  : hearts >= maxHearts
                    ? `${hearts} of ${maxHearts} hearts — full`
                    : `Next heart in ${Math.ceil(secondsToNextHeart / 60)} min, or clear a missed step`
              }
            >
              <span>❤️ {unlimitedHearts ? '∞' : `${hearts}/${maxHearts}`}</span>
            </div>
          </div>
        </header>
        )}

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
              workspaceExercise ? (
                <ExercisePanel
                  exercise={workspaceExercise}
                  exerciseInput={exerciseInput}
                  exercisePhase={exercisePhase}
                  exerciseFeedback={exerciseFeedback}
                  exercisePosition={exercisePosition}
                  exerciseTotal={exerciseTotal}
                  completedExerciseCount={completedExerciseCount}
                  onInputChange={setExerciseInput}
                  onSubmit={() => submitSubLessonExercise({ ...workspaceExercise, sublessonId: workspaceExercise.sublessonId })}
                  onContinue={continueToNextExercise}
                  onRetry={retryCurrentExercise}
                  onRunCode={runTests}
                  isRunningCode={isRunning}
                  lessonId={lesson.id}
                  lessonSource={lesson.source}
                  lessonObjectives={lesson.learning_objectives}
                  combo={consecutiveCorrect}
                  lessonType={lesson.type}
                  onBack={handleExerciseBack}
                  soundEnabled={soundEnabled}
                  onToggleSound={toggleSound}
                  runResults={results}
                  language={selectedLanguage}
                  footerExtra={tutorActionsRow}
                  outputExtra={tutorPanel}
                />
              ) : lessonWorkspaceExercise ? (
                /* ─── FOCUSED LESSON WORKSPACE (no active exercise) ─────── */
                <ExerciseWorkspace
                  lessonMode
                  exercise={lessonWorkspaceExercise}
                  exType="code"
                  exerciseInput={{ [lessonWorkspaceExercise.id]: { code } }}
                  exercisePhase="answering"
                  exerciseFeedback={null}
                  exercisePosition={1}
                  exerciseTotal={1}
                  completedExerciseCount={0}
                  onInputChange={(updater: any) => {
                    const snapshot = { [lessonWorkspaceExercise.id]: { code } }
                    const next = updater(snapshot)
                    const nextCode = next?.[lessonWorkspaceExercise.id]?.code
                    if (typeof nextCode === 'string') setCode(nextCode)
                  }}
                  onContinue={() => {}}
                  onRetry={() => {}}
                  onRun={runTests}
                  isRunning={isRunning}
                  onBack={() => setIsLessonActive(false)}
                  soundEnabled={soundEnabled}
                  onToggleSound={toggleSound}
                  lessonId={lesson.id}
                  lessonSource={lesson.source}
                  lessonObjectives={lesson.learning_objectives}
                  combo={consecutiveCorrect}
                  lessonType={lesson.type}
                  language={selectedLanguage}
                  editorFilename={`exercise.${LANGUAGE_FILE_EXT[selectedLanguage] || 'py'}`}
                  onOpenGuidebook={() => setIsGuidebookOpen(true)}
                  footerExtra={tutorActionsRow}
                  taskExtra={
                    <div className="ew-lesson-notes">
                      <span className="ew-section-label">Session notes</span>
                      <div className="ew-lesson-notes-row">
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
                          className="ew-lesson-notes-input"
                        />
                        <button
                          onClick={addNote}
                          aria-label="Add note"
                          className="ew-btn ew-btn-submit"
                          style={{ padding: '10px 16px' }}
                        >
                          +
                        </button>
                      </div>
                      {sessionNotes.length > 0 && (
                        <ul className="ew-lesson-notes-list">
                          {(sessionNotes ?? []).map((note, i) => (
                            <li key={i}>{note}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  }
                  outputExtra={
                    <>
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
                          {(results ?? []).map((r) => (
                            <div key={r.name} style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '14px', fontWeight: 700 }}>
                              <span role="img" aria-label={r.passed ? 'Passed' : 'Failed'}>{r.passed ? '✓' : '×'}</span>
                              <span>{r.name}</span>
                              {!r.required && <span style={{ fontSize: '10px', background: 'rgba(0,0,0,0.1)', padding: '2px 6px', borderRadius: '4px' }}>opt</span>}
                            </div>
                          ))}
                        </div>
                      )}
                      {tutorPanel}
                    </>
                  }
                  banner={
                    celebration && (
                      <div className={`duo-feedback-panel success ew-lesson-celebration${celebration.mistakeFree ? ' ew-celebration--perfect' : ''}${celebration.boss ? ' ew-celebration--boss' : ''}`} role="status">
                        <div className="duo-feedback-title">
                          <span>{celebration.boss ? '👑 BOSS CLEARED!' : '🎉 Lesson Complete!'}</span>
                          {celebration.mistakeFree && (
                            <span className="ew-perfect-badge">⚡ PERFECT — no mistakes!</span>
                          )}
                        </div>
                        <p style={{ fontWeight: 700, marginBottom: '8px' }}>
                          {celebration.boss
                            ? 'You just mastered a checkpoint — the hardest lesson in the unit!'
                            : 'Awesome work! You completed every exercise in this lesson.'}
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
                    )
                  }
                />
              ) : null
            ) : (
              <LearnPath
                lessons={safeLessons}
                activeLessonId={lesson?.id ?? null}
                isLoadingLesson={isLoadingLesson}
                onSelectLesson={(item) => loadLesson(item, true)}
                onOpenGuidebook={() => setIsGuidebookOpen(true)}
              />
            )}
          </div>
        )}

        {activeTab === 'practice' && (
          <div className="duo-page-container duo-page-container--practice">
            <PracticeHub
              lessons={safeLessons}
              isLoadingLesson={isLoadingLesson}
              onOpenLesson={(item) => {
                setActiveTab('learn')
                void loadLesson(item, true)
              }}
              onOpenGuidebook={() => setIsGuidebookOpen(true)}
              onBack={() => setActiveTab('learn')}
              materials={materials}
              completedMaterialIds={completedMaterialIds}
              onCompleteMaterial={handleCompleteMaterial}
              mistakes={mistakes}
              language={selectedLanguage}
            />
          </div>
        )}

        {activeTab === 'courses' && (
          <div className="duo-page-container">
            <CoursesPage
              courses={courses}
              selectedLanguage={selectedLanguage}
              onSelectCourse={handleCourseChange}
            />
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

        {activeTab === 'leaderboards' && (
          <div className="duo-page-container">
            <div className="duo-leaderboard-view">
              <div className="duo-league-banner">
                <div className="duo-league-shield">LB</div>
                <div className="duo-league-details">
                  <h2>Leaderboard</h2>
                  <p>
                    {leaderboardEntries.find((e) => e.is_current_user)
                      ? `Your rank: #${leaderboardEntries.find((e) => e.is_current_user)!.rank} · ${xp} XP · Level ${level}`
                      : `Level ${level} · ${xp} XP from course progression`}
                  </p>
                </div>
              </div>
              <div className="duo-rank-list">
                {Array.isArray(leaderboardEntries) && leaderboardEntries.length > 0 ? (
                  leaderboardEntries.map((entry) => (
                    <div
                      key={entry.user_id}
                      className={`duo-rank-item ${entry.is_current_user ? 'user-self' : ''}`}
                    >
                      <div className={`duo-rank-num ${entry.rank <= 3 ? `top-${entry.rank}` : ''}`}>
                        {entry.rank}
                      </div>
                      <div className="duo-user-avatar-circle">
                        {entry.username ? entry.username.replace('[Demo] ', '').charAt(0).toUpperCase() : 'U'}
                      </div>
                      <div className="duo-rank-name" style={{ flex: 1, fontWeight: entry.is_current_user ? 800 : 600 }}>
                        {entry.username}{entry.is_current_user ? ' (You)' : ''}{entry.is_demo ? ' · demo' : ''}
                      </div>
                      <div className="duo-rank-xp" style={{ fontWeight: 800 }}>
                        {entry.xp} XP
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="duo-empty-note">No leaderboard entries were returned by the server.</p>
                )}
              </div>
              <div className="duo-widget-card" style={{ marginTop: '16px' }}>
                <div className="duo-widget-title">
                  <span>Your stats</span>
                  <span className="duo-widget-link">TRACK: {selectedLanguage.toUpperCase()}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px', fontSize: '14px', fontWeight: 800 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Streak (profile)</span>
                    <span>{profileStreak == null ? 'Unavailable' : `${profileStreak} days`}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Total XP (progression)</span>
                    <span>{xp}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Level</span>
                    <span>{level}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Hearts</span>
                    <span>{unlimitedHearts ? 'Unlimited' : `${hearts} / ${gamification.maxHearts || 5}`}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'quests' && (
          <div className="duo-page-container">
            <QuestsPage
              courses={courses}
              selectedLanguage={selectedLanguage}
              completedCount={completedCount}
              totalCount={safeLessons.length}
              xp={xp}
              level={level}
            />
          </div>
        )}

        {/* ─── TAB 5: PROFILE VIEW ───────────────────────────────────────── */}
        {activeTab === 'profile' && (
          <div className="duo-page-container">
            <div className="duo-profile-view">
              <div className="duo-profile-header">
                <div className="duo-profile-avatar-large">
                  {(userProfile?.username || 'P').charAt(0).toUpperCase()}
                </div>
                <div className="duo-profile-meta">
                  <h1>{userProfile?.username || 'Profile unavailable'}</h1>
                  <p className="duo-profile-handle">
                    {userProfile ? userProfile.user_id : 'Server profile has not loaded'}
                  </p>
                </div>
              </div>

              <div className="duo-stats-grid">
                <div className="duo-stat-card">
                  <div className="duo-stat-card-icon">🔥</div>
                  <div>
                    <div className="duo-stat-card-val">{profileStreak == null ? '—' : profileStreak}</div>
                    <div className="duo-stat-card-lbl">Streak</div>
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
                  <div className="duo-stat-card-icon">🏅</div>
                  <div>
                    <div className="duo-stat-card-val">{level}</div>
                    <div className="duo-stat-card-lbl">Level</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ─── Bottom Footer Action Bar (only when the workspace is not open) ── */}
        {activeTab === 'learn' && isLessonActive && showLessonRunCode && !isExerciseWorkspace && (
          <footer className="duo-footer-bar">
            <div className="duo-footer-left" style={{ display: 'flex', gap: '12px' }}>
              <TutorActions
                hintDisabled={hintDisabled}
                isTutorLoading={isTutorLoading}
                isAiAvailable={isAiAvailable}
                aiEnabled={aiEnabled}
                answerArmed={answerArmed}
                hasCodeToRestore={restoreSnapshot !== null}
                onHint={askTutor}
                onAnswer={askSolution}
                onRestore={restoreAnsweredBuffer}
                answerDisabled={!lesson || isRunning}
              />
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
                  void api.refillHearts().then((status) => {
                    applyHearts(status)
                    setShowOutofHeartsModal(false)
                  })
                }}
              >
                Refill Hearts ❤️
              </button>
              <button
                className="duo-button duo-button-secondary"
                onClick={() => {
                  void api.setHeartSettings({ unlimited: true }).then((status) => {
                    applyHearts(status)
                    setShowOutofHeartsModal(false)
                  })
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
          applyUnlimitedHearts(value)
          void api.setHeartSettings({ unlimited: value }).then(applyHearts)
        }}
        onRestoreHearts={() => {
          restoreHearts(1)
          void api.hearts().then(applyHearts)
        }}
        gamification={{
          xp,
          level,
          streak: profileStreak ?? 0,
          currentDay: dailyProgress.currentDay,
          dailyXp: gamification.dailyXp || 0,
          dailyGoal: gamification.dailyGoal || 30,
        }}
      />
    </div>
  )
}

export default App
