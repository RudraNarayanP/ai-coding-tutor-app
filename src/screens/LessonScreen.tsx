/**
 * The focused lesson: one step of a lesson session, or the lesson's own open-ended
 * code task when there is no step left.
 *
 * Markup lifted out of App.tsx verbatim. The screen exists at two URLs —
 * /lesson/:lessonId and /lesson/:lessonId/exercise/:exerciseId — and renders from
 * whichever step the router names, so a refresh or a pasted link rebuilds the
 * session with no help from React state.
 */

import { useLearning } from '../learning/useLearning'
import ExercisePanel from '../components/ExercisePanel'
import ExerciseWorkspace from '../components/ExerciseWorkspace'
import { TutorActions } from '../components/TutorActions'
import { DEFAULT_FEEDBACK, LANGUAGE_FILE_EXT } from '../learning/types'
import { NotFoundScreen } from './NotFoundScreen'

/**
 * Shown when Browser Back lands on a step this learner has already cleared.
 *
 * The step is read-only — the panel's `correct` phase disables the answer input
 * and offers Continue rather than Check — and it awards nothing, because the
 * backend already recorded the real attempt. Reusing the existing phase keeps
 * this from becoming a second feedback design.
 */
const CLEARED_STEP_FEEDBACK = {
  passed: true,
  feedback: 'You already cleared this step. Continue to pick up where you left off.',
  xpAwarded: 0,
  attempts: 1,
}

export function LessonScreen() {
  const {
    addNote,
    aiEnabled,
    allPassed,
    answerArmed,
    askSolution,
    askTutor,
    completion,
    code,
    completedExerciseCount,
    consecutiveCorrect,
    continueToNextExercise,
    currentProviderStatus,
    exerciseFeedback,
    exerciseInput,
    exercisePhase,
    exercisePosition,
    exerciseTotal,
    failedRequired,
    feedback,
    goBack,
    goToNextLesson,
    goUpstream,
    handleExerciseBack,
    hintDisabled,
    isAiAvailable,
    isLoadingLesson,
    isReviewingCompletedStep,
    isRunning,
    isTutorLoading,
    lesson,
    lessonError,
    lessonIsOpen,
    lessonWorkspaceExercise,
    level,
    mistakes,
    noteInput,
    restoreAnsweredBuffer,
    restoreSnapshot,
    results,
    resultsRef,
    retryCurrentExercise,
    runTests,
    selectedLanguage,
    selectedProvider,
    sessionNotes,
    setCelebration,
    setCode,
    setExerciseInput,
    setIsGuidebookOpen,
    setLesson,
    setNoteInput,
    soundEnabled,
    submitSubLessonExercise,
    toggleSound,
    tutorLevel,
    tutorSource,
    workspaceExercise,
  } = useLearning()

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

  if (lessonError === 'not_found') {
    // A lesson the server says does not exist is the route's problem, not the
    // editor's: say so instead of opening an empty workspace over a made-up
    // lesson, which is what this branch used to do.
    return <NotFoundScreen />
  }

  if (!lessonIsOpen) {
    // Still resolving the lesson the URL asked for.
    return (
      <div className="duo-page-container">
{isLoadingLesson && (
  <div role="status" aria-label="Loading lesson" style={{ position: "fixed", top: "12px", right: "24px", background: "var(--yellow)", color: "#000", padding: "8px 16px", borderRadius: "20px", fontWeight: 900, zIndex: 9999 }}>
    Loading lesson…
  </div>
)}
      </div>
    )
  }

  return (
    <div className="duo-page-container">
{isLoadingLesson && (
  <div role="status" aria-label="Loading lesson" style={{ position: "fixed", top: "12px", right: "24px", background: "var(--yellow)", color: "#000", padding: "8px 16px", borderRadius: "20px", fontWeight: 900, zIndex: 9999 }}>
    Loading lesson…
  </div>
)}
      {lesson ? (
        workspaceExercise ? (
    <ExercisePanel
      exercise={workspaceExercise}
      exerciseInput={exerciseInput}
      exercisePhase={isReviewingCompletedStep ? 'correct' : exercisePhase}
      exerciseFeedback={isReviewingCompletedStep ? CLEARED_STEP_FEEDBACK : exerciseFeedback}
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
      onBack={goBack}
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
        completion && (
          <div className={`duo-feedback-panel success ew-lesson-celebration${completion.mistakeFree ? ' ew-celebration--perfect' : ''}${completion.boss ? ' ew-celebration--boss' : ''}`} role="status">
            <div className="duo-feedback-title">
              <span>{completion.boss ? '👑 BOSS CLEARED!' : '🎉 Lesson Complete!'}</span>
              {completion.mistakeFree && (
                <span className="ew-perfect-badge">⚡ PERFECT — no mistakes!</span>
              )}
            </div>
            <p style={{ fontWeight: 700, marginBottom: '8px' }}>
              {completion.boss
                ? 'You just mastered a checkpoint — the hardest lesson in the unit!'
                : 'Awesome work! You completed every exercise in this lesson.'}
            </p>
            {completion.xpEarned > 0 && (
              <p style={{ fontWeight: 700, color: '#16a34a', marginBottom: '16px' }}>
                +{completion.xpEarned} XP earned
              </p>
            )}
            <div style={{ display: 'flex', gap: '12px' }}>
              {completion.nextLessonId ? (
                <button className="duo-button duo-button-primary" onClick={goToNextLesson}>
                  Next Lesson →
                </button>
              ) : null}
              <button
                className="duo-button duo-button-secondary"
                onClick={() => {
                  setCelebration(null)
                  // Up to the unit this lesson belongs to, read from the URL and
                  // the lesson's own unit id — no remembered "previous screen".
                  goUpstream()
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
      ) : null}
    </div>
  )
}
