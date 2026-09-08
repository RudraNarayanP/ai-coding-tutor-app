import React from 'react'
import { SYNTAX_REFERENCE, SyntaxEntry } from '../utils/syntaxReference'

interface GuidebookPanelProps {
  isOpen: boolean
  onClose: () => void
  language: string
  conceptTitle?: string
}

export const GuidebookPanel: React.FC<GuidebookPanelProps> = ({
  isOpen,
  onClose,
  language,
  conceptTitle,
}) => {
  if (!isOpen) return null

  const entries: SyntaxEntry[] = SYNTAX_REFERENCE[language.toLowerCase()] || SYNTAX_REFERENCE['python']

  return (
    <div
      className="guidebook-drawer-overlay"
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        left: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.4)',
        zIndex: 2000,
        display: 'flex',
        justifyContent: 'flex-end',
      }}
      onClick={onClose}
    >
      <div
        className="guidebook-drawer"
        style={{
          width: '360px',
          height: '100%',
          backgroundColor: '#ffffff',
          boxShadow: '-4px 0 16px rgba(0, 0, 0, 0.15)',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Contextual Guidebook"
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h2 style={{ fontSize: '20px', fontWeight: 900, color: 'var(--ink)' }}>📖 Guidebook</h2>
            <p style={{ fontSize: '13px', fontWeight: 700, color: 'var(--ink-soft)' }}>
              {language.toUpperCase()} {conceptTitle ? `• ${conceptTitle}` : 'Syntax Reference'}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close Guidebook"
            style={{
              background: 'none',
              border: 'none',
              fontSize: '24px',
              fontWeight: 900,
              cursor: 'pointer',
              color: 'var(--ink-soft)',
            }}
          >
            ×
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {entries.map((item, idx) => (
            <div
              key={idx}
              style={{
                border: '2px solid var(--line)',
                borderRadius: '12px',
                padding: '16px',
                backgroundColor: '#f8fafc',
              }}
            >
              <h3 style={{ fontSize: '15px', fontWeight: 800, marginBottom: '6px', color: 'var(--blue-dark)' }}>
                {item.concept}
              </h3>
              <p style={{ fontSize: '13px', fontWeight: 600, marginBottom: '10px', color: '#475569' }}>
                {item.description}
              </p>
              <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '6px', color: '#64748b' }}>SYNTAX:</div>
              <pre
                style={{
                  backgroundColor: '#1e293b',
                  color: '#f8fafc',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontFamily: 'monospace',
                  overflowX: 'auto',
                  marginBottom: '10px',
                }}
              >
                <code>{item.syntax}</code>
              </pre>
              <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '6px', color: '#64748b' }}>EXAMPLE:</div>
              <pre
                style={{
                  backgroundColor: '#0f172a',
                  color: '#38bdf8',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontFamily: 'monospace',
                  overflowX: 'auto',
                }}
              >
                <code>{item.example}</code>
              </pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
