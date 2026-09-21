/**
 * CoursesScreen: moved out of App.tsx's tab branches unchanged.
 *
 * Every value comes from the learning session via the router outlet, and
 * every navigation affordance below goes through the router.
 */

import { useLearning } from '../learning/useLearning'
import { CoursesPage } from '../components/duo/CoursesPage'

export function CoursesScreen() {
  const {
    courses,
    handleCourseChange,
    selectedLanguage,
  } = useLearning()
  return (
  <div className="duo-page-container">
    <CoursesPage
      courses={courses}
      selectedLanguage={selectedLanguage}
      onSelectCourse={handleCourseChange}
    />
  </div>
  )
}
