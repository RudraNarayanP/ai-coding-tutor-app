import type { RichPart } from './types'

export function RichText({ parts }: { parts: RichPart[] }) {
  return (
    <>
      {parts.map((part, index) =>
        'code' in part ? (
          <code key={index} className="lp-inline-code">
            {part.code}
          </code>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </>
  )
}

/** Renders authored hint text. Backticks become chips and never show raw. */
export function HintText({ value }: { value: string }) {
  const bits = value.split(/`([^`]+)`/g)
  return (
    <>
      {bits.map((bit, index) =>
        index % 2 === 1 ? (
          <code key={index} className="lp-inline-code">
            {bit}
          </code>
        ) : (
          <span key={index}>{bit}</span>
        ),
      )}
    </>
  )
}

export function CodeBlock({ code }: { code: string }) {
  return (
    <pre className="lp-code" tabIndex={0}>
      <code>{code}</code>
    </pre>
  )
}

export function OptionCards({
  options,
  selected,
  onSelect,
  name,
}: {
  options: string[]
  selected: string | null
  onSelect: (option: string) => void
  name: string
}) {
  return (
    <div className="lp-options" role="group" aria-label={name}>
      {options.map((option, index) => {
        const pressed = selected === option
        return (
          <button
            key={option}
            type="button"
            className={`lp-option${pressed ? ' is-selected' : ''}`}
            aria-pressed={pressed}
            onClick={() => onSelect(option)}
          >
            <span className="lp-option-index" aria-hidden="true">
              {index + 1}
            </span>
            <span>{option}</span>
            {pressed ? <span className="lp-option-mark">✓</span> : null}
          </button>
        )
      })}
    </div>
  )
}
