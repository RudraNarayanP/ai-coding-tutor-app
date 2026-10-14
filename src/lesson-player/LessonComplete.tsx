import { PatchworkCharacter } from '../components/PatchworkCharacters'

export function LessonComplete({
  title,
  xp,
  accuracy,
  seconds,
  streak,
  perfect,
  sourceUrl,
  onContinue,
}: {
  title: string
  xp: number
  accuracy: number
  seconds: number
  streak: number
  perfect: boolean
  sourceUrl?: string
  onContinue: () => void
}) {
  const minutes = Math.floor(seconds / 60)
  const remain = seconds % 60
  const clock = `${minutes}:${String(remain).padStart(2, '0')}`
  return (
    <div className="lp-complete">
      <div className="lp-confetti" aria-hidden="true">
        {Array.from({ length: 18 }, (_, index) => (
          <span key={index} style={{ left: `${(index * 53) % 100}%`, animationDelay: `${index * 0.05}s` }} />
        ))}
      </div>
      <PatchworkCharacter name="patch" state="celebrate" size={120} />
      <h2>Lesson complete</h2>
      <p className="lp-complete-title">{title}</p>
      {perfect ? <p className="lp-perfect">Perfect! +5 bonus XP</p> : null}
      <ul className="lp-stats">
        <li>
          <span>XP</span>
          <strong>{xp}</strong>
        </li>
        <li>
          <span>Accuracy</span>
          <strong>{accuracy}%</strong>
        </li>
        <li>
          <span>Time</span>
          <strong>{clock}</strong>
        </li>
        <li>
          <span>Streak</span>
          <strong>🔥 {streak}</strong>
        </li>
      </ul>
      {sourceUrl ? (
        <a className="lp-source" href={sourceUrl} target="_blank" rel="noreferrer">
          Source
        </a>
      ) : null}
      <button type="button" className="lp-btn lp-btn-primary lp-check" onClick={onContinue}>
        Continue
      </button>
    </div>
  )
}
