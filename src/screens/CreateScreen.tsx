/**
 * The guided-course builder, at `/create`.
 *
 * CreatePage owns its own input → workspace swap internally, which is one screen
 * rather than two destinations, so it stays as it was. `onCourseReady` is wired to
 * the router now: CreatePage never calls it (it is a compatibility leftover), but
 * if it ever does, the learner should land on the new course's URL.
 */

import { useLearning } from '../learning/useLearning'
import { CreatePage } from '../components/CreatePage'

export function CreateScreen() {
  const { handleCourseChange } = useLearning()
  return (
    <CreatePage
      onCourseReady={async (cid) => {
        handleCourseChange(cid)
      }}
    />
  )
}
