import { PatchworkCharacter } from '../components/PatchworkCharacters'
import type { Exercise } from './types'
import { CodeBlock, OptionCards, RichText } from './rich'
import type { RunView } from './types'

export function TeachCard({ exercise }: { exercise: Exercise }) {
  return (
    <div className="lp-teach" data-screen="teach">
      <div className="lp-teach-row">
        <PatchworkCharacter name="patch" state="happy" size={96} />
        <div className="lp-bubble">
          <p>{exercise.speech}</p>
        </div>
      </div>
      {exercise.example ? <CodeBlock code={exercise.example} /> : null}
      {exercise.sourceUrl ? (
        <a className="lp-source" href={exercise.sourceUrl} target="_blank" rel="noreferrer">
          Source
        </a>
      ) : null}
    </div>
  )
}

export function MultipleChoice({
  exercise,
  selected,
  onSelect,
}: {
  exercise: Exercise
  selected: string | string[] | null
  onSelect: (option: string) => void
}) {
  const chosen = Array.isArray(selected) ? selected : selected ? [selected] : []
  return (
    <div className="lp-stack" data-screen="multiple_choice">
      <h2 className="lp-prompt">
        <RichText parts={exercise.prompt} />
      </h2>
      <div className="lp-options" role="group" aria-label="Choices">
        {(exercise.options ?? []).map((option, index) => {
          const pressed = chosen.includes(option)
          return (
            <button
              key={option}
              type="button"
              className={`lp-option${pressed ? ' is-selected' : ''}`}
              aria-pressed={pressed}
              onClick={() => onSelect(option)}
            >
              <span className="lp-option-index" aria-hidden="true">{index + 1}</span>
              <span>{option}</span>
              {pressed ? <span className="lp-option-mark">✓</span> : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function PredictOutput({
  exercise,
  selected,
  onSelect,
}: {
  exercise: Exercise
  selected: string | null
  onSelect: (option: string) => void
}) {
  return (
    <div className="lp-stack" data-screen="predict">
      <h2 className="lp-prompt">
        <RichText parts={exercise.prompt} />
      </h2>
      {exercise.code ? <CodeBlock code={exercise.code} /> : null}
      <OptionCards options={exercise.options ?? []} selected={selected} onSelect={onSelect} name="Predicted output" />
    </div>
  )
}

export function TapToBuild({
  exercise,
  picked,
  onChange,
}: {
  exercise: Exercise
  picked: string[]
  onChange: (next: string[]) => void
}) {
  const used = new Map<string, number>()
  picked.forEach((chip) => used.set(chip, (used.get(chip) ?? 0) + 1))

  return (
    <div className="lp-stack" data-screen="tap_to_build">
      <h2 className="lp-prompt">
        <RichText parts={exercise.prompt} />
      </h2>
      <div className="lp-tray" aria-label="Answer tray">
        {picked.length === 0 ? <span className="lp-tray-empty">Tap chips to build the line</span> : null}
        {picked.map((chip, index) => (
          <button
            key={`${chip}-${index}`}
            type="button"
            className="lp-chip"
            onClick={() => onChange(picked.filter((_, chipIndex) => chipIndex !== index))}
          >
            {chip}
          </button>
        ))}
      </div>
      <div className="lp-bank" aria-label="Code chips">
        {(exercise.chips ?? []).map((chip, index) => {
          const before = (exercise.chips ?? []).slice(0, index).filter((item) => item === chip).length
          const taken = used.get(chip) ?? 0
          const hidden = before < taken
          return (
            <button
              key={`${chip}-${index}`}
              type="button"
              className={`lp-chip${hidden ? ' is-used' : ''}`}
              disabled={hidden}
              onClick={() => onChange([...picked, chip])}
            >
              {chip}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function FillBlank({
  exercise,
  value,
  onChange,
}: {
  exercise: Exercise
  value: string | null
  onChange: (next: string | null) => void
}) {
  const [before, after = ''] = (exercise.code ?? '').split('___')
  return (
    <div className="lp-stack" data-screen="fill_blank">
      <h2 className="lp-prompt">
        <RichText parts={exercise.prompt} />
      </h2>
      <pre className="lp-code">
        <code>
          {before}
          <button type="button" className="lp-blank" onClick={() => onChange(null)}>
            {value ?? '___'}
          </button>
          {after}
        </code>
      </pre>
      <div className="lp-bank" aria-label="Blank choices">
        {(exercise.chips ?? []).map((chip) => (
          <button
            key={chip}
            type="button"
            className={`lp-chip${value === chip ? ' is-selected' : ''}`}
            aria-pressed={value === chip}
            onClick={() => onChange(chip)}
          >
            {chip}
          </button>
        ))}
      </div>
    </div>
  )
}

export function SpotTheBug({
  exercise,
  selected,
  onSelect,
}: {
  exercise: Exercise
  selected: string | null
  onSelect: (line: string) => void
}) {
  return (
    <div className="lp-stack" data-screen="spot_the_bug">
      <h2 className="lp-prompt">
        <RichText parts={exercise.prompt} />
      </h2>
      <div className="lp-code lp-bug" role="group" aria-label="Code lines">
        {(exercise.lines ?? []).map((line, index) => {
          const number = String(index + 1)
          const pressed = selected === number
          return (
            <button
              key={number}
              type="button"
              className={`lp-bug-line${pressed ? ' is-selected' : ''}`}
              aria-pressed={pressed}
              onClick={() => onSelect(number)}
            >
              <span className="lp-gutter-num">{number}</span>
              <span>{line}</span>
              {pressed ? <span className="lp-option-mark">✓</span> : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function WriteCode({
  exercise,
  code,
  onChange,
  run,
}: {
  exercise: Exercise
  code: string
  onChange: (next: string) => void
  run: RunView | null
}) {
  const contentLines = code.split('\n')
  const numberedLines = contentLines[contentLines.length - 1] === '' ? contentLines.slice(0, -1) : contentLines
  const rows = Math.max(6, numberedLines.length)
  return (
    <div className="lp-stack" data-screen="write_code">
      <h2 className="lp-prompt">Your turn!</h2>
      <p className="lp-goal">
        <RichText parts={exercise.prompt} />
      </p>
      {exercise.example ? (
        <div className="lp-example">
          <span>Example</span>
          <pre>{exercise.example}</pre>
        </div>
      ) : null}
      <div className="lp-write-grid">
        <div className="lp-editor">
          <div className="lp-gutter" aria-hidden="true">
            {numberedLines.map((_, index) => (
              <div key={index}>{index + 1}</div>
            ))}
          </div>
          <textarea
            aria-label="Code editor"
            className="lp-textarea"
            wrap="off"
            rows={rows}
            spellCheck={false}
            value={code}
            onChange={(event) => onChange(event.target.value)}
          />
        </div>
        <section className="lp-result" aria-label="Result">
          <h3>Result</h3>
          {!run?.ran ? <p className="lp-empty">Run to see what your code does.</p> : null}
          {run?.errorSummary ? (
            <div className="lp-error-friendly">
              <p>
                <span aria-hidden="true">✗ </span>
                {run.errorSummary}
              </p>
              {run.errorDetail ? (
                <details>
                  <summary>Details</summary>
                  <pre>{run.errorDetail}</pre>
                </details>
              ) : null}
            </div>
          ) : null}
          {run?.ran
            ? run.tests.map((test) => (
                <div key={test.id} className={`lp-test-row${test.passed ? ' is-pass' : ' is-fail'}`}>
                  <span aria-hidden="true">{test.passed ? '✓' : '✗'}</span>
                  <span>{test.label}</span>
                </div>
              ))
            : null}
        </section>
      </div>
    </div>
  )
}
