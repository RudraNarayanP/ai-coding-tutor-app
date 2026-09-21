/**
 * ProfileScreen: moved out of App.tsx's tab branches unchanged.
 *
 * Every value comes from the learning session via the router outlet, and
 * every navigation affordance below goes through the router.
 */

import { useLearning } from '../learning/useLearning'

export function ProfileScreen() {
  const {
    hearts,
    level,
    profileStreak,
    unlimitedHearts,
    userProfile,
    view,
    xp,
  } = useLearning()
  return (
  <div className="duo-page-container">
    <div className="duo-profile-view">
      <div className="duo-profile-header">
        <div className="duo-profile-avatar-large">
          {(userProfile?.username || 'P').charAt(0).toUpperCase()}
        </div>
        <div className="duo-profile-meta">
          <h1>{userProfile?.username || 'Profile unavailable'}</h1>
          <p className="duo-profile-handle">
            {userProfile ? userProfile.user_id : 'Server profile has not loaded'}
          </p>
        </div>
      </div>

      <div className="duo-stats-grid">
        <div className="duo-stat-card">
          <div className="duo-stat-card-icon">🔥</div>
          <div>
            <div className="duo-stat-card-val">{profileStreak == null ? '—' : profileStreak}</div>
            <div className="duo-stat-card-lbl">Streak</div>
          </div>
        </div>
        <div className="duo-stat-card">
          <div className="duo-stat-card-icon">⚡</div>
          <div>
            <div className="duo-stat-card-val">{xp} XP</div>
            <div className="duo-stat-card-lbl">Total XP</div>
          </div>
        </div>
        <div className="duo-stat-card">
          <div className="duo-stat-card-icon">❤️</div>
          <div>
            <div className="duo-stat-card-val">{unlimitedHearts ? '∞' : hearts}</div>
            <div className="duo-stat-card-lbl">Hearts</div>
          </div>
        </div>
        <div className="duo-stat-card">
          <div className="duo-stat-card-icon">🏅</div>
          <div>
            <div className="duo-stat-card-val">{level}</div>
            <div className="duo-stat-card-lbl">Level</div>
          </div>
        </div>
      </div>
    </div>
  </div>
  )
}
