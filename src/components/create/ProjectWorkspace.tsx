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
const DEFAULT_TERMINAL_HEIGHT = 280
const MIN_TERMINAL_HEIGHT = 140
const MAX_TERMINAL_HEIGHT = 520

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
  const [showExample, setShowExample] = useState(false)
  const [celebrate, setCelebrate] = useState(false)

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const resizeRef = useRef<{ startY: number; startHeight: number } | null>(null)
  const verificationLogStart = useRef<number | null>(null)
  const historyRef = useRef<string[]>([])
  const historyIndexRef = useRef(-1)

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

  const clearTerminal = () => {
    setTerminalLines([])
    setCommand('')
  }

  const handleHistory = (direction: -1 | 1) => {
    const hist = historyRef.current
    if (!hist.length) return
    const next = historyIndexRef.current + direction
    if (next < 0) {
      historyIndexRef.current = -1
      setCommand('')
      return
    }
    historyIndexRef.current = Math.min(next, hist.length - 1)
    setCommand(hist[hist.length - 1 - historyIndexRef.current])
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
    historyIndexRef.current = -1
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
      appendTerminal(makeTerminalLine(res.status === 'project_complete' ? 'success' : 'info', res.feedback))
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
      <div className="pw-root">
        <div className="pw-error-state">
          <h2>Couldn't open this project</h2>
          <p>{loadError}</p>
          <button className="duo-button duo-button-secondary" onClick={onExit}>
            Back to Create
          </button>
        </div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="pw-root">
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

  return (
    <div className="pw-root" aria-label="Guided project workspace">
      {/* Header */}
      <header className="pw-header">
        <div className="pw-header-main">
          <button className="pw-exit" onClick={onExit} aria-label="Back to Create">
            ← Create
          </button>
          <div>
            <h1 className="pw-title">{project.title}</h1>
            <p className="pw-goal">{project.project_goal}</p>
          </div>
        </div>
        <div className="pw-header-stats">
          <div className="pw-progress">
            <div className="pw-progress-bar">
              <div className="pw-progress-fill" style={{ width: `${project.completion_percent}%` }} />
            </div>
            <span className="pw-progress-label">{project.completion_percent}% complete</span>
          </div>
          <div className="pw-stat">⚡ {project.xp} XP</div>
          <div className="pw-stat">📄 {project.files_changed} files</div>
          <div className="pw-stat">✓ {passedTests} tests passed</div>
        </div>
      </header>

      <div className="pw-body">
        {/* Left: milestone map */}
        <aside className="pw-milestones" aria-label="Project milestones">
          <h3 className="pw-panel-title">Project Milestones</h3>
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
        </aside>

        {/* Center: editor + terminal */}
        <main className="pw-editor-col">
          <div className="pw-editor-stack">
            <div className="pw-editor-pane">
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

              <textarea
                className="pw-editor"
                value={activeFile?.content ?? ''}
                onChange={(e) => updateActiveFile(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault()
                    handleRun()
                  }
                }}
                spellCheck={false}
                aria-label={`Editor for ${activePath}`}
                placeholder="Write your code here. Your work persists across the whole project."
              />

              <div className="pw-editor-toolbar">
                <button className="duo-button duo-button-secondary" onClick={handleRun} disabled={running}>
                  {running ? 'Running…' : '▶ Run'}
                </button>
                <span className="pw-toolbar-hint">Ctrl+Enter to run · type in the terminal like VS Code</span>
              </div>
            </div>

            <ProjectTerminal
              cwd={cwd}
              lines={terminalLines}
              command={command}
              running={running}
              height={terminalHeight}
              onCommandChange={setCommand}
              onSubmit={handleSubmitCommand}
              onRunProject={handleRun}
              onClear={clearTerminal}
              onHistory={handleHistory}
              onResizeStart={handleTerminalResizeStart}
            />
          </div>
        </main>

        {/* Right: AI guidance + NEXT */}
        <aside className="pw-guide" aria-label="AI guidance">
          {currentMilestone ? (
            <div className="pw-microstep">
              <span className="pw-microstep-label">
                Step {currentMilestone.order} · +{currentMilestone.xp_reward} XP
              </span>
              <h3 className="pw-microstep-title">
                {currentMilestone.hook || currentMilestone.title}
              </h3>
              {currentMilestone.teach && compactText(currentMilestone.teach, 420) && (
                <p className="pw-teach">{compactText(currentMilestone.teach, 420)}</p>
              )}
              {compactText(currentMilestone.microstep.action, 220) && (
                <p className="pw-action">
                  <strong>Do this:</strong> {compactText(currentMilestone.microstep.action, 220)}
                </p>
              )}
              {compactText(currentMilestone.microstep.hint, 220) && (
                <p className="pw-hint">💡 {compactText(currentMilestone.microstep.hint, 220)}</p>
              )}
              <div className="pw-microstep-controls">
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
              {showExample && currentMilestone.example && (
                <pre className="pw-example">{currentMilestone.example}</pre>
              )}
              {expandedWhy === currentMilestone.id && (
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
            <div className="pw-microstep">
              <h3 className="pw-microstep-title">🎉 Project complete!</h3>
              <p className="pw-observation">You built the whole project from the source.</p>
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
            <div className="pw-ai-row">
              <input
                className="pw-ai-input"
                placeholder="Ask the AI about this step…"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                aria-label="Ask the AI"
              />
              <button className="duo-button duo-button-secondary" onClick={handleAskAi} disabled={askingAi}>
                {askingAi ? '…' : 'Ask'}
              </button>
            </div>
            {guidance && (guidance.suggestion_note || guidance.suggestion) && (
              <div className="pw-suggestion">
                {guidance.suggestion_note && <p className="pw-suggestion-note">{guidance.suggestion_note}</p>}
                {guidance.suggestion && (
                  <>
                    <pre className="pw-suggestion-code">{guidance.suggestion}</pre>
                    <button className="duo-button duo-button-secondary pw-apply" onClick={applySuggestion}>
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

          <button
            className="duo-button duo-button-primary pw-next"
            onClick={handleNext}
            disabled={verifying || project.completed}
          >
            {verifying ? 'Verifying…' : project.completed ? 'Completed 🎉' : 'NEXT →'}
          </button>
          <p className="pw-next-hint">
            NEXT inspects your actual workspace and verifies real progress — implement it your own way.
          </p>
        </aside>
      </div>

      {celebrate && (
        <div className="pw-celebrate" role="dialog" aria-label="Project complete">
          <div className="pw-celebrate-card">
            <h2>🎉 You shipped it!</h2>
            <p>You built “{project.title}” end-to-end, verified against the source.</p>
            <p className="pw-celebrate-xp">⚡ {project.xp} XP earned</p>
            <div className="pw-celebrate-actions">
              <button className="duo-button duo-button-secondary" onClick={() => setCelebrate(false)}>
                Keep exploring
              </button>
              <button className="duo-button duo-button-primary" onClick={onExit}>
                Back to Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
