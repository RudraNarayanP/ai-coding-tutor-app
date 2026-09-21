import { useOutletContext } from 'react-router-dom'
import type { useLearningSession } from './useLearningSession'

/** Everything the learning session exposes to the screen under it. */
export type LearningSession = ReturnType<typeof useLearningSession>

/**
 * The screen side of the session.
 *
 * AppLayout owns the one instance (it owns the chrome that reads XP, hearts and
 * the provider list) and passes it down through the router's own outlet context.
 * That keeps a screen one call away from its data without a second global store
 * that could disagree with the URL.
 */
export function useLearning(): LearningSession {
  return useOutletContext<LearningSession>()
}
