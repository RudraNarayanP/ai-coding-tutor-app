/**
 * LeaderboardsScreen: moved out of App.tsx's tab branches unchanged.
 *
 * Every value comes from the learning session via the router outlet, and
 * every navigation affordance below goes through the router.
 */

import { useLearning } from '../learning/useLearning'

export function LeaderboardsScreen() {
  const {
    gamification,
    hearts,
    leaderboardEntries,
    level,
    maxHearts,
    profileStreak,
    selectedLanguage,
    unlimitedHearts,
    view,
    xp,
  } = useLearning()
  return (
    <div className="duo-page-container">
    <div className="duo-leaderboard-view">
      <div className="duo-league-banner">
        <div className="duo-league-shield">LB</div>
        <div className="duo-league-details">
          <h2>Leaderboard</h2>
          <p>
            {leaderboardEntries.find((e) => e.is_current_user)
              ? `Your rank: #${leaderboardEntries.find((e) => e.is_current_user)!.rank} · ${xp} XP · Level ${level}`
              : `Level ${level} · ${xp} XP from course progression`}
          </p>
        </div>
      </div>
      <div className="duo-rank-list">
        {Array.isArray(leaderboardEntries) && leaderboardEntries.length > 0 ? (
          leaderboardEntries.map((entry) => (
            <div
              key={entry.user_id}
              className={`duo-rank-item ${entry.is_current_user ? 'user-self' : ''}`}
            >
              <div className={`duo-rank-num ${entry.rank <= 3 ? `top-${entry.rank}` : ''}`}>
                {entry.rank}
              </div>
              <div className="duo-user-avatar-circle">
                {entry.username ? entry.username.replace('[Demo] ', '').charAt(0).toUpperCase() : 'U'}
              </div>
              <div className="duo-rank-name" style={{ flex: 1, fontWeight: entry.is_current_user ? 800 : 600 }}>
                {entry.username}{entry.is_current_user ? ' (You)' : ''}{entry.is_demo ? ' · demo' : ''}
              </div>
              <div className="duo-rank-xp" style={{ fontWeight: 800 }}>
                {entry.xp} XP
              </div>
            </div>
          ))
        ) : (
          <p className="duo-empty-note">No leaderboard entries were returned by the server.</p>
        )}
      </div>
      <div className="duo-widget-card" style={{ marginTop: '16px' }}>
        <div className="duo-widget-title">
          <span>Your stats</span>
          <span className="duo-widget-link">TRACK: {selectedLanguage.toUpperCase()}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px', fontSize: '14px', fontWeight: 800 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Streak (profile)</span>
            <span>{profileStreak == null ? 'Unavailable' : `${profileStreak} days`}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Total XP (progression)</span>
            <span>{xp}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Level</span>
            <span>{level}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Hearts</span>
            <span>{unlimitedHearts ? 'Unlimited' : `${hearts} / ${gamification.maxHearts || 5}`}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
  )
}
