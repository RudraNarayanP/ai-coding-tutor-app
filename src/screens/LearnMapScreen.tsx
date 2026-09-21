/**
 * The learning map: a course's path of lesson nodes, or one unit of it.
 *
 * Three URLs share this screen because they are the same view at three depths —
 * `/learn` (the stored course), `/course/:courseId` and
 * `/course/:courseId/unit/:unitId`. That is what lets browser Back walk
 * lesson → unit → course → home instead of falling out of the app.
 */

import { useLearning } from '../learning/useLearning'
import { LearnPath } from '../components/duo/LearnPath'
import { groupLessonsIntoUnits } from '../components/duo/courseDisplay'
import { NotFoundScreen } from './NotFoundScreen'

export function LearnMapScreen() {
  const {
    activeCourse,
    courseIsSwitching,
    courseIsUnknown,
    isLoadingLesson,
    lesson,
    openLesson,
    openUnit,
    params,
    safeLessons,
    setIsGuidebookOpen,
  } = useLearning()

  if (courseIsUnknown) {
    // `/course/something-that-is-not-a-course` — say so, in the app's own
    // vocabulary, rather than showing the previous course under a new URL.
    return <NotFoundScreen />
  }

  if (courseIsSwitching) return <div className="duo-page-container" />

  const unitId = params.unitId ?? null
  if (unitId && !groupLessonsIntoUnits(safeLessons).some((unit) => unit.id === unitId)) {
    return <NotFoundScreen />
  }

  return (
    <div className="duo-page-container">
      <LearnPath
        lessons={safeLessons}
        activeLessonId={lesson?.id ?? null}
        isLoadingLesson={isLoadingLesson}
        onSelectLesson={(item) => openLesson(item.id)}
        onOpenGuidebook={() => setIsGuidebookOpen(true)}
        unitFilter={unitId}
        // The course a unit belongs to comes from the resolved course, not the
        // URL: `/learn` carries no course id at all, and building the link from
        // the missing param produced `/course/undefined/unit/…`. Only offer the
        // link once the course is known, and only on the whole-course map —
        // inside a unit the banner goes back to being a heading.
        onOpenUnit={
          unitId || !activeCourse
            ? undefined
            : (id) => openUnit(activeCourse.id, id)
        }
      />
    </div>
  )
}
