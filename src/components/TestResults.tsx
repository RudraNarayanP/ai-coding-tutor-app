import React from 'react'
import type { TestResult } from '../api'

interface TestResultsProps {
  tests: TestResult[]
  passed: boolean
  completed: boolean
}

// ─── TestResults ─────────────────────────────────────────────────────────────
// Renders the test-result region. Accessible contract (asserted by tests):
//   <section aria-label="Test results"> containing a status badge and one row
//   per test with a pass/fail icon (img role, name "Passed"/"Failed") and an
//   "opt" badge for non-required tests.

export const TestResults: React.FC<TestResultsProps> = ({ tests, passed, completed }) => {
  const requiredTests = tests.filter((t) => t.required)
  const failedRequired = requiredTests.filter((t) => !t.passed).length
  const allPassed = passed && failedRequired === 0

  const statusText = completed
    ? 'Lesson complete!'
    : allPassed
      ? `All ${tests.length} tests passed`
      : `${failedRequired} of ${requiredTests.length} required failed`

  return (
    <section className="test-results" aria-label="Test results" role="region">
      <div className={`test-results-badge ${allPassed ? 'is-pass' : 'is-fail'}`}>
        {allPassed ? '✓' : '✗'} {statusText}
      </div>
      <ul className="test-results-list">
        {tests.map((test) => (
          <li
            key={test.name}
            className={`test-row ${test.passed ? 'is-pass' : 'is-fail'}`}
          >
            <span
              role="img"
              aria-label={test.passed ? 'Passed' : 'Failed'}
              className="test-row-icon"
            >
              {test.passed ? '✓' : '✗'}
            </span>
            <span className="test-row-name">{test.name}</span>
            {!test.required && <span className="test-row-opt">opt</span>}
            {test.description && <span className="test-row-desc">{test.description}</span>}
            {!test.passed && test.error && <span className="test-row-error">{test.error}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}