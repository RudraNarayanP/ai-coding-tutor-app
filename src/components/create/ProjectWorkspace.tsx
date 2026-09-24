import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  projectApi,
  type CheckResult,
  type GuidanceResult,
  type NextResult,
  type ProjectView,
  type WorkspaceFile,
} from '../../utils/projectApi'
import { compactText, milestoneDescription, sourceExcerpt, whyExplanation } from './learnerCopy'
import { ProjectTerminal, makeTerminalLine, shellPrompt, type TerminalLine } from './ProjectTerminal'
import { CodeEditor } from '../CodeEditor'

// ─── ProjectWorkspace ─────────────────────────────────────────────────────────
// The persistent, VS Code-like workspace for a Create Course guided project.
// The learner owns the code across the whole project; the AI is read-only and
// only inspects the workspace when the learner clicks NEXT or asks for help.
// This component is rendered ONLY inside the Create Course flow.

export interface ProjectWorkspaceProps {
  courseId: string
  onExit: () => void
}

const AUTOSAVE_MS = 1200
const DEFAULT_TERMINAL_HEIGHT = 260
const MIN_TERMINAL_HEIGHT = 120
const MAX_TERMINAL_HEIGHT = 620

const SANDBOX_BANNER = [
  'Patchwork sandbox · bash · your files live in /workspace',
  'Try: ls · cat main.py · python main.py · pip install requests',
]

const TRANSCRIPT_FILLER =
  /\b(uh+|u+m+|er+|ah+|you know|kind of|sort of|i mean|gonna|we call it)\b/i

function looksLikeTranscript(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  if (TRANSCRIPT_FILLER.test(t)) return true
  if (t.split(/\s+/).length > 28) return true
  if (t.length > 90 && !t.includes('`') && (t.match(/\./g) || []).length === 0) return true
  return /\b(\w+(?:\s+\w+){0,3})\s+\1\b/i.test(t)
}

function lessonCopy(milestone: {
  title: string
  hook: string
  teach: string
  microstep: { observation: string; action: string; hint: string }
}) {
  const action = looksLikeTranscript(milestone.microstep.action)
    ? `Complete this step: ${milestone.title}.`
    : milestone.microstep.action
  const observation = looksLikeTranscript(milestone.microstep.observation) ? '' : milestone.microstep.observation
  const hook = looksLikeTranscript(milestone.hook) || milestone.hook.split(/\s+/).length > 12 ? '' : milestone.hook
  const teach = looksLikeTranscript(milestone.teach) ? '' : milestone.teach
  return { action, observation, hook, teach }
}

export const ProjectWorkspace: React.FC<ProjectWorkspaceProps> = ({ courseId, onExit }) => {
  const [project, setProject] = useState<ProjectView | null>(null)
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [activePath, setActivePath] = useState<string>('')
  const [loadError, setLoadError] = useState<string | null>(null)

  const [terminalLines, setTerminalLines] = useState<TerminalLine[]>([])
  const [command, setCommand] = useState('')
  const [cwd, setCwd] = useState('/workspace')
  const [terminalHeight, setTerminalHeight] = useState(DEFAULT_TERMINAL_HEIGHT)
  const [running, setRunning] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [nextResult, setNextResult] = useState<NextResult | null>(null)
  const [checks, setChecks] = useState<CheckResult[]>([])

  const [guidance, setGuidance] = useState<GuidanceResult | null>(null)
  const [askingAi, setAskingAi] = useState(false)
  const [question, setQuestion] = useState('')
  const [expandedWhy, setExpandedWhy] = useState<string | null>(null)
  const [expandedLearn, setExpandedLearn] = useState<string | null>(null)
  const [showExample, setShowExample] = useState(false)
  const [celebrate, setCelebrate] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const resizeRef = useRef<{ startY: number; startHeight: number } | null>(null)
  const verificationLogStart = useRef<number | null>(null)
  const historyRef = useRef<string[]>([])
  const historyIndexRef = useRef(0)

  const appendTerminal = useCallback((...lines: TerminalLine[]) => {
    setTerminalLines((prev) => [...prev, ...lines])
  }, [])

  // ── Load project ─────────────────────────────────────────────────────────
  useEffect(() => {
    let mounted = true
    projectApi
      .get(courseId)
      .then((p) => {
        if (!mounted) return
        setProject(p)
        setFiles(p.workspace_files.length ? p.workspace_files : [{ path: p.entry_file, content: '' }])
        setActivePath(p.entry_file || p.workspace_files[0]?.path || 'main.py')
        setTerminalLines(SANDBOX_BANNER.map((line) => makeTerminalLine('info', line)))
      })
      .catch((err) => mounted && setLoadError(err.message || 'Failed to load project'))
    return () => {
      mounted = false
    }
  }, [courseId])

  // Collapse the "Show example" panel whenever the active step changes.
  const currentStepKey = project?.milestones.find((m) => m.status === 'current')?.id ?? null
  useEffect(() => {
    setShowExample(false)
    setExpandedLearn(null)
  }, [currentStepKey])

  // ── Autosave (debounced) ───────────────────────────────────────────────────
  const scheduleSave = useCallback(
    (nextFiles: WorkspaceFile[]) => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => {
        projectApi.saveWorkspace(courseId, nextFiles).catch(() => {})
      }, AUTOSAVE_MS)
    },
    [courseId]
  )

  // Any edit invalidates the last verification result — clear the stale ✗/✓
  // feedback so a requirement the learner just satisfied is never shown as
  // "missing" until they re-run NEXT against the latest contents.
  const invalidateVerification = () => {
    setNextResult(null)
    setChecks([])
    if (verificationLogStart.current !== null) {
      setTerminalLines((prev) => prev.slice(0, verificationLogStart.current as number))
      verificationLogStart.current = null
    }
  }

  const updateActiveFile = (content: string) => {
    invalidateVerification()
    setFiles((prev) => {
      const next = prev.map((f) => (f.path === activePath ? { ...f, content } : f))
      scheduleSave(next)
      return next
    })
  }

  const addFile = () => {
    const name = window.prompt('New file name (e.g. helper.py)')
    if (!name) return
    const clean = name.trim()
    if (!clean || files.some((f) => f.path === clean)) return
    invalidateVerification()
    setFiles((prev) => {
      const next = [...prev, { path: clean, content: '' }]
      scheduleSave(next)
      return next
    })
    setActivePath(clean)
  }

  const clearTerminal = () => {
    setTerminalLines([])
    setCommand('')
  }

  const handleInterrupt = () => {
    setCommand('')
    appendTerminal(makeTerminalLine('info', '^C'))
  }

  const handleCandidates = (matches: string[]) => {
    appendTerminal(makeTerminalLine('stdout', matches.join('  ')))
  }

  const handleTerminalResizeStart = (event: React.MouseEvent) => {
    event.preventDefault()
    resizeRef.current = { startY: event.clientY, startHeight: terminalHeight }

    const onMove = (moveEvent: MouseEvent) => {
      if (!resizeRef.current) return
      const delta = resizeRef.current.startY - moveEvent.clientY
      const next = Math.min(
        MAX_TERMINAL_HEIGHT,
        Math.max(MIN_TERMINAL_HEIGHT, resizeRef.current.startHeight + delta)
      )
      setTerminalHeight(next)
    }

    const onUp = () => {
      resizeRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const handleHistory = (direction: -1 | 1) => {
    const hist = historyRef.current
    if (!hist.length) return
    // 0 = the learner's own live line; 1..n walk back through the log.
    const steps =
      direction === -1
        ? Math.min(historyIndexRef.current + 1, hist.length)
        : Math.max(historyIndexRef.current - 1, 0)
    historyIndexRef.current = steps
    setCommand(steps === 0 ? '' : hist[hist.length - steps])
  }

  const applyTerminalResult = (
    res: { stdout: string; stderr: string; exit_code: number; cwd: string; ran_ok: boolean; error: string | null }
  ) => {
    if (res.stdout) appendTerminal(makeTerminalLine('stdout', res.stdout.replace(/\n$/, '')))
    if (res.stderr) appendTerminal(makeTerminalLine('stderr', res.stderr.replace(/\n$/, '')))
    if (res.cwd) setCwd(res.cwd)
  }

  const runSandboxCommand = async (cmd: string) => {
    const trimmed = cmd.trim()
    if (!trimmed || running) return
    if (trimmed === 'clear' || trimmed === 'cls') {
      clearTerminal()
      return
    }
    const typed = `${shellPrompt(cwd)} ${trimmed}`
    setRunning(true)
    historyRef.current = [...historyRef.current, trimmed]
    historyIndexRef.current = 0
    setCommand('')
    appendTerminal(makeTerminalLine('command', typed))
    try {
      const res = await projectApi.exec(courseId, files, trimmed)
      applyTerminalResult(res)
    } catch (err) {
      appendTerminal(makeTerminalLine('error', (err as Error).message || 'Command failed'))
    } finally {
      setRunning(false)
    }
  }

  // ── Actions ────────────────────────────────────────────────────────────────
  const handleRun = async () => {
    if (!project || running) return
    await runSandboxCommand(`python ${project.entry_file || 'main.py'}`)
  }

  const handleSubmitCommand = async () => {
    await runSandboxCommand(command)
  }

  const handleNext = async () => {
    setVerifying(true)
    setTerminalLines((prev) => {
      verificationLogStart.current = prev.length
      return [...prev, makeTerminalLine('info', '— Verifying milestone —')]
    })
    try {
      const res = await projectApi.next(courseId, files)
      setNextResult(res)
      setChecks(res.checks || [])
      setProject(res.project)
      if (res.stdout) appendTerminal(makeTerminalLine('stdout', res.stdout))
      if (res.stderr) appendTerminal(makeTerminalLine('stderr', res.stderr))
      appendTerminal(makeTerminalLine('info', res.feedback))
      if (res.status === 'project_complete') {
        setCelebrate(true)
      }
    } catch (err) {
      const message = (err as Error).message
      appendTerminal(makeTerminalLine('error', message))
      setChecks([{ description: 'Verification failed', passed: false, detail: message }])
    } finally {
      setVerifying(false)
    }
  }

  const handleDeleteProject = async () => {
    const label = project?.title || 'this project'
    const ok = window.confirm(`Delete “${label}”? This cannot be undone.`)
    if (!ok) return
    setDeleting(true)
    try {
      await projectApi.remove(courseId)
      onExit()
    } catch (err) {
      setLoadError((err as Error).message || 'Could not delete this project.')
    } finally {
      setDeleting(false)
    }
  }

  const handleAskAi = async () => {
    setAskingAi(true)
    try {
      const res = await projectApi.guidance(courseId, files, question)
      setGuidance(res)
    } catch {
      /* guidance is best-effort */
    } finally {
      setAskingAi(false)
    }
  }

  const applySuggestion = () => {
    if (!guidance?.suggestion) return
    invalidateVerification()
    setFiles((prev) => {
      const next = prev.map((f) =>
        f.path === activePath ? { ...f, content: `${f.content.replace(/\s*$/, '')}\n\n${guidance.suggestion}\n` } : f
      )
      scheduleSave(next)
      return next
    })
  }

  // ── Render helpers ──────────────────────────────────────────────────────────
  if (loadError) {
    return (
      <div className="ew-root pw-root">
        <div className="pw-error-state">
          <h2>Couldn't open this project</h2>
          <p>{loadError}</p>
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="ew-btn ew-btn-back" onClick={onExit}>
              Back to Create
            </button>
            <button
              type="button"
              className="ew-btn ew-btn-back pw-delete"
              onClick={handleDeleteProject}
              disabled={deleting}
              aria-label="Delete this project"
            >
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="ew-root pw-root">
        <div className="pw-loading">Loading your project workspace…</div>
      </div>
    )
  }

  const activeFile = files.find((f) => f.path === activePath) || files[0]
  const currentMilestone =
    project.milestones.find((m) => m.status === 'current') ||
    project.milestones.find((m) => m.status !== 'completed') ||
    null
  const currentMilestoneId = currentMilestone?.id ?? null
  const passedTests = checks.filter((c) => c.passed).length
  const lesson = currentMilestone ? lessonCopy(currentMilestone) : null

  return (
    <div className="ew-root pw-root" aria-label="Guided project workspace">
      <header className="ew-topbar">
        <button type="button" className="ew-close" onClick={onExit} aria-label="Back to Create">
          ✕
        </button>
        <div
          className="ew-progress"
          role="progressbar"
          aria-label="Project progress"
          aria-valuenow={project.completion_percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="ew-progress-fill" style={{ width: `${project.completion_percent}%` }} />
        </div>
        <div className="ew-topbar-actions">
          <span className="pw-chip">⚡ {project.xp} XP</span>
          <span className="pw-chip">📄 {project.files_changed} files</span>
          <span className="pw-chip">✓ {passedTests} tests passed</span>
          <span className="pw-chip pw-chip-muted">{project.completion_percent}% complete</span>
          <button
            type="button"
            className="ew-topbar-link pw-delete"
            onClick={handleDeleteProject}
            disabled={deleting}
            aria-label="Delete this project"
          >
            {deleting ? 'Deleting…' : '🗑 Delete'}
          </button>
        </div>
      </header>

      <div className="ew-body ew-body--create">
        {/* Left: project + current step + milestone map */}
        <aside className="ew-task-col" aria-label="Project guidance">
          <span className="ew-section-label">Create</span>

          <div className="ew-task-card">
            <div className="ew-task-badge">
              <span className="ew-task-badge-icon" aria-hidden="true">🛠️</span> YOUR PROJECT
            </div>
            <h2 className="ew-task-title">{project.title}</h2>
            <p className="ew-task-desc">{project.course_intro || project.project_goal}</p>
          </div>

          {currentMilestone ? (
            <div className="ew-task-card pw-microstep">
              <div className="ew-task-badge">
                <span className="ew-task-badge-icon" aria-hidden="true">📋</span>
                Step {currentMilestone.order} · +{currentMilestone.xp_reward} XP
              </div>
              <h3 className="ew-task-title">{lesson?.hook || currentMilestone.title}</h3>
              {lesson?.observation && <p className="ew-task-desc">{lesson.observation}</p>}
              {lesson?.action && (
                <p className="pw-action">
                  <strong>Do this:</strong> {lesson.action}
                </p>
              )}
              {compactText(currentMilestone.microstep.hint, 220) && (
                <p className="pw-hint">💡 {compactText(currentMilestone.microstep.hint, 220)}</p>
              )}
              <div className="pw-microstep-controls">
                {lesson?.teach && (
                  <button
                    className="pw-why"
                    onClick={() =>
                      setExpandedLearn(expandedLearn === currentMilestone.id ? null : currentMilestone.id)
                    }
                  >
                    {expandedLearn === currentMilestone.id ? 'Hide' : 'Learn more'}
                  </button>
                )}
                {currentMilestone.example && (
                  <button className="pw-why" onClick={() => setShowExample((v) => !v)}>
                    {showExample ? 'Hide example' : 'Show example'}
                  </button>
                )}
                <button
                  className="pw-why"
                  onClick={() => setExpandedWhy(expandedWhy === currentMilestone.id ? null : currentMilestone.id)}
                >
                  {expandedWhy === currentMilestone.id ? 'Hide' : 'Why?'}
                </button>
              </div>
              {expandedLearn === currentMilestone.id && lesson?.teach && (
                <div className="pw-why-body">
                  <p>{lesson?.teach}</p>
                </div>
              )}
              {showExample && currentMilestone.example && (
                <pre className="pw-example">{currentMilestone.example}</pre>
              )}
              {expandedWhy === currentMilestone.id && currentMilestone.why && (
                <div className="pw-why-body">
                  <p>{whyExplanation(currentMilestone)}</p>
                  {sourceExcerpt(currentMilestone.source_quote) && (
                    <p className="pw-source-note">
                      <strong>From the source:</strong> “{sourceExcerpt(currentMilestone.source_quote)}”
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="ew-task-card pw-microstep">
              <div className="ew-task-badge">
                <span className="ew-task-badge-icon" aria-hidden="true">🎉</span> Project complete
              </div>
              <h3 className="ew-task-title">You built the whole project from the source.</h3>
            </div>
          )}

          {/* Verification feedback */}
          {nextResult && (
            <div className={`pw-verify ${nextResult.status === 'project_complete' ? 'ok' : 'pending'}`}>
              <p className="pw-verify-feedback">{nextResult.feedback}</p>
              {nextResult.advanced.length > 0 && (
                <ul className="pw-advanced">
                  {nextResult.advanced.map((a) => {
                    const done = project.milestones.find((m) => m.id === a.milestone_id)
                    return (
                      <li key={a.milestone_id}>
                        {done?.celebrate ? done.celebrate : '✓'} {a.title}{' '}
                        {a.xp_awarded > 0 ? `(+${a.xp_awarded} XP)` : '(already done)'}
                      </li>
                    )
                  })}
                </ul>
              )}
              {checks.length > 0 && nextResult.status === 'incomplete' && (
                <ul className="pw-checks">
                  {checks.map((c, i) => (
                    <li key={i} className={c.passed ? 'pw-check-pass' : 'pw-check-fail'}>
                      {c.passed ? '✓' : '✗'} {c.description}
                      {!c.passed && c.detail && <span className="pw-check-detail"> — {c.detail}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* AI help (read-only) */}
          <div className="pw-ai">
            <span className="ew-section-label">Ask the AI</span>
            <div className="pw-ai-row">
              <input
                className="pw-ai-input"
                placeholder="Ask about this step…"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                aria-label="Ask the AI"
              />
              <button className="ew-btn ew-btn-submit" onClick={handleAskAi} disabled={askingAi}>
                {askingAi ? '…' : 'Ask'}
              </button>
            </div>
            {guidance && (guidance.suggestion_note || guidance.suggestion) && (
              <div className="pw-suggestion">
                {guidance.suggestion_note && <p className="pw-suggestion-note">{guidance.suggestion_note}</p>}
                {guidance.suggestion && (
                  <>
                    <pre className="pw-suggestion-code">{guidance.suggestion}</pre>
                    <button className="ew-btn ew-btn-back pw-apply" onClick={applySuggestion}>
                      Apply suggestion
                    </button>
                  </>
                )}
                {guidance.provider_used && (
                  <span className="pw-provider">via {guidance.provider_used}</span>
                )}
              </div>
            )}
          </div>

          <div className="pw-milestones">
            <span className="ew-section-label">Project milestones</span>
            <ol className="pw-milestone-list">
              {project.milestones.map((m) => (
                <li
                  key={m.id}
                  className={`pw-milestone pw-milestone-${m.status}`}
                  aria-current={m.status === 'current' ? 'step' : undefined}
                >
                  <span className="pw-milestone-icon">
                    {m.status === 'completed' ? '✓' : m.status === 'current' ? '▶' : '○'}
                  </span>
                  <div className="pw-milestone-body">
                    <span className="pw-milestone-title">{m.title}</span>
                    {m.status === 'current' && milestoneDescription(m) && (
                      <span className="pw-milestone-source">{milestoneDescription(m)}</span>
                    )}
                  </div>
                  {m.status !== 'pending' && <span className="pw-milestone-xp">+{m.xp_reward}</span>}
                </li>
              ))}
            </ol>
            {project.tech_stack.length > 0 && (
              <div className="pw-techstack">
                <span className="pw-techstack-label">From the source:</span>
                {project.tech_stack.map((t) => (
                  <span key={t} className="pw-tech-pill">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* Right: editor + terminal, with the action bar below */}
        <div className="ew-workspace-pane">
          <div className="ew-workspace-columns ew-workspace-columns--single">
            <main className="ew-editor-col" aria-label="Code editor">
              <div className="pw-file-bar">
                <div className="pw-file-tabs" role="tablist" aria-label="Workspace files">
                  {files.map((f) => (
                    <button
                      key={f.path}
                      role="tab"
                      aria-selected={f.path === activePath}
                      className={`pw-file-tab ${f.path === activePath ? 'active' : ''}`}
                      onClick={() => setActivePath(f.path)}
                    >
                      {f.path}
                    </button>
                  ))}
                  <button className="pw-file-add" onClick={addFile} aria-label="Add file">
                    +
                  </button>
                </div>
                <span className="pw-toolbar-hint">Ctrl+Enter to run · type in the terminal</span>
              </div>

              <div className="ew-editor-shell">
                <CodeEditor
                  value={activeFile?.content ?? ''}
                  onChange={updateActiveFile}
                  filename={activePath || 'main.py'}
                  variant="workspace"
                  showHeader={false}
                  ariaLabel={`Editor for ${activePath}`}
                  onKeyDown={(e) => {
                    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                      e.preventDefault()
                      handleRun()
                    }
                  }}
                />
              </div>

              <ProjectTerminal
                cwd={cwd}
                lines={terminalLines}
                command={command}
                running={running}
                height={terminalHeight}
                completions={files.map((f) => f.path)}
                onCommandChange={setCommand}
                onSubmit={handleSubmitCommand}
                onInterrupt={handleInterrupt}
                onRunProject={handleRun}
                onClear={clearTerminal}
                onHistory={handleHistory}
                onResizeStart={handleTerminalResizeStart}
                onCandidates={handleCandidates}
              />
            </main>
          </div>

          <footer className="ew-footer">
            <div className="ew-footer-left">
              <button type="button" className="ew-btn ew-btn-back" onClick={onExit}>
                <span aria-hidden="true">←</span> BACK TO CREATE
              </button>
              <span className="pw-next-hint">
                NEXT inspects your actual workspace and verifies real progress.
              </span>
            </div>
            <div className="ew-footer-right">
              <button
                type="button"
                className="ew-btn ew-btn-run"
                onClick={handleRun}
                disabled={running}
                aria-label="Run code"
              >
                <span aria-hidden="true">▷</span> {running ? 'Running…' : 'RUN'}
              </button>
              <button
                type="button"
                className="ew-btn ew-btn-submit"
                onClick={handleNext}
                disabled={verifying || project.completed}
              >
                {verifying ? 'VERIFYING…' : project.completed ? 'COMPLETED 🎉' : 'NEXT →'}
              </button>
            </div>
          </footer>
        </div>
      </div>

      {celebrate && (
        <div className="pw-celebrate" role="dialog" aria-label="Project complete">
          <div className="pw-celebrate-card">
            <h2>🎉 You shipped it!</h2>
            <p>You built “{project.title}” end-to-end, verified against the source.</p>
            <p className="pw-celebrate-xp">⚡ {project.xp} XP earned</p>
            <div className="pw-celebrate-actions">
              <button className="ew-btn ew-btn-back" onClick={() => setCelebrate(false)}>
                Keep exploring
              </button>
              <button className="ew-btn ew-btn-submit" onClick={onExit}>
                Back to Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
