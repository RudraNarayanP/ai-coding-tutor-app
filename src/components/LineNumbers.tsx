import { useRef } from 'react'

/**
 * Gutter of line numbers that tracks a code buffer.
 *
 * Preserved verbatim from App.tsx during the routing refactor. It was already
 * unused there (the workspaces have their own gutter), and routing did not make
 * it unnecessary — so it lives here instead of being deleted along with the
 * navigation code.
 */
export function LineNumbers({ code }: { code: string }) {
  const contentRef = useRef<HTMLDivElement>(null)
  const lines = code.split('\n')

  return (
    <div className="line-numbers" aria-hidden="true">
      <div ref={contentRef} className="line-numbers-content">
        {lines.map((_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
    </div>
  )
}
