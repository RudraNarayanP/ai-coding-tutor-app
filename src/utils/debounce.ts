/** Lightweight debounce for UI write paths (drafts, autosave coalescing). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function debounce<T extends (...args: any[]) => void>(fn: T, waitMs: number): T & { cancel: () => void; flush: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastArgs: Parameters<T> | null = null

  const wrapped = ((...args: Parameters<T>) => {
    lastArgs = args
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      const pending = lastArgs
      lastArgs = null
      if (pending) fn(...pending)
    }, waitMs)
  }) as T & { cancel: () => void; flush: () => void }

  wrapped.cancel = () => {
    if (timer) clearTimeout(timer)
    timer = null
    lastArgs = null
  }

  wrapped.flush = () => {
    if (!timer || !lastArgs) {
      wrapped.cancel()
      return
    }
    const pending = lastArgs
    wrapped.cancel()
    fn(...pending)
  }

  return wrapped
}
