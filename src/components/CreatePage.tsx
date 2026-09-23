import React, { useState, useEffect, useRef } from 'react'
import { ProjectWorkspace } from './create/ProjectWorkspace'
import { CreateCourseError, projectApi, type ProjectSummary } from '../utils/projectApi'

export interface CreatePageProps {
  // Retained for backwards compatibility with the app shell; the guided-project
  // flow manages its own workspace and does not use this callback.
  onCourseReady?: (courseId: string) => void
}

export type CreateStep = 'input' | 'workspace'

type GateFeedback = {
  kind: 'reject' | 'insufficient' | 'error'
  title: string
  message: string
  nextStep: string
  missing: string[]
}

function gateFromError(err: unknown): GateFeedback {
  if (err instanceof CreateCourseError) {
    const kind = err.decision === 'reject' ? 'reject' : err.decision === 'insufficient' ? 'insufficient' : 'error'
    const title =
      kind === 'reject'
        ? "This source isn't suitable for a coding project"
        : kind === 'insufficient'
          ? "Not enough information to build a course"
          : 'Could not build a guided project'
    return {
      kind,
      title,
      message: err.message,
      nextStep: err.nextStep,
      missing: err.missingInformation,
    }
  }
  return {
    kind: 'error',
    title: 'Could not build a guided project',
    message: (err as Error).message || 'Could not build a guided project from this source.',
    nextStep: '',
    missing: [],
  }
}

export const CreatePage: React.FC<CreatePageProps> = () => {
  const [step, setStep] = useState<CreateStep>('input')
  const [materialType, setMaterialType] = useState<'youtube_url' | 'youtube_playlist' | 'transcript' | 'file_upload' | 'github_repo'>('youtube_url')
  const [inputContent, setInputContent] = useState('')
  const [courseTitle, setCourseTitle] = useState('')

  const [projectCourseId, setProjectCourseId] = useState<string | null>(null)
  const [creatingProject, setCreatingProject] = useState(false)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [gateFeedback, setGateFeedback] = useState<GateFeedback | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [cancelMessage, setCancelMessage] = useState<string | null>(null)
  const createAbortRef = useRef<AbortController | null>(null)

  // Load resumable guided projects for the Create Course section.
  useEffect(() => {
    let mounted = true
    projectApi
      .list()
      .then((list) => mounted && setProjects(list))
      .catch(() => {})
    return () => {
      mounted = false
    }
  }, [step])

  // Build a guided project (persistent workspace) from the source.
  const handleStartProject = async () => {
    setGateFeedback(null)
    setErrorMessage(null)
    setCancelMessage(null)
    setCreatingProject(true)

    const controller = new AbortController()
    createAbortRef.current = controller

    let reqType = materialType
    if (materialType === 'youtube_url' && inputContent.includes('list=')) {
      reqType = 'youtube_playlist'
    }

    try {
      const project = await projectApi.create(
        {
          material_type: reqType,
          content: inputContent,
          title: courseTitle,
        },
        { signal: controller.signal }
      )
      setProjectCourseId(project.course_id)
      setStep('workspace')
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        setCancelMessage('Build cancelled.')
        return
      }
      setGateFeedback(gateFromError(err))
      try {
        setProjects(await projectApi.list())
      } catch {
        /* listing is best-effort; the source was still not accepted */
      }
    } finally {
      createAbortRef.current = null
      setCreatingProject(false)
    }
  }

  const handleCancelBuild = () => {
    createAbortRef.current?.abort()
  }

  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleDeleteProject = async (courseId: string, title: string, e?: React.MouseEvent) => {
    e?.preventDefault()
    e?.stopPropagation()
    const ok = window.confirm(`Delete “${title}”? This cannot be undone.`)
    if (!ok) return
    setDeletingId(courseId)
    setErrorMessage(null)
    try {
      await projectApi.remove(courseId)
      setProjects((prev) => prev.filter((p) => p.course_id !== courseId))
    } catch (err) {
      setErrorMessage((err as Error).message || 'Could not delete this project.')
    } finally {
      setDeletingId(null)
    }
  }

  const openProject = (courseId: string) => {
    setProjectCourseId(courseId)
    setStep('workspace')
  }

  // Guided Project workspace takes over the Create Course view.
  if (step === 'workspace' && projectCourseId) {
    return (
      <ProjectWorkspace
        courseId={projectCourseId}
        onExit={() => {
          setStep('input')
          setProjectCourseId(null)
        }}
      />
    )
  }

  return (
    <div className="create-page-container" style={{ padding: '32px', maxWidth: '800px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 900, color: 'var(--ink)' }}>✨ AI Course Builder</h1>
        <p style={{ fontSize: '15px', fontWeight: 700, color: 'var(--ink-soft)' }}>
          Bring a tutorial — a YouTube video, playlist, transcript, or notes. Patchwork turns it into a guided project you actually build, step by step.
        </p>
      </div>

      {gateFeedback && (
        <div
          className={`create-gate create-gate-${gateFeedback.kind}`}
          role="alert"
          data-testid="create-source-gate"
        >
          <strong>{gateFeedback.title}</strong>
          <p>{gateFeedback.message}</p>
          {gateFeedback.missing.length > 0 && (
            <ul className="create-gate-missing">
              {gateFeedback.missing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          {gateFeedback.nextStep && !gateFeedback.message.includes(gateFeedback.nextStep) && (
            <p className="create-gate-next">{gateFeedback.nextStep}</p>
          )}
        </div>
      )}

      {errorMessage && (
        <div
          style={{ padding: '12px 16px', borderRadius: '12px', background: '#fef2f2', color: '#991b1b', fontWeight: 700, marginBottom: '20px' }}
          role="alert"
        >
          {errorMessage}
        </div>
      )}

      {cancelMessage && (
        <div style={{ padding: '12px 16px', borderRadius: '12px', background: '#f3f4f6', color: 'var(--ink-soft)', fontWeight: 700, marginBottom: '20px' }}>
          {cancelMessage}
        </div>
      )}

      {creatingProject && (
        <div
          className="duo-card"
          style={{ padding: '20px', marginBottom: '20px', textAlign: 'center' }}
          role="status"
          aria-live="polite"
        >
          <p style={{ fontSize: '15px', fontWeight: 800, color: 'var(--ink)', marginBottom: '6px' }}>
            Building your guided project…
          </p>
          <p style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink-soft)', marginBottom: '16px' }}>
            Fetching the source, planning milestones, and preparing your workspace.
          </p>
          <button
            type="button"
            className="duo-button duo-button-secondary"
            onClick={handleCancelBuild}
            aria-label="Cancel build"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Resume in-progress guided projects */}
      {projects.length > 0 && (
        <div className="duo-card" style={{ padding: '16px', marginBottom: '20px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 900, marginBottom: '10px', color: 'var(--ink)' }}>
            Resume a project
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {projects.map((p) => (
              <div key={p.course_id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'stretch' }}>
                  <button
                    className="duo-button duo-button-secondary"
                    onClick={() => openProject(p.course_id)}
                    disabled={p.usable === false}
                    style={{ flex: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center', textAlign: 'left' }}
                  >
                    <span>{p.title}</span>
                    <span style={{ fontSize: '12px', fontWeight: 800, color: 'var(--ink-soft)' }}>
                      {p.usable === false ? 'Can’t be opened' : p.completed ? 'Completed' : `${p.completion_percent}%`}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="duo-button duo-button-secondary"
                    onClick={(e) => handleDeleteProject(p.course_id, p.title, e)}
                    disabled={deletingId === p.course_id}
                    aria-label={`Delete ${p.title}`}
                    style={{ padding: '10px 14px', color: '#991b1b', flexShrink: 0 }}
                  >
                    {deletingId === p.course_id ? '…' : 'Delete'}
                  </button>
                </div>
                {/* The reason the server gave, not a generic "invalid". A learner who
                    spent twenty minutes building this deserves to know which part of
                    the source failed, and Delete is the only action left to them. */}
                {p.usable === false && p.unusable_reason && (
                  <p style={{ fontSize: '12px', fontWeight: 700, color: 'var(--ink-soft)', margin: 0 }}>
                    {p.unusable_reason}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="duo-card" style={{ padding: '24px', opacity: creatingProject ? 0.55 : 1, pointerEvents: creatingProject ? 'none' : 'auto' }}>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
          {[
            { type: 'youtube_url', label: 'YouTube URL / Playlist' },
            { type: 'github_repo', label: 'GitHub Repository' },
            { type: 'transcript', label: 'Paste Transcript / Notes' },
            { type: 'file_upload', label: 'Upload File' },
          ].map(({ type, label }) => (
            <button
              key={type}
              className={`duo-button ${materialType === type ? 'duo-button-primary' : 'duo-button-secondary'}`}
              onClick={() => setMaterialType(type as any)}
              style={{ flex: 1, padding: '10px' }}
            >
              {label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
          <div>
            <label style={{ display: 'block', fontWeight: 800, fontSize: '13px', marginBottom: '6px' }}>
              Project Title (Optional):
            </label>
            <input
              type="text"
              placeholder="e.g., Reproduce GPT-2 (124M)"
              value={courseTitle}
              onChange={(e) => setCourseTitle(e.target.value)}
              style={{ width: '100%', padding: '12px', borderRadius: '10px', border: '2px solid var(--line)', fontWeight: 700 }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontWeight: 800, fontSize: '13px', marginBottom: '6px' }}>
              {materialType === 'youtube_url'
                ? 'YouTube Video or Playlist URL:'
                : materialType === 'github_repo'
                  ? 'GitHub Repository URL:'
                  : 'Source Content / Transcript:'}
            </label>
            {materialType === 'youtube_url' || materialType === 'github_repo' ? (
              <input
                type="text"
                placeholder={materialType === 'github_repo'
                  ? 'https://github.com/owner/repo'
                  : 'https://www.youtube.com/watch?v=... or playlist URL'}
                value={inputContent}
                onChange={(e) => setInputContent(e.target.value)}
                style={{ width: '100%', padding: '12px', borderRadius: '10px', border: '2px solid var(--line)', fontWeight: 700 }}
              />
            ) : (
              <textarea
                rows={8}
                placeholder="Paste raw transcript, study guide, or Markdown notes here..."
                value={inputContent}
                onChange={(e) => setInputContent(e.target.value)}
                style={{ width: '100%', padding: '12px', borderRadius: '10px', border: '2px solid var(--line)', fontWeight: 700, fontFamily: 'inherit' }}
              />
            )}
            {materialType === 'github_repo' && (
              <p style={{ fontSize: '12px', fontWeight: 700, color: 'var(--ink-soft)', margin: '8px 0 0' }}>
                You rebuild the project yourself, file by file, in the order its own imports
                require. Public repositories with a license only — no code is copied into your
                workspace.
              </p>
            )}
          </div>
        </div>

        <button
          className="duo-button duo-button-primary"
          onClick={handleStartProject}
          disabled={(!inputContent.trim() && !courseTitle.trim()) || creatingProject}
          style={{ width: '100%', padding: '14px', fontSize: '16px' }}
        >
          Build Guided Project 🛠️
        </button>
        <p style={{ fontSize: '12px', fontWeight: 700, color: 'var(--ink-soft)', marginTop: '10px', textAlign: 'center' }}>
          You'll get one persistent workspace and build the source's project milestone by milestone.
        </p>
      </div>
    </div>
  )
}
