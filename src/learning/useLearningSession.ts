/**
 * The learning session: every piece of state and behaviour that is NOT
 * navigation, lifted out of App.tsx verbatim so the router can own where the
 * learner is while this owns what they are doing.
 *
 * Deliberately a plain hook over React state + plain fetch: no data library, no
 * second source of truth for progress. The backend still authoritatively owns
 * completion, XP, hearts and the mistake queue.
 *
 * Called once by AppLayout and handed to the screens through the router outlet
 * context, so a screen reads useLearning() instead of closing over App state.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, type ExerciseResult, type HeartStatus, type LeaderboardEntry, type LessonProgress, type Material, type MaterialCompletionResult, type MistakeItem, type TestOutResult, type UserProfile } from '../api'
import { coursePathTitle as buildCoursePathTitle } from '../components/duo/courseDisplay'
import { safeGetItem, safeSetItem, codeDraftKey, readCodeDraft, writeCodeDraft } from '../utils/storage'
import { widgetFor } from '../utils/exerciseTypes'
import {
  getGamificationState,
  recordActivity,
  getHearts,
  getDailyProgress,
  saveGameState,
  restoreGameState,
  levelFromXp,
} from '../utils/gamification'
import { playPatchworkSound } from '../utils/audio'
import {
  allBlanksFilled,
  assembleFillBlankCode,
  buildFillBlankTemplate,
  extractAnswersFromEdited,
  isFillBlankCodeComplete,
} from '../utils/assembleFillBlankCode'
import {
  CODE_EXERCISE_TYPES,
  DEFAULT_FEEDBACK,
  FILL_EXERCISE_TYPES,
  type CourseSummary,
  type Exercise,
  type Lesson,
  type LessonLoadError,
  type LessonSummary,
  type ProviderStatus,
  type ProvidersOverview,
  type TestResult,
} from './types'
import {
  PRACTICE_ACTIVITIES,
  coursePath,
  exercisePath,
  learnPath,
  lessonPath,
  practicePath,
  unitPath,
  viewFromPathname,
  type AppView,
} from './routes'

export type { Exercise, Lesson, LessonSummary, TestResult }
export type { ProvidersOverview, ProviderStatus, CourseSummary }

export function useLearningSession() {
  // ─── Navigation state lives in the URL ─────────────────────────────────────
  // There is deliberately no `activeTab`, no `isLessonActive` and no stored
  // "previous screen" below. Every one of those is read from the location, so
  // the router is the only writer and a screen can never disagree with the bar.
  const navigate = useNavigate()
  const location = useLocation()
  const params = useParams<{
    courseId?: string
    unitId?: string
    lessonId?: string
    exerciseId?: string
    activity?: string
  }>()

  /** Lesson asked for by the route, whether or not its data has arrived yet. */
  const routeLessonId = params.lessonId ?? null
  /**
   * Step pinned by the route. Empty unless the learner is deep in a lesson
   * session; `/lesson/:id` on its own means "whatever the backend says is next",
   * which keeps the derived-progression rule intact for a normal lesson open.
   */
  const pinnedExerciseId = params.exerciseId ?? null

  // The sidebar's seven tabs are now seven routes. `view` exists only so the
  // chrome and the data-fetch effects can ask "am I on the leaderboard?" the
  // same way they used to; it is derived, never stored.
  const view = useMemo(() => viewFromPathname(location.pathname), [location.pathname])

  const [isGuidebookOpen, setIsGuidebookOpen] = useState(false)
  const [courses, setCourses] = useState<CourseSummary[]>([])
  // Course selection is a *preference* (`/learn` has no course in the URL), so
  // it survives in localStorage. It is not a second navigation system: the URL
  // decides which course is open, and this only remembers it for the bare
  // `/learn` entry point and for cold starts.
  const [selectedLanguage, setSelectedLanguage] = useState<string>(() => {
    return safeGetItem('patchwork_active_language') || 'python'
  })
  const [lessons, setLessons] = useState<LessonSummary[]>([])
  const [lesson, setLesson] = useState<Lesson | null>(null)
  /** Why the route's lesson could not be shown, if it could not. */
  const [lessonError, setLessonError] = useState<LessonLoadError>(null)
  // Kept so the lesson loader can read the course map for its offline fallback
  // without depending on `lessons` and re-opening the lesson whenever the map
  // refreshes (which happens after every graded step).
  const lessonsRef = useRef<LessonSummary[]>([])
  useEffect(() => {
    lessonsRef.current = lessons
  }, [lessons])
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
  //
  // The route may pin a step (see `pinnedExerciseId`), which is the one case
  // where a step is chosen without asking the backend. That is read-only by
  // construction: the pin can only name a step this learner has already been
  // served, so XP and completion still come from the server. `derivedExercise`
  // stays the authority for "is this lesson finished", and a pin that points at
  // nothing the learner has reached is normalised away below.
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

  const derivedExerciseIndex = useMemo(() => {
    const reviewIndex = allExercises.findIndex((ex) => dueReviewIds.has(ex.id))
    if (reviewIndex >= 0) return reviewIndex
    return allExercises.findIndex((ex) => !completedExerciseIds.has(ex.id))
  }, [allExercises, completedExerciseIds, dueReviewIds])
  const derivedExercise =
    derivedExerciseIndex >= 0 ? allExercises[derivedExerciseIndex] : null

  // What the URL asked for, if it names a step this lesson actually has.
  const pinnedExerciseIndex = pinnedExerciseId
    ? allExercises.findIndex((ex) => ex.id === pinnedExerciseId)
    : -1
  const pinnedExercise = pinnedExerciseIndex >= 0 ? allExercises[pinnedExerciseIndex] : null

  // A step is addressable once the learner has been served it — i.e. it is the
  // derived current step, or it is already completed (Browser Back lands here).
  // Anything further ahead is treated as a stale/hand-edited URL and normalised
  // away below rather than handed out as a free preview of later work.
  const pinIsReachable =
    pinnedExercise !== null &&
    (pinnedExercise.id === derivedExercise?.id || completedExerciseIds.has(pinnedExercise.id))

  // Once the lesson is finished there is no step to pin: the completion
  // celebration is the screen, and it lives on the bare lesson route.
  const lessonHasExercises = allExercises.length > 0
  const allExercisesDone = lessonHasExercises && derivedExercise === null

  const currentExercise = allExercisesDone ? null : pinIsReachable ? pinnedExercise : derivedExercise
  const currentExerciseIndex = currentExercise
    ? allExercises.findIndex((ex) => ex.id === currentExercise.id)
    : -1
  /** Reviewing a step that is already graded: read-only, no re-award. */
  const isReviewingCompletedStep =
    currentExercise !== null && !allExercisesDone && currentExercise.id !== derivedExercise?.id

  // Lesson complete = lesson has exercises AND every one of them is completed.
  const lessonComplete = allExercisesDone

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
  }, [refreshMistakes, lesson?.id, view])

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
    if (view === 'leaderboards') {
      fetchLeaderboard()
    }
  }, [view, xp, fetchLeaderboard])

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

  // Accepts the language explicitly because a course switch reads it before the
  // `selectedLanguage` state has committed.
  const fetchProgression = useCallback(async (lang?: string) => {
    try {
      const res = await fetch(`/api/progression?language=${encodeURIComponent(lang || selectedLanguage)}`)
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

  // ─── Course selection: the URL picks it, this loads it ──────────────────────
  // `/course/:courseId` carries a CourseSummary id (`python-foundations`), while
  // every API call takes the language (`python`). `courses` maps one to the
  // other. A bare `/learn` has no course in the URL and resolves to the stored
  // preference, so the two identifiers stay distinct without a second router.
  const routeCourseId = params.courseId ?? null

  const openCourse = useMemo(() => {
    if (!routeCourseId) return null
    // Also accept the language, so `/course/python` and `/course/ml-math` are
    // shareable shorthand for the same track rather than a dead link.
    return courses.find((c) => c.id === routeCourseId || c.language === routeCourseId) ?? null
  }, [routeCourseId, courses])

  /** The course the learner is actually looking at, from route or preference. */
  const activeCourse = useMemo(
    () =>
      openCourse ??
      courses.find((c) => c.language === selectedLanguage || c.id === selectedLanguage) ??
      null,
    [openCourse, courses, selectedLanguage],
  )

  /** Unknown only once `/api/courses` has answered; before that we are loading. */
  const courseIsUnknown = routeCourseId !== null && openCourse === null && courses.length > 0

  /**
   * The named course has not been applied yet, so `lessons` still holds the
   * previous track for a tick. Screens draw nothing rather than flashing the
   * wrong course's map under a URL that says otherwise.
   */
  const courseIsSwitching =
    openCourse !== null &&
    openCourse.language !== selectedLanguage &&
    routeLessonId === null

  const applyCourseLanguage = useCallback(
    async (lang: string) => {
      setSelectedLanguage(lang)
      safeSetItem('patchwork_active_language', lang)
      setCelebration(null)
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
      fetchProgression(lang)
    },
    [fetchLessons, fetchProgression],
  )

  useEffect(() => {
    if (!openCourse || openCourse.language === selectedLanguage) return
    void applyCourseLanguage(openCourse.language)
  }, [openCourse, selectedLanguage, applyCourseLanguage])

  // ─── Select Language Course Track ───────────────────────────────────────────
  // Selecting a track is navigation now, so this only changes the URL. The
  // effect above notices the new course and loads it, which is the one direction
  // this data flows.
  const handleCourseChange = (courseIdOrLanguage: string) => {
    const course =
      courses.find((c) => c.id === courseIdOrLanguage || c.language === courseIdOrLanguage) ??
      null
    navigate(coursePath(course?.id ?? courseIdOrLanguage))
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

  // ─── Load the lesson named by the route ─────────────────────────────────────
  // Nothing else writes `lesson`: every click path navigates and this follows.
  //
  // A missing lesson and an unreachable backend used to land in the same branch,
  // and that branch invented a placeholder lesson with an empty editor — which
  // is why `/lesson/does-not-exist` looked like a real, if dull, lesson. They are
  // reported apart now: `not_found` is the route's fault, while `network` keeps
  // the old "work offline against a dead server" fallback.
  const loadLesson = useCallback(async (lessonId: string) => {
    setIsLoadingLesson(true)
    setLessonError(null)
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
        fetch(`/api/lessons/${encodeURIComponent(lessonId)}`),
        api.lessonProgress(lessonId),
      ])
      if (res.status === 404) {
        setLesson(null)
        setLessonError('not_found')
        return
      }
      if (!res.ok) throw new Error('Lesson fetch failed')
      const data: Lesson = await res.json()
      setLesson(data)
      if (prog) setLessonProgress(prog)

      const starter = data.starter_code || ''
      const savedDraft = readCodeDraft(codeDraftKey(data.id), starter)
      setCode(savedDraft !== null ? savedDraft : starter)
      saveGameState({ currentLessonId: data.id })
    } catch {
      // The server is unreachable. Keep the learner working against the last
      // known shape of the lesson rather than failing the screen.
      const summary = lessonsRef.current.find((l) => l.id === lessonId)
      setLesson({
        id: lessonId,
        title: summary?.title ?? 'Practice programming concepts.',
        description: 'Practice programming concepts.',
        order: summary?.order ?? 1,
        difficulty: summary?.difficulty ?? 'beginner',
        duration_minutes: summary?.duration_minutes ?? 5,
        starter_code: '# Write your solution here\n',
      })
      setCode('# Write your solution here\n')
      setLessonError('network')
      saveGameState({ currentLessonId: lessonId })
    } finally {
      setIsLoadingLesson(false)
    }
  }, [])

  // The route is the only thing that opens a lesson, so a refresh or a pasted
  // URL rebuilds the session with no help from React state. `lesson` survives
  // navigating away — the map uses it to mark which node was last open — but the
  // workspace is gated on it matching the route.
  useEffect(() => {
    if (!routeLessonId) return
    if (lesson?.id === routeLessonId && !lessonError) return
    void loadLesson(routeLessonId)
  }, [routeLessonId, lesson, lessonError, loadLesson])

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

        // A graded step is where the learner actually moves on — a correct answer
        // shows the next step straight away, so this, not a CONTINUE tap, is the
        // navigation event. One deliberate push per step, in one direction only:
        // the URL follows the step, and the step never reads the URL to decide
        // whether it is finished (the server's progress does that).
        const clearedNow = new Set([...completedExerciseIds, ex.id])
        const owedNext =
          allExercises.find((e) => dueReviewIds.has(e.id) && !clearedNow.has(e.id)) ??
          allExercises.find((e) => !clearedNow.has(e.id)) ??
          null
        if (owedNext) {
          navigate(exercisePath(lesson.id, owedNext.id))
        } else {
          // Nothing owed: the lesson is over. The celebration belongs to the
          // lesson route, and it replaces — finishing is not a place you go back
          // into, so Back from it leaves the lesson.
          navigate(lessonPath(lesson.id), { replace: true })
        }
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
  // points at the next exercise automatically. We clear ephemeral state and let
  // the URL follow the step the learner lands on.
  const continueToNextExercise = () => {
    const wasLessonComplete = lessonComplete
    const earnedXp = exerciseFeedback?.xpAwarded ?? 0
    const nextStep = derivedExercise
    setExerciseInput((prev: any) => {
      if (!currentExercise) return prev
      const next = { ...prev }
      delete next[currentExercise.id]
      return next
    })
    setExercisePhase('answering')
    setExerciseFeedback(null)

    if (!lesson) return

    if (!wasLessonComplete && nextStep && nextStep.id !== pinnedExerciseId) {
      // Continue from a step the learner went back to: forward to where they
      // actually stand. The grade-time navigation above covers the ordinary
      // advance, so this only runs for a deliberate Continue.
      navigate(exercisePath(lesson.id, nextStep.id))
      return
    }

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
      // No navigation here: the URL already came back to /lesson/:id when the
      // last step was graded, and the celebration is that screen.
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
  // A new lesson is a new screen, so it pushes: Back from the next lesson comes
  // home to the one the learner just finished, which is what they expect after
  // tapping "Next Lesson".
  const goToNextLesson = () => {
    const nextId = celebration?.nextLessonId
    setCelebration(null)
    if (nextId) {
      navigate(lessonPath(nextId))
      return
    }
    // Nothing follows this lesson: go back up to the map.
    goUpstream()
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

  // "Focused lesson mode" is now simply: the URL names a lesson and its data has
  // arrived. Nothing stores it, so the workspace and the bar cannot disagree.
  const lessonIsOpen = routeLessonId !== null && lesson !== null && lesson.id === routeLessonId
  const isLessonActive = routeLessonId !== null

  // Every lesson — with or without exercises — opens the fullscreen workspace.
  const isExerciseWorkspace = lessonIsOpen

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

  // ─── Going back ────────────────────────────────────────────────────────────
  // The in-app Back button and the browser's must do the same thing, so the
  // button drives the router rather than replaying the old set-state sequence.
  // `location.key === 'default'` means the app owns no earlier entry — the
  // learner opened this URL directly in a fresh tab — and stepping back there
  // would leave Patchwork, so those cases fall through to the route above.
  const appOwnsHistory = location.key !== 'default'

  /**
   * Where the current route sits under. Computed from the URL and the lesson's
   * own `unit_id`, which is the backend's course structure rather than a
   * parallel one — and the reason no "previous screen" state is kept anywhere.
   */
  const upstreamPath = useMemo(() => {
    const courseId = activeCourse?.id
    const unitId = lesson?.unit_id
    if (courseId && unitId) return unitPath(courseId, unitId)
    if (courseId) return coursePath(courseId)
    return learnPath()
  }, [activeCourse, lesson])

  const goBack = useCallback(() => {
    if (appOwnsHistory) {
      navigate(-1)
      return
    }
    navigate(upstreamPath, { replace: true })
  }, [appOwnsHistory, navigate, upstreamPath])

  /** Explicit "leave to the map", used once a lesson is finished. */
  const goUpstream = useCallback(() => {
    navigate(upstreamPath)
  }, [navigate, upstreamPath])

  const handleExerciseBack = goBack

  // A step URL that does not describe a step this learner has been served — a
  // hand-edited address, or a step that has since been re-queued — is corrected
  // in place. `replace` so the bad URL never becomes a history entry, and the
  // derived progression stays the authority for what is actually next.
  useEffect(() => {
    if (!pinnedExerciseId || !lesson) return
    const lessonHasNoSteps = (lesson.sublessons ?? []).length === 0
    if (!pinIsReachable || lessonHasNoSteps) navigate(lessonPath(lesson.id), { replace: true })
  }, [pinnedExerciseId, pinIsReachable, lesson, navigate])

  // ─── Opening a lesson from a screen ─────────────────────────────────────────
  // Course-map nodes, practice cards and the review queue all funnel through
  // here, and it is only a URL change: the loader effect above does the work.
  const openLesson = (lessonId: string) => navigate(lessonPath(lessonId))

  const openUnit = (courseId: string, unitId: string) => navigate(unitPath(courseId, unitId))

  // ─── Practice hub ──────────────────────────────────────────────────────────
  // Which practice card is open is "where the learner is", so the route carries
  // it (/practice/:activity) and the hub is driven from here. An absent segment
  // falls back to the hub's own default, which keeps plain `/practice`
  // behaving exactly as it always did.
  const practiceActivity = params.activity ?? null
  const practiceActivityIsValid =
    practiceActivity === null ||
    (PRACTICE_ACTIVITIES as readonly string[]).includes(practiceActivity)
  // Re-picking the card that is already open must not push a duplicate history
  // entry: PracticeHub also calls this when a lesson chip inside the card is
  // chosen, and that is a selection within the screen rather than a new screen.
  const selectPracticeActivity = (activity: string) => {
    if (activity === practiceActivity) return
    navigate(practicePath(activity))
  }
  // Everything the screens need. Exposed as one object so a screen can
  // destructure the same names the old App JSX used, and the returned
  // component trees stay byte-identical to what they replaced.
  return {
    activeCourse,
    addNote,
    aiEnabled,
    allExercises,
    allExercisesDone,
    allPassed,
    answerArmed,
    appOwnsHistory,
    applyCourseLanguage,
    applyHearts,
    askSolution,
    askTutor,
    backendError,
    celebration,
    charSpeech,
    charState,
    charSubTab,
    code,
    codingFeedbackActive,
    completedCount,
    completedExerciseCount,
    completedExerciseIds,
    completedMaterialIds,
    consecutiveCorrect,
    continueToNextExercise,
    courseIsUnknown,
    coursePathTitle,
    courses,
    currentExercise,
    currentExerciseIndex,
    currentExerciseIsCode,
    currentExerciseIsFill,
    currentProviderStatus,
    customTitle,
    dailyProgress,
    derivedExercise,
    derivedExerciseIndex,
    dueReviewIds,
    editorRef,
    exerciseFeedback,
    exerciseInput,
    exercisePhase,
    exercisePosition,
    exerciseTotal,
    failedRequired,
    feedback,
    fetchCourses,
    fetchLeaderboard,
    fetchLessonProgress,
    fetchLessons,
    fetchProgression,
    fetchProviders,
    fetchUserProfile,
    gamification,
    getRunnableCode,
    goBack,
    goToNextLesson,
    goUpstream,
    handleCompleteMaterial,
    handleCourseChange,
    handleEditorKeyDown,
    handleExerciseBack,
    handleGenerateCourse,
    handleProviderSelection,
    handleRunTestOut,
    hearts,
    hintDisabled,
    hintLevel,
    isAiAvailable,
    isCodingType,
    isExerciseWorkspace,
    isGeneratingCourse,
    isGuidebookOpen,
    isLessonActive,
    isLoadingLesson,
    isReviewingCompletedStep,
    isRunning,
    isTutorLoading,
    lastCompletedCodingExercise,
    leaderboardEntries,
    lesson,
    lessonComplete,
    lessonError,
    lessonHasExercises,
    lessonIsOpen,
    lessonProgress,
    lessonWorkspaceExercise,
    lessons,
    lessonsRef,
    level,
    loadLesson,
    location,
    materialInput,
    materialType,
    materials,
    maxHearts,
    mistakes,
    navigate,
    noteInput,
    openCourse,
    openLesson,
    openUnit,
    params,
    pinIsReachable,
    pinnedExercise,
    pinnedExerciseId,
    pinnedExerciseIndex,
    practiceActivity,
    practiceActivityIsValid,
    previousHints,
    profileStreak,
    progressPct,
    providersOverview,
    refreshMistakes,
    restoreAnsweredBuffer,
    restoreSnapshot,
    results,
    resultsRef,
    retryCurrentExercise,
    routeCourseId,
    routeLessonId,
    runTests,
    safeLessons,
    secondsToNextHeart,
    selectPracticeActivity,
    selectedLanguage,
    selectedProvider,
    sessionNotes,
    setAiEnabled,
    setAnswerArmed,
    setBackendError,
    setCelebration,
    setCharSpeech,
    setCharState,
    setCharSubTab,
    setCode,
    setCompletedMaterialIds,
    setConsecutiveCorrect,
    setCourses,
    setCustomTitle,
    setExerciseFeedback,
    setExerciseInput,
    setExercisePhase,
    setFeedback,
    setGamification,
    setHearts,
    setHintLevel,
    setIsGeneratingCourse,
    setIsGuidebookOpen,
    setIsLoadingLesson,
    setIsRunning,
    setIsTutorLoading,
    setLeaderboardEntries,
    setLesson,
    setLessonError,
    setLessonProgress,
    setLessons,
    setLevel,
    setMaterialInput,
    setMaterialType,
    setMaterials,
    setMaxHearts,
    setMistakes,
    setNoteInput,
    setPreviousHints,
    setProvidersOverview,
    setRestoreSnapshot,
    setResults,
    setSecondsToNextHeart,
    setSelectedLanguage,
    setSelectedProvider,
    setSessionNotes,
    setShowCreateModal,
    setShowOutofHeartsModal,
    setShowSettings,
    setShowTestOutModal,
    setSoundEnabled,
    setTestOutResult,
    setTestOutSubmissions,
    setTutorLevel,
    setTutorSource,
    setUnlimitedHearts,
    setUserProfile,
    setXp,
    setXpGainPopup,
    showCreateModal,
    showLessonRunCode,
    showOutofHeartsModal,
    showSettings,
    showTestOutModal,
    soundEnabled,
    submitSubLessonExercise,
    testOutResult,
    testOutSubmissions,
    toggleSound,
    triggerXpGain,
    tutorLevel,
    tutorSource,
    unlimitedHearts,
    upstreamPath,
    userProfile,
    view,
    visitMistakesRef,
    workspaceExercise,
    xp,
    xpGainPopup,
  }

  // The session surface. One object so each screen can destructure the same
  // names the old App JSX closed over, which keeps the moved markup identical
  // to what it replaced.
  return {
    activeCourse,
    addNote,
    aiEnabled,
    allExercises,
    allExercisesDone,
    allPassed,
    answerArmed,
    appOwnsHistory,
    applyCourseLanguage,
    applyHearts,
    askSolution,
    askTutor,
    backendError,
    celebration,
    charSpeech,
    charState,
    charSubTab,
    code,
    codingFeedbackActive,
    completedCount,
    completedExerciseCount,
    completedExerciseIds,
    completedMaterialIds,
    consecutiveCorrect,
    continueToNextExercise,
    courseIsUnknown,
    coursePathTitle,
    courses,
    currentExercise,
    currentExerciseIndex,
    currentExerciseIsCode,
    currentExerciseIsFill,
    currentProviderStatus,
    customTitle,
    dailyProgress,
    derivedExercise,
    derivedExerciseIndex,
    dueReviewIds,
    editorRef,
    exerciseFeedback,
    exerciseInput,
    exercisePhase,
    exercisePosition,
    exerciseTotal,
    failedRequired,
    feedback,
    fetchCourses,
    fetchLeaderboard,
    fetchLessonProgress,
    fetchLessons,
    fetchProgression,
    fetchProviders,
    fetchUserProfile,
    gamification,
    getRunnableCode,
    goBack,
    goToNextLesson,
    goUpstream,
    handleCompleteMaterial,
    handleCourseChange,
    handleEditorKeyDown,
    handleExerciseBack,
    handleGenerateCourse,
    handleProviderSelection,
    handleRunTestOut,
    hearts,
    hintDisabled,
    hintLevel,
    isAiAvailable,
    isCodingType,
    isExerciseWorkspace,
    isGeneratingCourse,
    isGuidebookOpen,
    isLessonActive,
    isLoadingLesson,
    isReviewingCompletedStep,
    isRunning,
    isTutorLoading,
    lastCompletedCodingExercise,
    leaderboardEntries,
    lesson,
    lessonComplete,
    lessonError,
    lessonHasExercises,
    lessonIsOpen,
    lessonProgress,
    lessonWorkspaceExercise,
    lessons,
    lessonsRef,
    level,
    loadLesson,
    location,
    materialInput,
    materialType,
    materials,
    maxHearts,
    mistakes,
    navigate,
    noteInput,
    openCourse,
    openLesson,
    openUnit,
    params,
    pinIsReachable,
    pinnedExercise,
    pinnedExerciseId,
    pinnedExerciseIndex,
    practiceActivity,
    practiceActivityIsValid,
    previousHints,
    profileStreak,
    progressPct,
    providersOverview,
    refreshMistakes,
    restoreAnsweredBuffer,
    restoreSnapshot,
    results,
    resultsRef,
    retryCurrentExercise,
    routeCourseId,
    routeLessonId,
    runTests,
    safeLessons,
    secondsToNextHeart,
    selectPracticeActivity,
    selectedLanguage,
    selectedProvider,
    sessionNotes,
    setAiEnabled,
    setAnswerArmed,
    setBackendError,
    setCelebration,
    setCharSpeech,
    setCharState,
    setCharSubTab,
    setCode,
    setCompletedMaterialIds,
    setConsecutiveCorrect,
    setCourses,
    setCustomTitle,
    setExerciseFeedback,
    setExerciseInput,
    setExercisePhase,
    setFeedback,
    setGamification,
    setHearts,
    setHintLevel,
    setIsGeneratingCourse,
    setIsGuidebookOpen,
    setIsLoadingLesson,
    setIsRunning,
    setIsTutorLoading,
    setLeaderboardEntries,
    setLesson,
    setLessonError,
    setLessonProgress,
    setLessons,
    setLevel,
    setMaterialInput,
    setMaterialType,
    setMaterials,
    setMaxHearts,
    setMistakes,
    setNoteInput,
    setPreviousHints,
    setProvidersOverview,
    setRestoreSnapshot,
    setResults,
    setSecondsToNextHeart,
    setSelectedLanguage,
    setSelectedProvider,
    setSessionNotes,
    setShowCreateModal,
    setShowOutofHeartsModal,
    setShowSettings,
    setShowTestOutModal,
    setSoundEnabled,
    setTestOutResult,
    setTestOutSubmissions,
    setTutorLevel,
    setTutorSource,
    setUnlimitedHearts,
    setUserProfile,
    setXp,
    setXpGainPopup,
    showCreateModal,
    showLessonRunCode,
    showOutofHeartsModal,
    showSettings,
    showTestOutModal,
    soundEnabled,
    submitSubLessonExercise,
    testOutResult,
    testOutSubmissions,
    toggleSound,
    triggerXpGain,
    tutorLevel,
    tutorSource,
    unlimitedHearts,
    upstreamPath,
    userProfile,
    view,
    visitMistakesRef,
    workspaceExercise,
    xp,
    xpGainPopup,
  }
  // The session surface. One object so each screen can destructure the same
  // names the old App JSX closed over, which keeps the moved markup identical
  // to what it replaced.
  return {
    activeCourse,
    addNote,
    aiEnabled,
    allExercises,
    allExercisesDone,
    allPassed,
    answerArmed,
    appOwnsHistory,
    applyCourseLanguage,
    applyHearts,
    askSolution,
    askTutor,
    backendError,
    celebration,
    charSpeech,
    charState,
    charSubTab,
    code,
    codingFeedbackActive,
    completedCount,
    completedExerciseCount,
    completedExerciseIds,
    completedMaterialIds,
    consecutiveCorrect,
    continueToNextExercise,
    courseIsSwitching,
    courseIsUnknown,
    coursePathTitle,
    courses,
    currentExercise,
    currentExerciseIndex,
    currentExerciseIsCode,
    currentExerciseIsFill,
    currentProviderStatus,
    customTitle,
    dailyProgress,
    derivedExercise,
    derivedExerciseIndex,
    dueReviewIds,
    editorRef,
    exerciseFeedback,
    exerciseInput,
    exercisePhase,
    exercisePosition,
    exerciseTotal,
    failedRequired,
    feedback,
    fetchCourses,
    fetchLeaderboard,
    fetchLessonProgress,
    fetchLessons,
    fetchProgression,
    fetchProviders,
    fetchUserProfile,
    gamification,
    getRunnableCode,
    goBack,
    goToNextLesson,
    goUpstream,
    handleCompleteMaterial,
    handleCourseChange,
    handleEditorKeyDown,
    handleExerciseBack,
    handleGenerateCourse,
    handleProviderSelection,
    handleRunTestOut,
    hearts,
    hintDisabled,
    hintLevel,
    isAiAvailable,
    isCodingType,
    isExerciseWorkspace,
    isGeneratingCourse,
    isGuidebookOpen,
    isLessonActive,
    isLoadingLesson,
    isReviewingCompletedStep,
    isRunning,
    isTutorLoading,
    lastCompletedCodingExercise,
    leaderboardEntries,
    lesson,
    lessonComplete,
    lessonError,
    lessonHasExercises,
    lessonIsOpen,
    lessonProgress,
    lessonWorkspaceExercise,
    lessons,
    lessonsRef,
    level,
    loadLesson,
    location,
    materialInput,
    materialType,
    materials,
    maxHearts,
    mistakes,
    navigate,
    noteInput,
    openCourse,
    openLesson,
    openUnit,
    params,
    pinIsReachable,
    pinnedExercise,
    pinnedExerciseId,
    pinnedExerciseIndex,
    practiceActivity,
    practiceActivityIsValid,
    previousHints,
    profileStreak,
    progressPct,
    providersOverview,
    refreshMistakes,
    restoreAnsweredBuffer,
    restoreSnapshot,
    results,
    resultsRef,
    retryCurrentExercise,
    routeCourseId,
    routeLessonId,
    runTests,
    safeLessons,
    secondsToNextHeart,
    selectPracticeActivity,
    selectedLanguage,
    selectedProvider,
    sessionNotes,
    setAiEnabled,
    setAnswerArmed,
    setBackendError,
    setCelebration,
    setCharSpeech,
    setCharState,
    setCharSubTab,
    setCode,
    setCompletedMaterialIds,
    setConsecutiveCorrect,
    setCourses,
    setCustomTitle,
    setExerciseFeedback,
    setExerciseInput,
    setExercisePhase,
    setFeedback,
    setGamification,
    setHearts,
    setHintLevel,
    setIsGeneratingCourse,
    setIsGuidebookOpen,
    setIsLoadingLesson,
    setIsRunning,
    setIsTutorLoading,
    setLeaderboardEntries,
    setLesson,
    setLessonError,
    setLessonProgress,
    setLessons,
    setLevel,
    setMaterialInput,
    setMaterialType,
    setMaterials,
    setMaxHearts,
    setMistakes,
    setNoteInput,
    setPreviousHints,
    setProvidersOverview,
    setRestoreSnapshot,
    setResults,
    setSecondsToNextHeart,
    setSelectedLanguage,
    setSelectedProvider,
    setSessionNotes,
    setShowCreateModal,
    setShowOutofHeartsModal,
    setShowSettings,
    setShowTestOutModal,
    setSoundEnabled,
    setTestOutResult,
    setTestOutSubmissions,
    setTutorLevel,
    setTutorSource,
    setUnlimitedHearts,
    setUserProfile,
    setXp,
    setXpGainPopup,
    showCreateModal,
    showLessonRunCode,
    showOutofHeartsModal,
    showSettings,
    showTestOutModal,
    soundEnabled,
    submitSubLessonExercise,
    testOutResult,
    testOutSubmissions,
    toggleSound,
    triggerXpGain,
    tutorLevel,
    tutorSource,
    unlimitedHearts,
    upstreamPath,
    userProfile,
    view,
    visitMistakesRef,
    workspaceExercise,
    xp,
    xpGainPopup,
  }
}
