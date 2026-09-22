/**
 * The teaching session runner: one rung per screen, one primary verb, and the
 * ladder's own reason for being on this rung at this moment.
 *
 * Two rules shape everything below. A rung asks for exactly one thing, because
 * decision time grows with the number of simultaneous options and a code exercise
 * already carries several moving parts. And failing while learning is free and
 * explained, so the message names the misconception rather than the verdict — the
 * server hands back authored per-answer feedback for precisely this.
 */

import { useMemo, useState } from 'react'
import ExerciseAnswerInput from '../components/ExerciseAnswerInput'
import { CodeEditor } from '../components/CodeEditor'
import type { LadderSession, LadderStep, StepOutcome } from '../learning/useStepSession'

/** Must match EXTRA_HINTS_PER_STEP in `learning/useStepSession.ts`. */
const AI_HINTS = 2

type RunnerProps = {
  session: LadderSession
  step: LadderStep | null
  index: number
  input: Record<string, any>
  setInput: (patch: Record<string, any>) => void
  outcome: StepOutcome | null
  clearOutcome: () => void
  busy: boolean
  hintsUsed: number
  extraHints?: string[]
  hintBusy?: boolean
  bumpHints: () => void | Promise<void>
  advance: () => void
  markSeen: () => void
  attempt: () => Promise<StepOutcome | null>
  progress: { done: number; total: number; bonus: number }
  finished: boolean
  onExit: () => void
  onNextLesson: (lessonId: string) => void
}

export function StepRunner(props: RunnerProps) {
  const { session, step, outcome, finished } = props

  if (finished || !step) {
    return <CompletionScreen session={session} outcome={outcome} onNextLesson={props.onNextLesson} onExit={props.onExit} />
  }

  return (
    <div className="lr-root" data-stage={step.stage}>
      <ProgressRail
        done={props.progress.done}
        total={props.progress.total}
        bonus={props.progress.bonus}
        stage={step.stage}
        skill={session.skill}
      />

      {step.stage === 'introduce' || step.stage === 'show' ? (
        <PresentationCard step={step} busy={props.busy} onContinue={props.markSeen} />
      ) : (
        <PracticeCard
          step={step}
          input={props.input}
          setInput={props.setInput}
          outcome={outcome}
          busy={props.busy}
          hintsUsed={props.hintsUsed}
          extraHints={props.extraHints}
          hintBusy={props.hintBusy}
          bumpHints={props.bumpHints}
          onAdvance={props.advance}
          onAttempt={props.attempt}
          onRetry={props.clearOutcome}
        />
      )}

      {/* The ladder says why it is on this rung. Explanations like these are what
          make an adaptive system reviewable rather than mysterious. */}
      <p className="lr-reason">{step.reason}</p>
    </div>
  )
}

function ProgressRail({ done, total, bonus, stage, skill }: { done: number; total: number; bonus: number; stage: string; skill: string }) {
  const dots = Array.from({ length: Math.max(total, 1) }, (_, i) => i < done)
  return (
    <div className="lr-rail">
      <div className="lr-rail-head">
        <span className="lr-skill">{humanSkill(skill)}</span>
        <span className="lr-count" aria-live="polite">
          {Math.min(done + 1, total)} / {total}
        </span>
      </div>
      <div className="lr-dots" role="img" aria-label={`${done} of ${total} steps complete`}>
        {dots.map((filled, i) => (
          <span key={i} className={`lr-dot${filled ? ' is-done' : ''}${i === done ? ' is-now' : ''}`} />
        ))}
        {bonus > 0 ? (
          <span className="lr-bonus" title="Retrieval practice added past the end">
            +{bonus} practice
          </span>
        ) : null}
      </div>
      <span className={`lr-stage lr-stage--${stage}`}>{stageLabel(stage)}</span>
    </div>
  )
}

function PresentationCard({ step, busy, onContinue }: { step: LadderStep; busy: boolean; onContinue: () => void }) {
  const content = step.content || {}
  const symbols = content.symbols || {}
  return (
    <div className="lr-card">
      <h2 className="lr-lead">{content.lead || step.title || step.question || humanStage(step.stage)}</h2>
      {step.stage === 'show' && content.given ? (
        <p className="lr-given">{content.given}</p>
      ) : null}
      {Object.keys(symbols).length > 0 ? (
        <dl className="lr-symbols">
          {Object.entries(symbols).map(([symbol, meaning]) => (
            <div className="lr-symbol" key={symbol}>
              <dt>{symbol}</dt>
              <dd>{String(meaning)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {content.formula ? <pre className="lr-formula">{content.formula}</pre> : null}
      {Array.isArray(content.lines) ? (
        <pre className="lr-lines">{content.lines.join('\n')}</pre>
      ) : null}
      {content.say ? <p className="lr-say">{content.say}</p> : null}
      {content.takeaway ? <p className="lr-takeaway">{content.takeaway}</p> : null}
      <button
        type="button"
        className="duo-button duo-button-primary lr-cta"
        onClick={onContinue}
        disabled={busy}
      >
        {step.action || 'Continue'}
      </button>
    </div>
  )
}

function PracticeCard(props: {
  step: LadderStep
  input: Record<string, any>
  setInput: (patch: Record<string, any>) => void
  outcome: StepOutcome | null
  busy: boolean
  hintsUsed: number
  extraHints?: string[]
  hintBusy?: boolean
  bumpHints: () => void | Promise<void>
  onAdvance: () => void
  onAttempt: () => Promise<StepOutcome | null>
  onRetry: () => void
}) {
  const { step, input, setInput, outcome, busy } = props
  const [showHints, setShowHints] = useState(false)
  const exercise = useMemo(
    () => ({
      id: step.id,
      type: step.widget,
      question: step.question || '',
      options: step.options || [],
      // No `blanks`: for a fill rung that array *is* the answer key, so the server
      // never sends it. The editor renders the task from `starter_code`.
      pairs: step.pairs || [],
      starter_code: step.starter_code || '',
    }),
    [step],
  )
  const isEditor = isEditorish(step)
  const answered = hasAnswer(step, input)
  const authored = step.hints ?? []
  const extra = props.extraHints ?? []
  const moreAuthoredHints = props.hintsUsed < authored.length
  const canAskAI = !moreAuthoredHints && extra.length < AI_HINTS
  const revealed = [...authored.slice(0, props.hintsUsed), ...extra]

  return (
    <div className="lr-card">
      <p className="lr-question">{step.question}</p>

      {isEditor ? (
        <CodeEditor
          value={input.code ?? step.starter_code ?? ''}
          onChange={(value) => setInput({ code: value })}
          disabled={busy || outcome?.passed === true}
          ariaLabel="Your code"
          showHeader={false}
        />
      ) : (
        <ExerciseAnswerInput
          exercise={exercise}
          exType={step.widget}
          exState={input}
          disabled={busy || outcome?.passed === true}
          setState={setInput}
        />
      )}

      {outcome ? (
        <div className={`duo-feedback-panel ${outcome.passed ? 'success' : 'error'} lr-feedback`} role="status">
          <div className="duo-feedback-title">
            <span>{outcome.passed ? stageWin(step.stage) : 'Not yet'}</span>
            {outcome.xp_awarded > 0 ? <span className="lr-xp">+{outcome.xp_awarded} XP</span> : null}
          </div>
          <p>{outcome.feedback}</p>
          {outcome.passed && outcome.explanation ? <p className="lr-why">{outcome.explanation}</p> : null}
          {!outcome.passed && !outcome.charging ? (
            <p className="lr-free-note">No heart at stake — this rung is here to teach you something.</p>
          ) : null}
        </div>
      ) : null}

      <div className="lr-actions">
        <div className="lr-hints">
            {moreAuthoredHints || canAskAI ? (
              <button
                type="button"
                className="duo-button duo-button-secondary lr-hint-btn"
                onClick={() => {
                  setShowHints(true)
                  void props.bumpHints()
                }}
                disabled={busy || props.hintBusy}
              >
                {props.hintBusy
                  ? 'Thinking…'
                  : moreAuthoredHints
                    ? `💡 Hint ${props.hintsUsed + 1} of ${authored.length}`
                    : `💡 Ask for a nudge (${extra.length + 1} of ${AI_HINTS})`}
              </button>
            ) : (
              // Both ladders ran out. The hints already asked for stay on screen,
              // or the last tap would erase its own reward and the learner would
              // be told "no more" mid-sentence.
              <span className="lr-hint-exhausted">No more hints — this one is yours.</span>
            )}
            {showHints && revealed.length > 0 ? (
              <ol className="lr-hint-list">
                {revealed.map((hint, i) => (
                  <li key={i}>{hint}</li>
                ))}
              </ol>
            ) : null}
          </div>

        {outcome?.passed ? (
          <button type="button" className="duo-button duo-button-primary lr-cta" onClick={props.onAdvance}>
            Continue →
          </button>
        ) : (
          <button
            type="button"
            className="duo-button duo-button-primary lr-cta"
            onClick={() => void props.onAttempt()}
            disabled={busy || !answered}
          >
            {busy ? 'Checking…' : step.stage === 'independent' || step.stage === 'transfer' || step.stage === 'mastery' ? 'Run the tests' : 'Check'}
          </button>
        )}
        {outcome && !outcome.passed ? (
          <button type="button" className="duo-button duo-button-secondary" onClick={props.onRetry}>
            Try again
          </button>
        ) : null}
      </div>
    </div>
  )
}

function CompletionScreen({ session, outcome, onNextLesson, onExit }: {
  session: LadderSession
  outcome: StepOutcome | null
  onNextLesson: (lessonId: string) => void
  onExit: () => void
}) {
  // The lesson's own concept, from the session the server regenerated after the
  // last attempt — not `outcome.demonstrated`, which describes the step attempted
  // and may be a retrieval hook for a concept an earlier lesson taught.
  const demonstrated = session.demonstrated
  const nextLesson = outcome?.next_lesson_id ?? null
  const earned = outcome?.xp_awarded ?? 0
  return (
    <div className="lr-card lr-card--done" role="status">
      <h2 className="lr-lead">{demonstrated ? `${humanSkill(session.skill)} — demonstrated` : `${humanSkill(session.skill)} — finished for today`}</h2>
      <p className="lr-say">{session.objective}</p>
      <ul className="lr-evidence">
        {session.evidence.length === 0 && !demonstrated ? <li>Reviewed the worked example</li> : null}
        {session.evidence.includes('independent') ? <li>✓ Wrote the function yourself</li> : null}
        {session.evidence.includes('debugged') ? <li>✓ Found the bug in someone else&apos;s code</li> : null}
        {session.evidence.includes('transferred') ? <li>✓ Used it on a problem you had not seen</li> : null}
        {session.evidence.includes('delayed_recall') ? <li>✓ Recalled it later, from memory</li> : null}
      </ul>
      {earned > 0 ? <p className="lr-xp-total">+{earned} XP</p> : null}
      {session.story.why_next ? (
        <p className="lr-next-why">{session.story.why_next}</p>
      ) : null}
      <div className="lr-actions">
        {nextLesson ? (
          <button type="button" className="duo-button duo-button-primary" onClick={() => onNextLesson(nextLesson)}>
            Next: {humanSkill(nextLesson)} →
          </button>
        ) : null}
        <button type="button" className="duo-button duo-button-secondary" onClick={onExit}>
          Back to my path
        </button>
      </div>
    </div>
  )
}

function isEditorish(step: LadderStep): boolean {
  if (step.widget === 'code' || step.widget === 'tiny_coding') return true
  // A fill step whose template is a program, not a sentence, belongs in the
  // editor: `return w * ___ + b` is unreadable as a row of text inputs.
  return (step.widget === 'fill_blank' || step.widget === 'code_completion') && (step.starter_code || '').includes('\n')
}

function hasAnswer(step: LadderStep, input: Record<string, any>): boolean {
  switch (step.widget) {
    case 'ordering':
      return (input.order || input.answers || []).length === (step.options || []).length
    case 'matching':
      return (input.pairs || []).length === (step.pairs || []).length
    case 'select_multiple':
      return (input.answers || input.selected || []).length > 0
    case 'fill_blank':
    case 'code_completion':
      return Boolean((input.answers || []).filter(Boolean).length) || Boolean(input.code)
    case 'code':
    case 'tiny_coding':
    case 'identify_mistake':
      return (input.code ?? step.starter_code ?? '').trim().length > 0 && !/(^|\n)\s*(#\s*TODO|pass\s*$)/m.test(input.code ?? '')
    default:
      return String(input.answer ?? '').trim().length > 0
  }
}

const STAGE_LABELS: Record<string, string> = {
  introduce: 'The idea',
  show: 'Worked example',
  interact: 'Try it',
  guided: 'Put it together',
  scaffolded: 'Finish it',
  independent: 'Your turn',
  explain: 'Find the bug',
  transfer: 'New situation',
  mastery: 'Prove it',
  review: 'Recall',
}

function stageLabel(stage: string) {
  return STAGE_LABELS[stage] || humanStage(stage)
}

function stageWin(stage: string) {
  if (stage === 'independent' || stage === 'transfer') return 'That works'
  if (stage === 'explain') return 'Found it'
  if (stage === 'mastery') return 'Demonstrated'
  return 'Correct'
}

function humanStage(stage: string) {
  return stage.charAt(0).toUpperCase() + stage.slice(1)
}

/** `linear-prediction` / `linreg-predict` → `Linear prediction` / `Linreg predict`. */
function humanSkill(id: string) {
  const words = id.split(/[-_]/).filter(Boolean)
  const [first, ...rest] = words
  if (!first) return id
  return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(' ')
}

export type { LadderSession, LadderStep, StepOutcome }
