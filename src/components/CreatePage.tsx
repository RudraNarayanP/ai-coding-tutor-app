import React, { useState, useEffect } from 'react'
import { GuidebookPanel } from './GuidebookPanel'

export interface CreatePageProps {
  onCourseReady: (courseId: string) => void
}

export type CreateStep = 'input' | 'generating' | 'preview' | 'editing'

export interface CoursePreviewData {
  course_id: string
  title: string
  source_name: string
  source_url: string
  unit_count: number
  lesson_count: number
  exercise_count: number
  checkpoint_count: number
  topics: string[]
  difficulty: string
  domain: string
  language: string
  estimated_minutes: number
  sequencing_rationale: string
  access_notes: string[]
}

export const CreatePage: React.FC<CreatePageProps> = ({ onCourseReady }) => {
  const [step, setStep] = useState<CreateStep>('input')
  const [materialType, setMaterialType] = useState<'youtube_url' | 'youtube_playlist' | 'transcript' | 'file_upload'>('youtube_url')
  const [inputContent, setInputContent] = useState('')
  const [courseTitle, setCourseTitle] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)

  const [stages, setStages] = useState<Array<{ name: string; label: string; state: string }>>([])
  const [preview, setPreview] = useState<CoursePreviewData | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [duplicateCourse, setDuplicateCourse] = useState<{ existing_course_id: string; existing_title: string } | null>(null)

  // Edit controls state
  const [editTitle, setEditTitle] = useState('')
  const [editDifficulty, setEditDifficulty] = useState('beginner')
  const [editIntensity, setEditIntensity] = useState('balanced')
  const [editPedagogicalStyle, setEditPedagogicalStyle] = useState('conceptual')
  const [topicsList, setTopicsList] = useState<string[]>([])

  // Submit Course Generation Request
  const handleStartGeneration = async (forceDuplicate = false) => {
    setErrorMessage(null)
    setDuplicateCourse(null)

    let reqType = materialType
    if (materialType === 'youtube_url' && inputContent.includes('list=')) {
      reqType = 'youtube_playlist'
    }

    try {
      const res = await fetch('/api/generate-course', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          material_type: reqType,
          content: inputContent,
          title: courseTitle,
          force_duplicate: forceDuplicate,
        }),
      })

      if (res.status === 409) {
        const dupData = await res.json()
        setDuplicateCourse({
          existing_course_id: dupData.detail.existing_course_id,
          existing_title: dupData.detail.existing_title,
        })
        return
      }

      if (!res.ok) {
        const errData = await res.json()
        setErrorMessage(errData.detail?.message || 'Failed to start course generation.')
        return
      }

      const data = await res.json()
      setJobId(data.job_id)
      setStep('generating')
    } catch {
      setErrorMessage('Network error initiating course generation.')
    }
  }

  // Poll Job Status during 'generating' step
  useEffect(() => {
    if (step !== 'generating' || !jobId) return

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/generate-course/${jobId}/status`)
        if (res.ok) {
          const data = await res.json()
          setStages(data.stages || [])

          if (data.status === 'draft' && data.preview) {
            setPreview(data.preview)
            setEditTitle(data.preview.title)
            setEditDifficulty(data.preview.difficulty || 'beginner')
            setTopicsList(data.preview.topics || [])
            setStep('preview')
            clearInterval(interval)
          } else if (data.status === 'error') {
            setErrorMessage(data.error || 'Course generation failed.')
            setStep('input')
            clearInterval(interval)
          }
        }
      } catch {
        // continue polling
      }
    }, 1500)

    return () => clearInterval(interval)
  }, [step, jobId])

  // Confirm Draft Course
  const handleConfirmCourse = async () => {
    if (!jobId) return
    try {
      const res = await fetch(`/api/generate-course/${jobId}/confirm`, {
        method: 'POST',
      })
      if (res.ok) {
        const courseSummary = await res.json()
        onCourseReady(courseSummary.id)
      } else {
        setErrorMessage('Failed to confirm and active course.')
      }
    } catch {
      setErrorMessage('Network error confirming course.')
    }
  }

  return (
    <div className="create-page-container" style={{ padding: '32px', maxWidth: '800px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 900, color: 'var(--ink)' }}>✨ AI Course Builder</h1>
        <p style={{ fontSize: '15px', fontWeight: 700, color: 'var(--ink-soft)' }}>
          Transform YouTube videos, playlists, transcripts, or study notes into structured, interactive Patchwork courses.
        </p>
      </div>

      {errorMessage && (
        <div style={{ padding: '12px 16px', borderRadius: '12px', background: '#fee2e2', color: '#991b1b', fontWeight: 700, marginBottom: '20px' }}>
          ⚠️ {errorMessage}
        </div>
      )}

      {/* Duplicate Course Resolution Modal */}
      {duplicateCourse && (
        <div style={{ border: '2px solid var(--yellow-dark)', borderRadius: '16px', background: '#fefce8', padding: '20px', marginBottom: '24px' }}>
          <h3 style={{ fontSize: '18px', fontWeight: 900, color: '#854d0e', marginBottom: '8px' }}>
            Existing Course Found!
          </h3>
          <p style={{ fontSize: '14px', fontWeight: 700, color: '#a16207', marginBottom: '16px' }}>
            You have previously imported this source as <strong>"{duplicateCourse.existing_title}"</strong>.
          </p>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              className="duo-button duo-button-primary"
              onClick={() => onCourseReady(duplicateCourse.existing_course_id)}
            >
              OPEN EXISTING
            </button>
            <button
              className="duo-button duo-button-secondary"
              onClick={() => handleStartGeneration(true)}
            >
              CREATE NEW VERSION
            </button>
          </div>
        </div>
      )}

      {/* STEP 1: INPUT */}
      {step === 'input' && (
        <div className="duo-card" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
            {[
              { type: 'youtube_url', label: 'YouTube URL / Playlist' },
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
                Course Title (Optional):
              </label>
              <input
                type="text"
                placeholder="e.g., Master Quantum Mechanics & Computing"
                value={courseTitle}
                onChange={(e) => setCourseTitle(e.target.value)}
                style={{ width: '100%', padding: '12px', borderRadius: '10px', border: '2px solid var(--line)', fontWeight: 700 }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontWeight: 800, fontSize: '13px', marginBottom: '6px' }}>
                {materialType === 'youtube_url' ? 'YouTube Video or Playlist URL:' : 'Source Content / Transcript:'}
              </label>
              {materialType === 'youtube_url' ? (
                <input
                  type="text"
                  placeholder="https://www.youtube.com/watch?v=... or playlist URL"
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
            </div>
          </div>

          <button
            className="duo-button duo-button-primary"
            onClick={() => handleStartGeneration(false)}
            disabled={!inputContent.trim() && !courseTitle.trim()}
            style={{ width: '100%', padding: '14px', fontSize: '16px' }}
          >
            Generate Interactive Course ✨
          </button>
        </div>
      )}

      {/* STEP 2: GENERATING PROGRESS TRACKER */}
      {step === 'generating' && (
        <div className="duo-card" style={{ padding: '32px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 900, marginBottom: '20px', textAlign: 'center' }}>
            Building Your AI Custom Course…
          </h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
            {stages.map((st) => (
              <div key={st.name} style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '15px', fontWeight: 800 }}>
                <span style={{ fontSize: '18px' }}>
                  {st.state === 'done' ? '✓' : st.state === 'active' ? '🔄' : st.state === 'error' ? '❌' : '○'}
                </span>
                <span style={{ color: st.state === 'done' ? 'var(--green-dark)' : st.state === 'active' ? 'var(--blue-dark)' : 'var(--ink-soft)' }}>
                  {st.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* STEP 3: PREVIEW */}
      {step === 'preview' && preview && (
        <div className="duo-card" style={{ padding: '32px' }}>
          <div style={{ borderBottom: '2px solid var(--line)', paddingBottom: '16px', marginBottom: '20px' }}>
            <span style={{ fontSize: '12px', fontWeight: 900, color: 'var(--blue-dark)', textTransform: 'uppercase' }}>
              COURSE PREVIEW
            </span>
            <h2 style={{ fontSize: '24px', fontWeight: 900, marginTop: '4px' }}>{preview.title}</h2>
            <p style={{ fontSize: '14px', fontWeight: 700, color: 'var(--ink-soft)' }}>
              Source: {preview.source_name}
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px', textAlign: 'center' }}>
            <div style={{ padding: '12px', background: '#f1f5f9', borderRadius: '10px' }}>
              <div style={{ fontSize: '20px', fontWeight: 900 }}>{preview.unit_count}</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#64748b' }}>UNITS</div>
            </div>
            <div style={{ padding: '12px', background: '#f1f5f9', borderRadius: '10px' }}>
              <div style={{ fontSize: '20px', fontWeight: 900 }}>{preview.lesson_count}</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#64748b' }}>LESSONS</div>
            </div>
            <div style={{ padding: '12px', background: '#f1f5f9', borderRadius: '10px' }}>
              <div style={{ fontSize: '20px', fontWeight: 900 }}>{preview.exercise_count}</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#64748b' }}>EXERCISES</div>
            </div>
            <div style={{ padding: '12px', background: '#f1f5f9', borderRadius: '10px' }}>
              <div style={{ fontSize: '20px', fontWeight: 900 }}>{preview.checkpoint_count}</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#64748b' }}>CHECKPOINTS</div>
            </div>
          </div>

          {preview.sequencing_rationale && (
            <div style={{ background: '#f8fafc', padding: '16px', borderRadius: '12px', marginBottom: '24px', border: '1px solid #e2e8f0' }}>
              <h4 style={{ fontSize: '14px', fontWeight: 800, marginBottom: '6px' }}>How this course is structured:</h4>
              <p style={{ fontSize: '13px', fontWeight: 600, color: '#475569' }}>{preview.sequencing_rationale}</p>
            </div>
          )}

          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <button
              className="duo-button duo-button-secondary"
              onClick={() => setStep('editing')}
            >
              EDIT COURSE
            </button>
            <button
              className="duo-button duo-button-primary"
              onClick={handleConfirmCourse}
              style={{ padding: '12px 24px' }}
            >
              START LEARNING 🚀
            </button>
          </div>
        </div>
      )}

      {/* STEP 4: EDITING */}
      {step === 'editing' && preview && (
        <div className="duo-card" style={{ padding: '32px' }}>
          <h2 style={{ fontSize: '22px', fontWeight: 900, marginBottom: '20px' }}>Customize Course Settings</h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
            <div>
              <label style={{ display: 'block', fontWeight: 800, fontSize: '13px', marginBottom: '6px' }}>Title:</label>
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '2px solid var(--line)', fontWeight: 700 }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontWeight: 800, fontSize: '13px', marginBottom: '6px' }}>Difficulty:</label>
              <select
                value={editDifficulty}
                onChange={(e) => setEditDifficulty(e.target.value)}
                style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '2px solid var(--line)', fontWeight: 700 }}
              >
                <option value="beginner">Beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontWeight: 800, fontSize: '13px', marginBottom: '6px' }}>Teaching / Pedagogical Style:</label>
              <select
                value={editPedagogicalStyle}
                onChange={(e) => setEditPedagogicalStyle(e.target.value)}
                style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '2px solid var(--line)', fontWeight: 700 }}
              >
                <option value="conceptual">Conceptual (Intuition-first)</option>
                <option value="mathematical">Mathematical (Rigorous & formal)</option>
                <option value="practical">Practical (Examples-first)</option>
                <option value="visual">Visual (Diagrams & models)</option>
                <option value="socratic">Socratic (Guided discovery)</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <button
              className="duo-button duo-button-secondary"
              onClick={() => setStep('preview')}
            >
              Cancel
            </button>
            <button
              className="duo-button duo-button-primary"
              onClick={handleConfirmCourse}
            >
              SAVE & START 🚀
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
