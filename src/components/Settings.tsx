import { useState, useEffect, useCallback } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

type ProviderId = 'ollama' | 'openai' | 'anthropic' | 'openrouter' | 'gemini'

interface ProviderInfo {
  id: string
  name: string
  has_key: boolean
  key_masked: string | null
  model: string
  configured: boolean
  available: boolean
  health_status: {
    available: boolean
    reason: string | null
    error: string | null
  } | null
  setup_instructions: string | null
  error: string | null
}

interface SettingsResponse {
  providers: ProviderInfo[]
  current_provider: string
}

interface ValidationResult {
  valid: boolean
  error: string | null
  provider: string
  key_masked: string | null
}

// ─── Provider Icons ────────────────────────────────────────────────────────────

const ProviderIcon = ({ provider }: { provider: string }) => {
  const icons: Record<string, string> = {
    ollama: '🦙',
    openai: '🤖',
    anthropic: '🧠',
    openrouter: '🔀',
    gemini: '💎',
  }
  return <span style={{ fontSize: '1.5rem' }}>{icons[provider] || '⚙️'}</span>
}

// ─── Status Badge ──────────────────────────────────────────────────────────────

const StatusBadge = ({ available, configured }: { available: boolean; configured: boolean }) => {
  if (available) {
    return <span className="status-badge status-available">✓ Online</span>
  }
  if (configured) {
    return <span className="status-badge status-configured">⚠ Offline</span>
  }
  return <span className="status-badge status-unconfigured">○ Not Set</span>
}

// ─── Settings Component ─────────────────────────────────────────────────────────

interface SettingsProps {
  isOpen: boolean
  onClose: () => void
  backendUrl: string
  onBackendUrlChange: (url: string) => void
  onProviderChange?: () => void
  // Gameplay preferences (Duolingo-style hearts)
  unlimitedHearts?: boolean
  hearts?: number
  onToggleUnlimitedHearts?: (value: boolean) => void
  onRestoreHearts?: () => void
  gamification?: {
    xp: number
    level: number
    streak: number
    currentDay: number
    dailyXp: number
    dailyGoal: number
  }
}

export default function Settings({
  isOpen,
  onClose,
  backendUrl,
  onBackendUrlChange,
  onProviderChange,
  unlimitedHearts = false,
  hearts = 5,
  onToggleUnlimitedHearts,
  onRestoreHearts,
  gamification,
}: SettingsProps) {
  const [settings, setSettings] = useState<SettingsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeProvider, setActiveProvider] = useState<string | null>(null)
  
  // API Key input state
  const [apiKey, setApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [model, setModel] = useState('')
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  // Fetch settings on mount
  const fetchSettings = useCallback(async () => {
    if (!isOpen) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${backendUrl}/api/settings`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json() as SettingsResponse
      setSettings(data)
    } catch (err) {
      setError('Failed to load settings. Is the backend running?')
      console.error('Settings fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [backendUrl, isOpen])

  useEffect(() => {
    fetchSettings()
  }, [fetchSettings])

  // Reset form when switching providers
  useEffect(() => {
    if (activeProvider) {
      const provider = settings?.providers.find(p => p.id === activeProvider)
      if (provider) {
        setModel(provider.model || '')
        setApiKey('')
        setValidationResult(null)
        setSaveMessage(null)
      }
    }
  }, [activeProvider, settings])

  // Validate API key
  const handleValidate = async () => {
    if (!apiKey.trim() || !activeProvider) return
    
    setValidationResult(null)
    try {
      const response = await fetch(`${backendUrl}/api/settings/providers/${activeProvider}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, model: model || null }),
      })
      const result = await response.json() as ValidationResult
      setValidationResult(result)
    } catch (err) {
      setValidationResult({
        valid: false,
        error: 'Validation request failed',
        provider: activeProvider,
        key_masked: null,
      })
    }
  }

  // Save API key
  const handleSave = async () => {
    if (!apiKey.trim() || !activeProvider) return
    
    setSaving(true)
    setSaveMessage(null)
    try {
      const response = await fetch(`${backendUrl}/api/settings/providers/${activeProvider}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, model: model || null }),
      })
      
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail?.message || 'Save failed')
      }
      
      const result = await response.json()
      setSaveMessage(result.message)
      setApiKey('')
      setValidationResult(null)
      
      // Refresh settings
      await fetchSettings()
      onProviderChange?.()
    } catch (err) {
      setSaveMessage(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setSaving(false)
    }
  }

  // Delete API key
  const handleDelete = async (providerId: string) => {
    if (!confirm(`Are you sure you want to remove the API key for ${providerId}?`)) return
    
    try {
      await fetch(`${backendUrl}/api/settings/providers/${providerId}/key`, {
        method: 'DELETE',
      })
      await fetchSettings()
      onProviderChange?.()
      if (activeProvider === providerId) {
        setActiveProvider(null)
      }
    } catch (err) {
      console.error('Delete error:', err)
    }
  }

  // Set provider as active
  const handleSelectProvider = async (providerId: string) => {
    try {
      const response = await fetch(`${backendUrl}/api/ai/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerId }),
      })
      if (response.ok) {
        await fetchSettings()
        onProviderChange?.()
      }
    } catch (err) {
      console.error('Select provider error:', err)
    }
  }

  if (!isOpen) return null

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <h2>⚙️ API Settings</h2>
          <button className="settings-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="settings-content">
          {/* Backend URL Setting */}
          <div className="settings-section">
            <h3>🌐 Backend Connection</h3>
            <div className="setting-row">
              <label htmlFor="backend-url">Backend URL:</label>
              <input
                id="backend-url"
                type="text"
                value={backendUrl}
                onChange={e => onBackendUrlChange(e.target.value)}
                placeholder="http://localhost:8000"
                style={{ flex: 1, padding: '8px', borderRadius: '6px', border: '1px solid #ccc' }}
              />
            </div>
            <p className="setting-hint">Change this if your backend runs on a different port.</p>
          </div>

          {/* Gameplay / Hearts Preferences */}
          <div className="settings-section">
            <h3>🎮 Gameplay — Hearts</h3>
            <p className="setting-hint">
              Every mistake costs one heart — just like Duolingo. Lose all hearts and you
              can keep practicing but progress is paused until they restore.
            </p>

            <div className="setting-row">
              <label htmlFor="unlimited-hearts">Unlimited Hearts:</label>
              <button
                id="unlimited-hearts"
                type="button"
                className={`btn-${unlimitedHearts ? 'primary' : 'secondary'}`}
                onClick={() => onToggleUnlimitedHearts?.(!unlimitedHearts)}
                style={{ borderRadius: '8px' }}
              >
                {unlimitedHearts ? '✅ ON — no hearts lost' : 'Off — hearts can be lost'}
              </button>
            </div>

            <div className="setting-row" style={{ marginTop: '8px' }}>
              <label htmlFor="hearts-count">Hearts:</label>
              <span id="hearts-count" style={{ fontWeight: 700 }}>
                {unlimitedHearts ? '∞ (Unlimited)' : `${'❤️ '.repeat(Math.max(0, Math.min(hearts, 5)))}${hearts}/5`}
              </span>
              {!unlimitedHearts && (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => onRestoreHearts?.()}
                  style={{ marginLeft: '8px', padding: '4px 10px', borderRadius: '8px' }}
                >
                  +1 Heart
                </button>
              )}
            </div>

            {gamification && (
              <div className="current-config" style={{ marginTop: '12px' }}>
                <div className="config-item">
                  <span className="config-label">Progression</span>
                  <span className="config-value">Day {gamification.currentDay}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">Streak</span>
                  <span className="config-value">{gamification.streak} days</span>
                </div>
                <div className="config-item">
                  <span className="config-label">XP Today</span>
                  <span className="config-value">{gamification.dailyXp} / {gamification.dailyGoal}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">Total XP</span>
                  <span className="config-value">{gamification.xp} (Level {gamification.level})</span>
                </div>
              </div>
            )}
          </div>

          {/* Provider Selection */}
          {loading ? (
            <div className="settings-loading">Loading providers...</div>
          ) : error ? (
            <div className="settings-error">{error}</div>
          ) : settings ? (
            <>
              <div className="settings-section">
                <h3>🤖 AI Providers</h3>
                <p className="setting-hint">Select a provider to configure. Keys are encrypted and stored securely.</p>
                
                <div className="provider-grid">
                  {settings.providers.map(provider => (
                    <div
                      key={provider.id}
                      className={`provider-card ${activeProvider === provider.id ? 'active' : ''}`}
                      onClick={() => setActiveProvider(provider.id)}
                    >
                      <div className="provider-card-header">
                        <ProviderIcon provider={provider.id} />
                        <div className="provider-card-info">
                          <strong>{provider.name}</strong>
                          <StatusBadge available={provider.available} configured={provider.configured} />
                        </div>
                      </div>
                      {provider.has_key && (
                        <div className="provider-key-info">
                          Key: <code>{provider.key_masked}</code>
                        </div>
                      )}
                      {provider.health_status?.reason && !provider.available && (
                        <div className="provider-error">{provider.health_status.reason}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Provider Configuration Panel */}
              {activeProvider && (
                <div className="settings-section provider-config">
                  <h3>Configure {settings.providers.find(p => p.id === activeProvider)?.name}</h3>
                  
                  {settings.providers.find(p => p.id === activeProvider)?.setup_instructions && (
                    <div className="setup-instructions">
                      💡 {settings.providers.find(p => p.id === activeProvider)?.setup_instructions}
                    </div>
                  )}

                  <div className="setting-row">
                    <label htmlFor="api-key">API Key:</label>
                    <div className="api-key-input">
                      <input
                        id="api-key"
                        type={showApiKey ? 'text' : 'password'}
                        value={apiKey}
                        onChange={e => {
                          setApiKey(e.target.value)
                          setValidationResult(null)
                        }}
                        placeholder="Enter your API key..."
                        style={{ flex: 1, padding: '8px', borderRadius: '6px', border: '1px solid #ccc' }}
                      />
                      <button
                        type="button"
                        className="show-key-btn"
                        onClick={() => setShowApiKey(!showApiKey)}
                        aria-label={showApiKey ? 'Hide key' : 'Show key'}
                      >
                        {showApiKey ? '🙈' : '👁️'}
                      </button>
                    </div>
                  </div>

                  <div className="setting-row">
                    <label htmlFor="model">Model:</label>
                    <input
                      id="model"
                      type="text"
                      value={model}
                      onChange={e => setModel(e.target.value)}
                      placeholder="Leave empty for default"
                      style={{ flex: 1, padding: '8px', borderRadius: '6px', border: '1px solid #ccc' }}
                    />
                  </div>

                  {/* Validation Result */}
                  {validationResult && (
                    <div className={`validation-result ${validationResult.valid ? 'valid' : 'invalid'}`}>
                      {validationResult.valid ? (
                        <>✓ Key validated! Masked: <code>{validationResult.key_masked}</code></>
                      ) : (
                        <>✗ {validationResult.error}</>
                      )}
                    </div>
                  )}

                  {/* Save Message */}
                  {saveMessage && (
                    <div className={`save-message ${saveMessage.startsWith('Error') ? 'error' : 'success'}`}>
                      {saveMessage}
                    </div>
                  )}

                  <div className="config-actions">
                    <button
                      className="btn-secondary"
                      onClick={handleValidate}
                      disabled={!apiKey.trim() || saving}
                    >
                      🔍 Test Key
                    </button>
                    <button
                      className="btn-primary"
                      onClick={handleSave}
                      disabled={!apiKey.trim() || saving}
                    >
                      {saving ? '⏳ Saving...' : '💾 Save'}
                    </button>
                    {activeProvider && settings.current_provider !== activeProvider && (
                      <button
                        className="btn-secondary"
                        onClick={() => handleSelectProvider(activeProvider)}
                        disabled={saving}
                      >
                        ⚡ Set as Active Provider
                      </button>
                    )}
                    {settings.providers.find(p => p.id === activeProvider)?.has_key && (
                      <button
                        className="btn-danger"
                        onClick={() => handleDelete(activeProvider)}
                        disabled={saving}
                      >
                        🗑️ Remove Key
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Current Provider Info */}
              <div className="settings-section">
                <h3>📊 Current Configuration</h3>
                <div className="current-config">
                  <div className="config-item">
                    <span className="config-label">Active Provider:</span>
                    <span className="config-value">{settings.current_provider}</span>
                  </div>

                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>

      <style>{`
        .settings-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 20px;
        }

        .settings-modal {
          background: white;
          border-radius: 16px;
          width: 100%;
          max-width: 700px;
          max-height: 90vh;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
        }

        .settings-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px 24px;
          border-bottom: 1px solid #e5e5e5;
          background: #f8f9fa;
        }

        .settings-header h2 {
          margin: 0;
          font-size: 1.25rem;
          color: #333;
        }

        .settings-close {
          background: none;
          border: none;
          font-size: 2rem;
          cursor: pointer;
          color: #666;
          padding: 0;
          line-height: 1;
        }

        .settings-close:hover {
          color: #333;
        }

        .settings-content {
          padding: 24px;
          overflow-y: auto;
          flex: 1;
        }

        .settings-section {
          margin-bottom: 28px;
        }

        .settings-section h3 {
          margin: 0 0 12px 0;
          font-size: 1.1rem;
          color: #333;
        }

        .setting-row {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 12px;
        }

        .setting-row label {
          min-width: 100px;
          font-weight: 500;
          color: #555;
        }

        .setting-hint {
          font-size: 0.85rem;
          color: #888;
          margin: 8px 0;
        }

        .provider-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 12px;
          margin-top: 12px;
        }

        .provider-card {
          border: 2px solid #e5e5e5;
          border-radius: 12px;
          padding: 16px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .provider-card:hover {
          border-color: #58a6ff;
          background: #f8f9fa;
        }

        .provider-card.active {
          border-color: #58a6ff;
          background: #e6f3ff;
        }

        .provider-card-header {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .provider-card-info {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .provider-card-info strong {
          font-size: 0.95rem;
        }

        .provider-key-info {
          margin-top: 8px;
          font-size: 0.8rem;
          color: #666;
        }

        .provider-key-info code {
          background: #f0f0f0;
          padding: 2px 6px;
          border-radius: 4px;
        }

        .provider-error {
          margin-top: 8px;
          font-size: 0.8rem;
          color: #d32f2f;
        }

        .status-badge {
          display: inline-block;
          font-size: 0.75rem;
          padding: 2px 8px;
          border-radius: 12px;
          font-weight: 500;
        }

        .status-available {
          background: #e6f4ea;
          color: #1e7e34;
        }

        .status-configured {
          background: #fff3e0;
          color: #e65100;
        }

        .status-unconfigured {
          background: #f5f5f5;
          color: #757575;
        }

        .setup-instructions {
          background: #e3f2fd;
          border-radius: 8px;
          padding: 12px 16px;
          margin-bottom: 16px;
          font-size: 0.9rem;
          color: #1565c0;
        }

        .api-key-input {
          display: flex;
          gap: 8px;
          flex: 1;
        }

        .show-key-btn {
          background: #f5f5f5;
          border: 1px solid #ccc;
          border-radius: 6px;
          padding: 8px 12px;
          cursor: pointer;
        }

        .show-key-btn:hover {
          background: #e5e5e5;
        }

        .validation-result {
          padding: 12px 16px;
          border-radius: 8px;
          margin: 12px 0;
          font-size: 0.9rem;
        }

        .validation-result.valid {
          background: #e6f4ea;
          color: #1e7e34;
        }

        .validation-result.invalid {
          background: #ffebee;
          color: #c62828;
        }

        .validation-result code {
          background: rgba(0,0,0,0.1);
          padding: 2px 6px;
          border-radius: 4px;
        }

        .save-message {
          padding: 12px 16px;
          border-radius: 8px;
          margin: 12px 0;
          font-size: 0.9rem;
        }

        .save-message.success {
          background: #e6f4ea;
          color: #1e7e34;
        }

        .save-message.error {
          background: #ffebee;
          color: #c62828;
        }

        .config-actions {
          display: flex;
          gap: 12px;
          margin-top: 16px;
        }

        .btn-primary, .btn-secondary, .btn-danger {
          padding: 10px 20px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          border: none;
        }

        .btn-primary {
          background: #58cc02;
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          background: #46a002;
        }

        .btn-secondary {
          background: #f0f0f0;
          color: #333;
        }

        .btn-secondary:hover:not(:disabled) {
          background: #e0e0e0;
        }

        .btn-danger {
          background: #ff5252;
          color: white;
        }

        .btn-danger:hover:not(:disabled) {
          background: #d32f2f;
        }

        .btn-primary:disabled, .btn-secondary:disabled, .btn-danger:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .current-config {
          background: #f8f9fa;
          border-radius: 8px;
          padding: 16px;
        }

        .config-item {
          display: flex;
          justify-content: space-between;
          padding: 8px 0;
          border-bottom: 1px solid #e5e5e5;
        }

        .config-item:last-child {
          border-bottom: none;
        }

        .config-label {
          color: #666;
        }

        .config-value {
          font-weight: 600;
          color: #333;
        }

        .settings-loading, .settings-error {
          text-align: center;
          padding: 40px;
          color: #666;
        }

        .settings-error {
          color: #d32f2f;
        }

        .provider-config {
          background: #fafafa;
          border-radius: 12px;
          padding: 20px;
          border: 1px solid #e5e5e5;
        }
      `}</style>
    </div>
  )
}
