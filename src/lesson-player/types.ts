export type RichPart = { text: string } | { code: string }

export type ScreenType =
  | 'teach'
  | 'multiple_choice'
  | 'predict'
  | 'tap_to_build'
  | 'fill_blank'
  | 'spot_the_bug'
  | 'write_code'

export type WriteTest =
  | { id: string; label: string; expectStdout: string }
  | { id: string; label: string; expr: string; expectRepr: string }

export type Exercise = {
  id: string
  type: ScreenType
  prompt: RichPart[]
  speech?: string
  example?: string
  code?: string
  lines?: string[]
  options?: string[]
  chips?: string[]
  /** Canonical answer. Write screens are graded by running tests. */
  answer: string | string[]
  explanation: string
  hints: [string, string, string]
  tests?: WriteTest[]
  xp: number
  starter?: string
  sourceUrl?: string
  sourceLabel?: string
  /** When set, the backend grades this screen. The answer key stays on the server. */
  server?: {
    lessonId: string
    exerciseId: string
    sublessonId?: string
    kind: 'choice' | 'order' | 'multi' | 'fill' | 'code'
  }
  multi?: boolean
}

export type PlayerLesson = {
  id: string
  title: string
  unitId: string
  unitTitle: string
  unitColor: string
  sourceUrl?: string
  sourceLabel?: string
  screens: Exercise[]
}

export type TestRow = { id: string; label: string; passed: boolean }

export type RunView = {
  ran: boolean
  errorSummary: string | null
  errorDetail: string | null
  tests: TestRow[]
}
