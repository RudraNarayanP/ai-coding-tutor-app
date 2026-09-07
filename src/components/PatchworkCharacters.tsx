import React from 'react'

export type CharacterName = 'patch' | 'nova' | 'byte' | 'bug'
export type CharacterState = 'idle' | 'happy' | 'celebrate' | 'thinking' | 'confused' | 'encouraging'

interface CharacterProps {
  name?: CharacterName
  state?: CharacterState
  size?: number
  speech?: string
}

export const PatchworkCharacter: React.FC<CharacterProps> = ({
  name = 'patch',
  state = 'idle',
  size = 80,
  speech,
}) => {
  const getAvatarSvg = () => {
    if (name === 'nova') {
      return (
        <svg width={size} height={size} viewBox="0 0 100 100" className={`patch-char state-${state}`}>
          <circle cx="50" cy="50" r="42" fill="#1cb0f6" stroke="#1899d6" strokeWidth="6" />
          {/* Glasses */}
          <rect x="25" y="38" width="22" height="16" rx="4" fill="#ffffff" stroke="#0f172a" strokeWidth="3" />
          <rect x="53" y="38" width="22" height="16" rx="4" fill="#ffffff" stroke="#0f172a" strokeWidth="3" />
          <line x1="47" y1="46" x2="53" y2="46" stroke="#0f172a" strokeWidth="3" />
          {/* Eyes */}
          <circle cx="36" cy="46" r="4" fill="#0f172a" />
          <circle cx="64" cy="46" r="4" fill="#0f172a" />
          {/* Smile */}
          {state === 'celebrate' || state === 'happy' ? (
            <path d="M 35 65 Q 50 80 65 65" fill="none" stroke="#ffffff" strokeWidth="5" strokeLinecap="round" />
          ) : (
            <path d="M 38 68 Q 50 75 62 68" fill="none" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" />
          )}
        </svg>
      )
    }

    if (name === 'byte') {
      return (
        <svg width={size} height={size} viewBox="0 0 100 100" className={`patch-char state-${state}`}>
          <rect x="15" y="18" width="70" height="64" rx="14" fill="#0f172a" stroke="#ce82ff" strokeWidth="6" />
          {/* Antenna */}
          <line x1="50" y1="18" x2="50" y2="6" stroke="#ce82ff" strokeWidth="4" />
          <circle cx="50" cy="5" r="5" fill="#ff9600" />
          {/* Eyes / Visor */}
          <rect x="26" y="34" width="48" height="18" rx="8" fill="#ce82ff" />
          <circle cx="38" cy="43" r="4" fill="#0f172a" />
          <circle cx="62" cy="43" r="4" fill="#0f172a" />
          {/* Mouth */}
          <path d="M 38 65 L 62 65" stroke="#ce82ff" strokeWidth="4" strokeLinecap="round" />
        </svg>
      )
    }

    if (name === 'bug') {
      return (
        <svg width={size} height={size} viewBox="0 0 100 100" className={`patch-char state-${state}`}>
          <circle cx="50" cy="52" r="38" fill="#ff9600" stroke="#ea2b2b" strokeWidth="5" />
          {/* Antennas */}
          <path d="M 35 20 Q 25 5 18 12" fill="none" stroke="#ea2b2b" strokeWidth="4" strokeLinecap="round" />
          <path d="M 65 20 Q 75 5 82 12" fill="none" stroke="#ea2b2b" strokeWidth="4" strokeLinecap="round" />
          {/* Big friendly eyes */}
          <circle cx="36" cy="45" r="9" fill="#ffffff" />
          <circle cx="64" cy="45" r="9" fill="#ffffff" />
          <circle cx="38" cy="45" r="4" fill="#0f172a" />
          <circle cx="62" cy="45" r="4" fill="#0f172a" />
          {/* Playful grin */}
          <path d="M 36 68 Q 50 80 64 68" fill="none" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" />
        </svg>
      )
    }

    // Default PATCH Mascot
    return (
      <svg width={size} height={size} viewBox="0 0 100 100" className={`patch-char state-${state}`}>
        <circle cx="50" cy="50" r="42" fill="#58cc02" stroke="#46a302" strokeWidth="6" />
        {/* Headphones */}
        <path d="M 12 50 A 38 38 0 0 1 88 50" fill="none" stroke="#ce82ff" strokeWidth="8" strokeLinecap="round" />
        <rect x="8" y="42" width="12" height="22" rx="6" fill="#ce82ff" />
        <rect x="80" y="42" width="12" height="22" rx="6" fill="#ce82ff" />
        {/* Eyes */}
        <circle cx="36" cy="46" r="8" fill="#ffffff" />
        <circle cx="64" cy="46" r="8" fill="#ffffff" />
        <circle cx="38" cy="46" r="4" fill="#0f172a" />
        <circle cx="62" cy="46" r="4" fill="#0f172a" />
        {/* Beak / Mouth */}
        <polygon points="50,54 42,62 58,62" fill="#ff9600" />
      </svg>
    )
  }

  return (
    <div className="patch-character-wrapper" style={{ display: 'inline-flex', alignItems: 'center', gap: '12px' }}>
      <div className="patch-char-svg-box">{getAvatarSvg()}</div>
      {speech && (
        <div className="patch-speech-bubble">
          <span>{speech}</span>
        </div>
      )}
    </div>
  )
}
