/**
 * The practice hub, at `/practice` and `/practice/:activity`.
 *
 * Which of the six cards is open is a place the learner can be, so it lives in
 * the URL; which lesson they picked inside a card stayed local state, because
 * that is a choice about what to do next rather than somewhere to be.
 */

import { useLearning } from '../learning/useLearning'
import { PracticeHub, type PracticeActivityId } from '../components/duo/PracticeHub'
import { NotFoundScreen } from './NotFoundScreen'

export function PracticeScreen() {
  const {
    completedMaterialIds,
    goBack,
    handleCompleteMaterial,
    isLoadingLesson,
    materials,
    mistakes,
    openLesson,
    practiceActivity,
    practiceActivityIsValid,
    safeLessons,
    selectPracticeActivity,
    setIsGuidebookOpen,
    selectedLanguage,
  } = useLearning()

  if (!practiceActivityIsValid) return <NotFoundScreen />

  return (
    <div className="duo-page-container duo-page-container--practice">
      <PracticeHub
        lessons={safeLessons}
        isLoadingLesson={isLoadingLesson}
        onOpenLesson={(item) => openLesson(item.id)}
        onOpenGuidebook={() => setIsGuidebookOpen(true)}
        onBack={goBack}
        materials={materials}
        completedMaterialIds={completedMaterialIds}
        onCompleteMaterial={handleCompleteMaterial}
        mistakes={mistakes}
        language={selectedLanguage}
        activity={(practiceActivity ?? undefined) as PracticeActivityId | undefined}
        onActivityChange={selectPracticeActivity}
      />
    </div>
  )
}
