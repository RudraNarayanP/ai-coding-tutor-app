/**
 * Patchwork's route table.
 *
 * This file used to hold the application's whole navigation system: seven tab
 * names, an `isLessonActive` flag and a lesson object, all guessing where the
 * learner was against a URL that never changed. It now holds a map from URL to
 * screen and nothing else.
 *
 *   browser URL → router → screen → learning session → exercise components
 *
 * AppLayout is a pathless route, so its sidebar, header and modals stay mounted
 * across navigation while the screen underneath is whatever the URL asked for.
 *
 * The default export wraps its own BrowserRouter rather than main.tsx doing it.
 * That is so the existing `render(<App />)` suites keep working untouched: the
 * router is part of the app. A test that wants a chosen starting URL renders
 * AppRoutes inside a MemoryRouter instead — see src/routing.test.tsx.
 */

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './AppLayout'
import { reviewPath } from './learning/routes'
import { CoursesScreen } from './screens/CoursesScreen'
import { CreateScreen } from './screens/CreateScreen'
import { LearnMapScreen } from './screens/LearnMapScreen'
import { LeaderboardsScreen } from './screens/LeaderboardsScreen'
import { LessonScreen } from './screens/LessonScreen'
import { NotFoundScreen } from './screens/NotFoundScreen'
import { PracticeScreen } from './screens/PracticeScreen'
import { ProfileScreen } from './screens/ProfileScreen'
import { QuestsScreen } from './screens/QuestsScreen'

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        {/* `/` is the home screen. It redirects rather than duplicating the map,
            and `replace` keeps the dead `/` from becoming a history entry the
            learner has to back out of. */}
        <Route index element={<Navigate to="/learn" replace />} />

        {/* The learning map. `/learn` resolves the stored course; `/course/:id`
            names it explicitly, which is what makes the URL shareable and lets
            Back walk map → course → unit. */}
        <Route path="learn" element={<LearnMapScreen />} />
        <Route path="course/:courseId" element={<LearnMapScreen />} />
        <Route path="course/:courseId/unit/:unitId" element={<LearnMapScreen />} />

        {/* A lesson, and one step inside it. `/lesson/:id` shows whatever the
            backend says is next; the step route pins a step this learner has
            already been served, so refresh and Back land exactly there. */}
        <Route path="lesson/:lessonId" element={<LessonScreen />} />
        <Route path="lesson/:lessonId/exercise/:exerciseId" element={<LessonScreen />} />

        <Route path="courses" element={<CoursesScreen />} />
        <Route path="practice" element={<PracticeScreen />} />
        <Route path="practice/:activity" element={<PracticeScreen />} />
        {/* The review session is PracticeHub's mistake queue. `/review` is the
            shareable name for it, redirected onto the real activity id. */}
        <Route path="review" element={<Navigate to={reviewPath()} replace />} />

        <Route path="quests" element={<QuestsScreen />} />
        <Route path="create" element={<CreateScreen />} />
        <Route path="leaderboards" element={<LeaderboardsScreen />} />
        <Route path="profile" element={<ProfileScreen />} />

        <Route path="*" element={<NotFoundScreen />} />
      </Route>
    </Routes>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}

export default App
