import React from 'react'
import type { TestResult } from '../api'
import { CodeEditor } from './CodeEditor'
import { TestResults } from './TestResults'

interface LessonWorkspaceProps {
  lessonTitle: string
  lessonDescription: string
  code: string
  onCodeChange: (v: string) => void
  onRun: () => void
  isRunning: boolean
  runDisabled: boolean
  testResults: TestResult[] | null
  testPassed: boolean
  testCompleted: boolean
  // AI / hint
  aiAvailable: boolean
  aiEnabled: boolean
  onToggleAi: () => void
  onRequestHint: () => void
  tutorFeedback: string | null
  tutorLoading: boolean
  // Solution
  onViewSolution: () => void
  // Completion
  showCompletion: boolean
  onNextLesson: () => void
  // Status
  aiStatusText: string
  aiStatusDetail: string
}

// ─── LessonWorkspace ─────────────────────────────────────────────────────────
// The main content pane. Hosts the lesson header, code editor, run controls,
// test results, AI tutor panel, and the completion/next-lesson flow.

export const LessonWorkspace: React.FC<LessonWorkspaceProps> = ({
  lessonTitle,
  lessonDescription,
  code,
  onCodeChange,
  onRun,
  isRunning,
  runDisabled,
  testResults,
  testPassed,
  testCompleted,
  aiAvailable,
  aiEnabled,
  onToggleAi,
  onRequestHint,
  tutorFeedback,
  tutorLoading,
  onViewSolution,
  showCompletion,
  onNextLesson,
  aiStatusText,
  aiStatusDetail,
}) => {
  // Derive the hint-button label/state from the AI availability model.
  const hintDisabled = !aiAvailable || !aiEnabled
  const hintLabel = !aiAvailable
    ? 'AI tutor unavailable'
    : !aiEnabled
      ? 'AI tutor is paused'
      : 'Request a hint'

  return (
    <div className="lesson-workspace">
      {/* Lesson header */}
      <header className="lesson-header">
        <h2 className="lesson-title">{lessonTitle}</h2>
        {lessonDescription && <p className="lesson-desc">{lessonDescription}</p>}
      </header>

      {/* AI status bar */}
      <div className={`ai-status-bar ${aiAvailable ? 'is-ready' : 'is-offline'}`}>
        <span className="ai-status-dot" aria-hidden="true" />
        <span className="ai-status-text">{aiStatusText}</span>
        {aiStatusDetail && <span className="ai-status-detail">{aiStatusDetail}</span>}
      </div>

      {/* Controls row */}
      <div className="lesson-controls">
        <button
          type="button"
          className="btn btn-run"
          onClick={onRun}
          disabled={runDisabled || isRunning}
        >
          {isRunning ? 'Running…' : 'Run code'}
        </button>

        <button
          type="button"
          className="btn btn-hint"
          onClick={onRequestHint}
          disabled={hintDisabled}
          aria-label={hintLabel}
        >
          {hintLabel}
        </button>

        <button
          type="button"
          className="btn btn-solution"
          onClick={onViewSolution}
        >
          View Solution
        </button>

        <button
          type="button"
          className={`btn btn-ai-toggle ${aiEnabled ? 'is-on' : 'is-off'}`}
          onClick={onToggleAi}
          aria-label={aiEnabled ? 'AI tutor on' : 'AI tutor off'}
        >
          {aiEnabled ? 'AI tutor on' : 'AI tutor off'}
        </button>
      </div>

      {/* Code editor */}
      <CodeEditor value={code} onChange={onCodeChange} filename="exercise.py" />

      {/* Tutor feedback */}
      {(tutorFeedback || tutorLoading) && (
        <div className="tutor-feedback" role="status" aria-label="Tutor feedback">
          {tutorLoading ? 'Thinking…' : tutorFeedback}
        </div>
      )}

      {/* Test results */}
      {testResults && (
        <TestResults tests={testResults} passed={testPassed} completed={testCompleted} />
      )}

      {/* Completion banner */}
      {showCompletion && (
        <div className="completion-banner" role="status">
          <span className="completion-icon" aria-hidden="true">🎉</span>
          <span className="completion-text">Lesson Complete!</span>
          <button type="button" className="btn btn-next" onClick={onNextLesson}>
            Next Lesson
          </button>
        </div>
      )}
    </div>
  )
}