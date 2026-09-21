/**
 * The settings panel survives whatever `/api/settings` actually returns.
 *
 * These cases exist because the panel used to cast the JSON body to its own type
 * and then read `settings.providers.map(...)` — so a body without a provider list
 * threw during render and took the whole app down, and a malformed row threw too.
 * A broken backend must be reported, not crashed through.
 */

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Settings from './Settings'

const provider = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  name: id === 'ollama' ? 'Ollama (Local)' : 'OpenAI',
  has_key: false,
  key_masked: null,
  model: 'gpt-4o-mini',
  configured: true,
  available: true,
  health_status: null,
  setup_instructions: null,
  error: null,
  ...over,
})

function mockSettings(body: unknown, ok = true, status = 200) {
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({
      ok,
      status,
      json: () => Promise.resolve(body),
    })
  ))
}

function openPanel() {
  return render(
    <Settings
      isOpen
      onClose={() => {}}
      backendUrl=""
      onBackendUrlChange={() => {}}
      unlimitedHearts={false}
      hearts={5}
      gamification={{ xp: 0, level: 1, streak: 0, currentDay: 1, dailyXp: 0, dailyGoal: 30 }}
    />
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Settings with a damaged payload', () => {
  it('reports a body with no provider list instead of throwing', async () => {
    mockSettings({})
    openPanel()

    await waitFor(() =>
      expect(screen.getByText(/returned settings without a provider list/i)).toBeInTheDocument()
    )
    // The rest of the panel is still there: a bad AI-settings body must not cost
    // the learner their gameplay controls.
    expect(screen.getByText(/Gameplay — Hearts/i)).toBeInTheDocument()
    expect(screen.queryByText(/Configure/i)).not.toBeInTheDocument()
  })

  it('drops rows it cannot render and keeps the usable ones', async () => {
    // A null, a bare string, an object with no id, then one real row.
    mockSettings({ providers: [null, 'ollama', { name: 'No Id' }, provider('openai')], current_provider: 'openai' })
    openPanel()

    await waitFor(() => expect(screen.getByText('OpenAI')).toBeInTheDocument())
    expect(screen.queryByText('No Id')).not.toBeInTheDocument()
    expect(screen.queryByText(/returned settings without a provider list/i)).not.toBeInTheDocument()
  })

  it('labels a nameless row with its id rather than an empty card', async () => {
    mockSettings({ providers: [provider('gemini', { name: '' })], current_provider: 'gemini' })
    const { container } = openPanel()

    // Scoped to the card, because the id also appears in the "Active Provider"
    // readout below; what matters is that the tile is not blank.
    await waitFor(() =>
      expect(container.querySelector('.provider-card-info strong')?.textContent).toBe('gemini')
    )
  })

  it('says so when the backend genuinely has no providers', async () => {
    mockSettings({ providers: [], current_provider: '' })
    openPanel()

    await waitFor(() =>
      expect(screen.getByText(/reported no providers/i)).toBeInTheDocument()
    )
  })

  it('keeps the unreachable-backend message for a failed request', async () => {
    mockSettings({}, false, 500)
    openPanel()

    await waitFor(() =>
      expect(screen.getByText(/Failed to load settings\. Is the backend running\?/i)).toBeInTheDocument()
    )
  })

  it('still renders a well-formed provider list', async () => {
    mockSettings({
      providers: [provider('ollama'), provider('openai')],
      current_provider: 'ollama',
    })
    openPanel()

    await waitFor(() => expect(screen.getByText('Ollama (Local)')).toBeInTheDocument())
    expect(screen.getByText('OpenAI')).toBeInTheDocument()
  })
})
