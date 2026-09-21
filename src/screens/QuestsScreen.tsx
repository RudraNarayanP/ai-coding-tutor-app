/**
 * QuestsScreen: moved out of App.tsx's tab branches unchanged.
 *
 * Every value comes from the learning session via the router outlet, and
 * every navigation affordance below goes through the router.
 */

import { useLearning } from '../learning/useLearning'
import { QuestsPage } from '../components/duo/QuestsPage'

export function QuestsScreen() {
  const {
    completedCount,
    courses,
    level,
    safeLessons,
    selectedLanguage,
    xp,
  } = useLearning()
  return (
  <div className="duo-page-container">
    <QuestsPage
      courses={courses}
      selectedLanguage={selectedLanguage}
      completedCount={completedCount}
      totalCount={safeLessons.length}
      xp={xp}
      level={level}
    />
  </div>
  )
}
