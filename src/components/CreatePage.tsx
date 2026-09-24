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
  const [materialType, setMaterialType] = useState<'youtube_url' | 'youtube_playlist' | 'transcript' | 'file_upload'>('youtube_url')
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
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(() => new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const toggleProjectSelected = (courseId: string, selected: boolean) => {
    setSelectedProjectIds((prev) => {
      const next = new Set(prev)
      if (selected) next.add(courseId)
      else next.delete(courseId)
      return next
    })
  }

  const allProjectsSelected =
    projects.length > 0 && projects.every((p) => selectedProjectIds.has(p.course_id))

  const toggleSelectAllProjects = () => {
    if (allProjectsSelected) {
      setSelectedProjectIds(new Set())
      return
    }
    setSelectedProjectIds(new Set(projects.map((p) => p.course_id)))
  }

  const handleDeleteSelectedProjects = async () => {
    const ids = projects.filter((p) => selectedProjectIds.has(p.course_id)).map((p) => p.course_id)
    if (ids.length === 0) return
    const ok = window.confirm(
      `Delete ${ids.length} selected project${ids.length === 1 ? '' : 's'}? This cannot be undone.`
    )
    if (!ok) return
    setBulkDeleting(true)
    setErrorMessage(null)
    const failed: string[] = []
    for (const courseId of ids) {
      try {
        await projectApi.remove(courseId)
      } catch {
        failed.push(courseId)
      }
    }
    const removed = new Set(ids.filter((id) => !failed.includes(id)))
    setProjects((prev) => prev.filter((p) => !removed.has(p.course_id)))
    setSelectedProjectIds(new Set(failed))
    if (failed.length > 0) {
      setErrorMessage(`Could not delete ${failed.length} project${failed.length === 1 ? '' : 's'}.`)
    }
    setBulkDeleting(false)
  }

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
      setSelectedProjectIds((prev) => {
        if (!prev.has(courseId)) return prev
        const next = new Set(prev)
        next.delete(courseId)
        return next
      })
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
    <div className="cw-page">
      <div className="cw-hero">
        <span className="ew-section-label">Create</span>
        <h1 className="cw-title">Build a guided project from any tutorial</h1>
        <p className="cw-sub">
          Bring a YouTube video, playlist, transcript, or notes. Patchwork turns it into a guided project
          you actually build, step by step.
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
        <div className="cw-alert cw-alert-error" role="alert">
          {errorMessage}
        </div>
      )}

      {cancelMessage && <div className="cw-alert">{cancelMessage}</div>}

      {creatingProject && (
        <div className="ew-task-card cw-building" role="status" aria-live="polite">
          <p className="cw-building-title">Building your guided project…</p>
          <p className="cw-building-note">
            Fetching the source, planning milestones, and preparing your workspace.
          </p>
          <button type="button" className="ew-btn ew-btn-back" onClick={handleCancelBuild} aria-label="Cancel build">
            Cancel
          </button>
        </div>
      )}

      {/* Resume in-progress guided projects */}
      {projects.length > 0 && (
        <section className="ew-task-card">
          <div className="cw-row-between">
            <span className="ew-section-label">Resume a project</span>
            <div className="cw-row-actions">
              <label className="cw-checkbox">
                <input
                  type="checkbox"
                  checked={allProjectsSelected}
                  onChange={toggleSelectAllProjects}
                  aria-label="Select all projects"
                />
                Select all
              </label>
              <button
                type="button"
                className="ew-btn ew-btn-back cw-btn-danger"
                onClick={handleDeleteSelectedProjects}
                disabled={selectedProjectIds.size === 0 || bulkDeleting || deletingId !== null}
                aria-label="Delete selected projects"
              >
                {bulkDeleting
                  ? 'Deleting…'
                  : `Delete selected${selectedProjectIds.size > 0 ? ` (${selectedProjectIds.size})` : ''}`}
              </button>
            </div>
          </div>
          <div className="cw-project-list">
            {projects.map((p) => (
              <div key={p.course_id} className="cw-project-row">
                <label className="cw-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedProjectIds.has(p.course_id)}
                    onChange={(e) => toggleProjectSelected(p.course_id, e.target.checked)}
                    aria-label={`Select ${p.title} for deletion`}
                  />
                </label>
                <button className="cw-project-open" onClick={() => openProject(p.course_id)}>
                  <span className="cw-project-title">{p.title}</span>
                  <span className="cw-project-progress">
                    {p.completed ? 'Completed' : `${p.completion_percent}%`}
                  </span>
                </button>
                <button
                  type="button"
                  className="ew-btn ew-btn-back cw-btn-danger"
                  onClick={(e) => handleDeleteProject(p.course_id, p.title, e)}
                  disabled={deletingId === p.course_id}
                  aria-label={`Delete ${p.title}`}
                >
                  {deletingId === p.course_id ? '…' : 'Delete'}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className={`ew-task-card${creatingProject ? ' cw-disabled' : ''}`}>
        <div className="cw-tabs">
          {[
            { type: 'youtube_url', label: 'YouTube URL / Playlist' },
            { type: 'transcript', label: 'Paste Transcript / Notes' },
            { type: 'file_upload', label: 'Upload File' },
          ].map(({ type, label }) => (
            <button
              key={type}
              type="button"
              className={`cw-tab${materialType === type ? ' active' : ''}`}
              aria-pressed={materialType === type}
              onClick={() => setMaterialType(type as any)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="cw-fields">
          <div className="cw-field">
            <label className="cw-label" htmlFor="cw-project-title">
              Project title (optional)
            </label>
            <input
              id="cw-project-title"
              className="cw-input"
              type="text"
              placeholder="e.g., Reproduce GPT-2 (124M)"
              value={courseTitle}
              onChange={(e) => setCourseTitle(e.target.value)}
            />
          </div>

          <div className="cw-field">
            <label className="cw-label" htmlFor="cw-source-content">
              {materialType === 'youtube_url' ? 'YouTube video or playlist URL' : 'Source content / transcript'}
            </label>
            {materialType === 'youtube_url' ? (
              <input
                id="cw-source-content"
                className="cw-input"
                type="text"
                placeholder="https://www.youtube.com/watch?v=... or playlist URL"
                value={inputContent}
                onChange={(e) => setInputContent(e.target.value)}
              />
            ) : (
              <textarea
                id="cw-source-content"
                className="cw-input cw-textarea"
                rows={8}
                placeholder="Paste raw transcript, study guide, or Markdown notes here..."
                value={inputContent}
                onChange={(e) => setInputContent(e.target.value)}
              />
            )}
          </div>
        </div>

        <button
          className="ew-btn ew-btn-submit cw-build"
          onClick={handleStartProject}
          disabled={(!inputContent.trim() && !courseTitle.trim()) || creatingProject}
        >
          BUILD GUIDED PROJECT
        </button>
        <p className="cw-footnote">
          You'll get one persistent workspace and build the source's project milestone by milestone.
        </p>
      </section>
    </div>
  )
}
