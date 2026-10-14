import { useEffect, useRef, useState } from 'react'
import { playPatchworkSound } from '../utils/audio'
import { displayAnswer, FeedbackSheet } from './FeedbackSheet'
import { enqueueMiss, gradeExercise, hasDraft } from './grade'
import { HeartPractice } from './HeartPractice'
import { resolveHint } from './hints'
import { LessonComplete } from './LessonComplete'
import { LessonShell } from './LessonShell'
import { awardXp, earnHeart, loadProgress, loseHeart, markLessonComplete, usePlayerProgress } from './progressStore'
import { gradeOnServer } from './serverGrade'
import { HintText } from './rich'
import { runWriteExercise } from './runSnippet'
import {
  FillBlank,
  MultipleChoice,
  PredictOutput,
  SpotTheBug,
  TapToBuild,
  TeachCard,
  WriteCode,
} from './screens'
import type { Exercise, PlayerLesson, RunView } from './types'
import './lessonPlayer.css'

export function LessonPlayer({
  lesson,
  soundEnabled,
  onToggleSound,
  onQuit,
  onOpenGuidebook,
}: {
  lesson: PlayerLesson
  soundEnabled: boolean
  onToggleSound: () => void
  onQuit: () => void
  onOpenGuidebook?: () => void
}) {
  const stats = usePlayerProgress()
  const [queue, setQueue] = useState<Exercise[]>(lesson.screens)
  const [index, setIndex] = useState(0)
  const [draft, setDraft] = useState<string | string[] | null>(null)
  const [code, setCode] = useState('')
  const [run, setRun] = useState<RunView | null>(null)
  const [phase, setPhase] = useState<'answer' | 'feedback'>('answer')
  const [feedback, setFeedback] = useState<{
    correct: boolean
    xp: number
    message: string
    detail?: string
    answerLine?: string
  } | null>(null)
  const [hintLevel, setHintLevel] = useState(0)
  const [hintText, setHintText] = useState('')
  const [hintBusy, setHintBusy] = useState(false)
  const [assisted, setAssisted] = useState<string[]>([])
  const [requeued, setRequeued] = useState<string[]>([])
  const [missed, setMissed] = useState<string[]>([])
  const [correctFirst, setCorrectFirst] = useState(0)
  const [graded, setGraded] = useState(0)
  const [earnedXp, setEarnedXp] = useState(0)
  const [done, setDone] = useState(false)
  const [practice, setPractice] = useState(false)
  const [running, setRunning] = useState(false)
  const started = useRef(Date.now())
  const finished = useRef<{ xp: number; accuracy: number; perfect: boolean; seconds: number } | null>(null)

  const screen = queue[index]

  useEffect(() => {
    const next = queue[index]
    if (!next) return
    setPhase('answer')
    setFeedback(null)
    setHintLevel(0)
    setHintText('')
    setRun(null)
    if (next.type === 'write_code') {
      const starter = next.starter ?? ''
      setCode(starter)
      setDraft(starter)
    } else if (next.type === 'tap_to_build') {
      setDraft([])
    } else {
      setDraft(null)
    }
  }, [index])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      const typing = target && (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT')
      if (typing) return
      if (practice || done) {
        if (event.key === 'Enter') {
          const button = document.querySelector<HTMLButtonElement>('.lp-complete .lp-btn, .lp-practice .lp-btn-primary:not(:disabled)')
          button?.click()
        }
        return
      }
      if (event.key === 'Enter') {
        event.preventDefault()
        if (phase === 'feedback') {
          document.querySelector<HTMLButtonElement>('.lp-btn-sheet')?.click()
        } else {
          document.querySelector<HTMLButtonElement>('.lp-check')?.click()
        }
      }
      if (phase === 'answer' && screen?.options && ['1', '2', '3', '4'].includes(event.key)) {
        const option = screen.options[Number(event.key) - 1]
        if (option) setDraft(option)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [phase, practice, done, screen])

  if (!screen && !done) return null

  function goNext() {
    if (index + 1 >= queue.length) {
      finish()
      return
    }
    setIndex((value) => value + 1)
  }

  function finish() {
    const perfect = missed.length === 0 && assisted.length === 0 && graded > 0 && correctFirst === graded
    const bonus = perfect ? 5 : 0
    if (bonus) awardXp(bonus)
    const totalXp = earnedXp + bonus
    markLessonComplete(lesson.id, 5)
    const accuracy = graded === 0 ? 100 : Math.round((correctFirst / graded) * 100)
    finished.current = {
      xp: totalXp,
      accuracy,
      perfect,
      seconds: Math.max(1, Math.round((Date.now() - started.current) / 1000)),
    }
    playPatchworkSound('lesson_complete', soundEnabled)
    setDone(true)
  }

  async function runNow() {
    if (!screen || screen.type !== 'write_code' || running) return
    setRunning(true)
    const view = await runWriteExercise(screen, code)
    setRun(view)
    setRunning(false)
    return view
  }

  async function onCheck() {
    if (!screen || phase === 'feedback') return
    if (screen.type === 'teach') {
      goNext()
      return
    }
    if (!hasDraft(screen, screen.type === 'write_code' ? code : draft)) return

    let correct = false
    let detail = screen.explanation
    let answerLine: string | undefined
    if (screen.type === 'write_code') {
      const view = run ?? (await runNow())
      correct = Boolean(view && view.tests.length > 0 && view.tests.every((test) => test.passed) && !view.errorSummary)
      if (!correct && view?.errorSummary) detail = view.errorSummary
    } else if (screen.server) {
      const graded = await gradeOnServer(screen, draft, code)
      correct = graded.passed
      detail = graded.explanation
      answerLine = graded.answerLine
    } else {
      correct = gradeExercise(screen, draft)
    }

    setGraded((count) => count + 1)
    if (correct) {
      const helped = assisted.includes(screen.id)
      const xp = helped ? 0 : screen.xp
      if (!missed.includes(screen.id)) setCorrectFirst((count) => count + 1)
      if (xp) {
        awardXp(xp)
        setEarnedXp((value) => value + xp)
      }
      playPatchworkSound('correct_chime', soundEnabled)
      if (xp) playPatchworkSound('xp_gain', soundEnabled)
      setFeedback({ correct: true, xp, message: `Nice! ${detail}`, detail })
    } else {
      const offline = /offline/i.test(detail)
      if (!offline) {
        const next = loseHeart()
        setMissed((ids) => (ids.includes(screen.id) ? ids : [...ids, screen.id]))
        const queued = enqueueMiss(queue, screen, requeued)
        setQueue(queued.queue)
        setRequeued(queued.requeued)
        if (next.hearts <= 0) setPractice(false)
      }
      playPatchworkSound('error', soundEnabled)
      setFeedback({ correct: false, xp: 0, message: '', detail, answerLine })
    }
    setPhase('feedback')
  }

  function onContinue() {
    if (feedback && !feedback.correct && loadProgress().hearts <= 0) {
      setPractice(true)
      setPhase('answer')
      return
    }
    goNext()
  }

  async function onHint() {
    if (!screen || hintBusy || hintLevel >= 3) return
    const nextLevel = hintLevel + 1
    setHintBusy(true)
    const text = await resolveHint(screen.hints[nextLevel - 1], nextLevel, lesson, screen.prompt)
    setHintText(text)
    setHintLevel(nextLevel)
    if (nextLevel === 3) {
      setAssisted((ids) => (ids.includes(screen.id) ? ids : [...ids, screen.id]))
      loseHeart()
    }
    setHintBusy(false)
  }

  if (done && finished.current) {
    const summary = finished.current
    return (
      <div className="lp">
        <LessonComplete
          title={lesson.title}
          xp={summary.xp}
          accuracy={summary.accuracy}
          seconds={summary.seconds}
          streak={stats.streak}
          perfect={summary.perfect}
          sourceUrl={lesson.sourceUrl}
          onContinue={onQuit}
        />
      </div>
    )
  }

  if (!screen) return null

  const ready = hasDraft(screen, screen.type === 'write_code' ? code : draft)
  const primaryLabel = screen.type === 'teach' ? 'Continue' : 'Check'

  const footer =
    phase === 'feedback' && feedback ? (
      <FeedbackSheet
        correct={feedback.correct}
        xp={feedback.xp}
        message={feedback.message}
        answer={feedback.correct ? undefined : feedback.answerLine || displayAnswer(screen) || undefined}
        explanation={feedback.detail || screen.explanation}
        onContinue={onContinue}
      />
    ) : (
      <footer className="lp-footer">
        <div className="lp-hint-wrap">
          <button type="button" className="lp-btn lp-btn-secondary" onClick={onHint} disabled={hintBusy || hintLevel >= 3}>
            Hint 💡
          </button>
          {hintText ? (
            <p className="lp-hint-text">
              <HintText value={hintText} />
            </p>
          ) : null}
        </div>
        <div className="lp-footer-actions">
          {screen.type === 'write_code' ? (
            <button type="button" className="lp-btn lp-btn-secondary" onClick={() => void runNow()} disabled={!ready || running}>
              {running ? 'Running…' : 'Run'}
            </button>
          ) : null}
          <button type="button" className="lp-btn lp-btn-primary lp-check" disabled={!ready} onClick={() => void onCheck()}>
            {primaryLabel}
          </button>
        </div>
      </footer>
    )

  return (
    <LessonShell
      progress={index}
      total={queue.length}
      hearts={stats.hearts}
      streak={stats.streak}
      onQuit={onQuit}
      soundEnabled={soundEnabled}
      onToggleSound={onToggleSound}
      onOpenGuidebook={onOpenGuidebook}
      lessonId={lesson.id}
      footer={practice ? <div className="lp-footer" /> : footer}
    >
      {practice ? (
        <HeartPractice
          onDone={(earned) => {
            if (earned) earnHeart()
            setPractice(false)
            goNext()
          }}
        />
      ) : null}
      {!practice && screen.type === 'teach' ? <TeachCard exercise={screen} /> : null}
      {!practice && screen.type === 'multiple_choice' ? (
        <MultipleChoice
          exercise={screen}
          selected={screen.multi ? (Array.isArray(draft) ? draft : []) : typeof draft === 'string' ? draft : null}
          onSelect={(option) => {
            if (!screen.multi) {
              setDraft(option)
              return
            }
            const current = Array.isArray(draft) ? draft : []
            setDraft(current.includes(option) ? current.filter((item) => item !== option) : [...current, option])
          }}
        />
      ) : null}
      {!practice && screen.type === 'predict' ? (
        <PredictOutput exercise={screen} selected={typeof draft === 'string' ? draft : null} onSelect={setDraft} />
      ) : null}
      {!practice && screen.type === 'tap_to_build' ? (
        <TapToBuild exercise={screen} picked={Array.isArray(draft) ? draft : []} onChange={setDraft} />
      ) : null}
      {!practice && screen.type === 'fill_blank' ? (
        <FillBlank exercise={screen} value={typeof draft === 'string' ? draft : null} onChange={setDraft} />
      ) : null}
      {!practice && screen.type === 'spot_the_bug' ? (
        <SpotTheBug exercise={screen} selected={typeof draft === 'string' ? draft : null} onSelect={setDraft} />
      ) : null}
      {!practice && screen.type === 'write_code' ? (
        <WriteCode exercise={screen} code={code} onChange={setCode} run={run} />
      ) : null}
    </LessonShell>
  )
}
