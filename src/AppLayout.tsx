/**
 * The app shell: sidebar, top bar, global modals, and an Outlet where the router
 * puts the current screen.
 *
 * This owns chrome, not location. Which section is showing is answered by the URL
 * (see the route table in src/App.tsx); the session hook below supplies the data.
 */

import { Outlet, useNavigate } from 'react-router-dom'
import { GuidebookPanel } from './components/GuidebookPanel'
import { TutorActions } from './components/TutorActions'
import Settings from './components/Settings'
import { api } from './api'
import { useLearningSession } from './learning/useLearningSession'
import {
  coursesPath,
  createPath,
  leaderboardsPath,
  learnPath,
  practicePath,
  profilePath,
  questsPath,
  type AppView,
} from './learning/routes'
import {
  restoreHearts,
  setUnlimitedHearts as applyUnlimitedHearts,
} from './utils/gamification'

/** The seven sidebar destinations. `active` replaces the old `activeTab ===` tests. */
const NAV_ITEMS: {
  label: string
  icon: string
  path: string
  active: (view: AppView, lessonOpen: boolean) => boolean
}[] = [
  { label: 'LEARN', icon: '🏠', path: learnPath(), active: (v, open) => v === 'learn' && !open },
  { label: 'PRACTICE', icon: '💪', path: practicePath(), active: (v) => v === 'practice' },
  { label: 'QUESTS', icon: '🎯', path: questsPath(), active: (v) => v === 'quests' },
  { label: 'COURSES', icon: '📚', path: coursesPath(), active: (v) => v === 'courses' },
  { label: 'CREATE', icon: '✨', path: createPath(), active: (v) => v === 'create' },
  { label: 'LEADERBOARDS', icon: '🛡️', path: leaderboardsPath(), active: (v) => v === 'leaderboards' },
  { label: 'PROFILE', icon: '👤', path: profilePath(), active: (v) => v === 'profile' },
]

export function AppLayout() {
  const session = useLearningSession()
  const navigate = useNavigate()
  const {
    aiEnabled,
    answerArmed,
    applyHearts,
    askSolution,
    askTutor,
    backendError,
    code,
    completedCount,
    concepts,
    coursePathTitle,
    courses,
    currentProviderStatus,
    customTitle,
    dailyProgress,
    feedback,
    gamification,
    handleGenerateCourse,
    handleProviderSelection,
    hearts,
    hintDisabled,
    isAiAvailable,
    isExerciseWorkspace,
    isGeneratingCourse,
    isGuidebookOpen,
    isLessonActive,
    isLoadingLesson,
    isRunning,
    isTutorLoading,
    lesson,
    level,
    materialInput,
    materialType,
    maxHearts,
    profileStreak,
    progressPct,
    providersOverview,
    restoreAnsweredBuffer,
    restoreSnapshot,
    runTests,
    safeLessons,
    secondsToNextHeart,
    selectedLanguage,
    selectedProvider,
    setAiEnabled,
    setCustomTitle,
    setIsGuidebookOpen,
    setMaterialInput,
    setMaterialType,
    setShowCreateModal,
    setShowOutofHeartsModal,
    setShowSettings,
    showCreateModal,
    showLessonRunCode,
    showOutofHeartsModal,
    showSettings,
    soundEnabled,
    toggleSound,
    unlimitedHearts,
    view,
    xp,
  } = session

  return (
    <div className={`duo-layout${isExerciseWorkspace ? ' duo-layout--exercise-focus' : ''}${view === 'practice' ? ' duo-layout--practice' : ''}`}>
      {/* ─── Left Sidebar Navigation Bar ─────────────────────────────────── */}
      <aside className="duo-nav-sidebar" aria-label="Main Navigation">
        <div className="duo-logo-area">
          <div className="duo-logo-text">patchwork</div>
        </div>

        <nav className="duo-nav-menu" aria-label="App Navigation Tabs">
          {/*
            Same buttons, same markup — only the click handler changed. Each one
            pushes a route, so the browser bar and this highlight are the same
            fact read from the same place. They stay buttons (rather than links)
            because that is what they have always been to the keyboard and to the
            accessibility queries in the existing tests.
          */}
          {NAV_ITEMS.map((item) => (
            <button
              key={item.path}
              className={`duo-nav-item ${item.active(view, isLessonActive) ? 'active' : ''}`}
              onClick={() => navigate(item.path)}
            >
              <span className="duo-nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
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
        {!isExerciseWorkspace && view !== 'practice' && (
        <header className="duo-top-header" role="banner">
          <div className="duo-header-left">
            <button
              type="button"
              className="duo-button duo-button-secondary"
              style={{ padding: '6px 12px', fontSize: '12px' }}
              onClick={() => navigate(coursesPath())}
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
            {/* The number that matters: concepts the learner has demonstrated
                independently. XP and streak stay, but they are not the goal. */}
            {concepts && concepts.total > 0 ? (
              <div
                className="duo-stat-pill"
                title={`${concepts.demonstrated} of ${concepts.total} concepts demonstrated independently`}
                aria-label={`Concepts demonstrated: ${concepts.demonstrated}`}
              >
                <span className="lr-metric">
                  <span className="lr-metric-val">🧠 {concepts.demonstrated}</span>
                  <span className="lr-metric-lbl">demonstrated</span>
                </span>
              </div>
            ) : null}
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

        {/* ─── The current screen, per the URL ──────────────────────────────
            This one line replaces the seven `activeTab === …` branches that used
            to live here. The session is handed down through the outlet so a
            screen reads its data without App plumbing each value as a prop. */}
        <Outlet context={session} />

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
        {/* ─── Bottom Footer Action Bar (only when the workspace is not open) ── */}
        {view === 'learn' && isLessonActive && showLessonRunCode && !isExerciseWorkspace && (
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
