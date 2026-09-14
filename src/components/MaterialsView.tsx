import React, { useState } from 'react'
import type { Material, MaterialCompletionResult } from '../api'

interface MaterialsViewProps {
  materials: Material[]
  completedMaterialIds: string[]
  onCompleteMaterial: (id: string, user_answer?: string) => Promise<MaterialCompletionResult | null>
}

export const MaterialsView: React.FC<MaterialsViewProps> = ({
  materials,
  completedMaterialIds,
  onCompleteMaterial,
}) => {
  const [filterStage, setFilterStage] = useState<string>('all')
  const [selectedAnswers, setSelectedAnswers] = useState<Record<string, string>>({})
  const [feedback, setFeedback] = useState<Record<string, { passed: boolean; message: string }>>({})
  const [submittingId, setSubmittingId] = useState<string | null>(null)

  const completedSet = new Set(completedMaterialIds)

  const filteredMaterials = materials.filter((m) => {
    if (filterStage === 'all') return true
    if (filterStage === 'visualize') return m.is_visualizer || m.recommended_stage === 'visualize'
    if (filterStage === 'practice') return m.recommended_stage === 'practice' || m.recommended_stage === 'try'
    if (filterStage === 'build') return m.is_project || m.recommended_stage === 'build'
    if (filterStage === 'reference') return m.is_reference || m.recommended_stage === 'reference' || m.recommended_stage === 'learn'
    if (filterStage === 'challenge') return m.is_challenge || m.recommended_stage === 'challenge'
    return true
  })

  const handleCheckCompanion = async (m: Material) => {
    const ans = selectedAnswers[m.id]
    if (!ans) return
    setSubmittingId(m.id)
    const res = await onCompleteMaterial(m.id, ans)
    setSubmittingId(null)
    if (res) {
      setFeedback((prev) => ({
        ...prev,
        [m.id]: { passed: res.passed, message: res.feedback },
      }))
    }
  }

  return (
    <div className="duo-materials-view" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 900, color: 'var(--ink)' }}>Curated Learning Resources</h2>
        <p style={{ fontSize: '15px', color: 'var(--ink-soft)', fontWeight: 600 }}>
          Interactive visualizers, official references, and real-world tools matched to your current course.
        </p>
      </div>

      {/* Stage Filter Tabs */}
      <div className="duo-char-tabs" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        {[
          { id: 'all', label: 'All Resources' },
          { id: 'visualize', label: '👀 Visualizers' },
          { id: 'practice', label: '⚡ Practice' },
          { id: 'build', label: '🛠 Projects' },
          { id: 'reference', label: '📖 References' },
          { id: 'challenge', label: '🏆 Challenges' },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`duo-button ${filterStage === tab.id ? 'duo-button-primary' : 'duo-button-secondary'}`}
            style={{ padding: '8px 14px', fontSize: '14px' }}
            onClick={() => setFilterStage(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Material Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
        {filteredMaterials.map((m) => {
          const isDone = completedSet.has(m.id)
          const fb = feedback[m.id]
          const selectedAns = selectedAnswers[m.id]

          return (
            <div
              key={m.id}
              className="duo-hero-card"
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                padding: '20px',
                borderRadius: '16px',
                border: isDone ? '2px solid var(--green, #22c55e)' : '2px solid var(--line)',
                background: 'var(--bg-card, #ffffff)',
                gap: '16px',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                  <span
                    style={{
                      fontSize: '12px',
                      fontWeight: 800,
                      padding: '4px 10px',
                      borderRadius: '12px',
                      background: 'var(--bg-soft, #f1f5f9)',
                      color: 'var(--ink-soft)',
                      textTransform: 'uppercase',
                    }}
                  >
                    {m.category} • {m.estimated_minutes} min
                  </span>
                  {isDone && (
                    <span style={{ fontSize: '13px', fontWeight: 800, color: 'var(--green, #22c55e)' }}>
                      ✓ Completed (+{m.xp_reward} XP)
                    </span>
                  )}
                </div>

                <h3 style={{ fontSize: '18px', fontWeight: 800, color: 'var(--ink)' }}>{m.title}</h3>
                <p style={{ fontSize: '14px', color: 'var(--ink-soft)', lineHeight: 1.4 }}>{m.description}</p>
              </div>

              {/* Action row & Companion check */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: 'auto' }}>
                <a
                  href={m.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="duo-button duo-button-secondary"
                  style={{ textDecoration: 'none', textAlign: 'center', fontSize: '14px', padding: '10px 16px' }}
                >
                  Open Resource ↗ ({m.source_domain || 'External'})
                </a>

                {/* Companion activity if present */}
                {m.companion_question && (
                  <div
                    style={{
                      background: 'var(--bg-soft, #f8fafc)',
                      padding: '12px',
                      borderRadius: '12px',
                      border: '1px solid var(--line)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                    }}
                  >
                    <div style={{ fontSize: '13px', fontWeight: 800, color: 'var(--ink)' }}>
                      Companion Check (+{m.xp_reward} XP):
                    </div>
                    <p style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>
                      {m.companion_question.question}
                    </p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {m.companion_question.options.map((opt) => (
                        <button
                          key={opt}
                          type="button"
                          disabled={isDone}
                          className={`exercise-option-btn ${selectedAns === opt ? 'selected' : ''}`}
                          style={{ fontSize: '13px', padding: '8px 12px', textAlign: 'left' }}
                          onClick={() => setSelectedAnswers((prev) => ({ ...prev, [m.id]: opt }))}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>

                    {!isDone && (
                      <button
                        type="button"
                        className="duo-button duo-button-primary"
                        style={{ fontSize: '13px', padding: '8px 14px', marginTop: '4px' }}
                        disabled={!selectedAns || submittingId === m.id}
                        onClick={() => handleCheckCompanion(m)}
                      >
                        {submittingId === m.id ? 'Checking…' : `Check & Claim +${m.xp_reward} XP ⚡`}
                      </button>
                    )}

                    {fb && (
                      <div
                        style={{
                          fontSize: '13px',
                          fontWeight: 700,
                          color: fb.passed ? 'var(--green, #22c55e)' : 'var(--red, #ef4444)',
                          marginTop: '4px',
                        }}
                      >
                        {fb.message}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
