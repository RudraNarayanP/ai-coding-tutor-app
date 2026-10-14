import type { LessonView } from '../api'
import { playerLessons } from './lessons'
import { parseRichLessonText } from '../utils/parseRichLessonText'
import type { Exercise, PlayerLesson, RichPart, ScreenType } from './types'

type RemoteExercise = {
  id: string
  title?: string
  type?: string
  question?: string
  options?: string[]
  pairs?: { left: string; right: string }[]
  starter_code?: string
  hints?: string[]
  xp_reward?: number
  explanation?: string
  micro_explanation?: string
  worked_example?: string
}

type RemoteLesson = {
  id: string
  title: string
  description?: string
  starter_code?: string
  learning_objectives?: string[]
  source?: { url?: string; name?: string } | null
  unit_id?: string
  unit_title?: string
  player_mode?: string
  sublessons?: { id: string; title?: string; exercises?: RemoteExercise[] }[]
}

const COLORS = ['#1cb0f6', '#ce82ff', '#ff9600', '#58cc02', '#ff4b4b', '#ffc800']

function colorFor(id: string): string {
  let hash = 0
  for (const char of id) hash = (hash + char.charCodeAt(0)) % COLORS.length
  return COLORS[hash]
}

function friendlyTitle(title: string): string {
  return title.replace(/^\d+\.\s*/, '').replace(/`([^`]+)`/g, '$1').trim()
}

function oneSentence(value: string): string {
  const clean = value.replace(/```[\s\S]*?```/g, ' ').replace(/`([^`]+)`/g, '$1').replace(/\s+/g, ' ').trim()
  const match = clean.match(/^.*?[.!?](\s|$)/)
  return (match?.[0] ?? clean).trim().slice(0, 160)
}

function partsFrom(value: string): RichPart[] {
  const stripped = value.replace(/```[\s\S]*?```/g, ' ').trim()
  const segments = parseRichLessonText(stripped || 'Read this step.')
  const parts: RichPart[] = []
  for (const segment of segments) {
    if (segment.type === 'code') parts.push({ code: segment.value })
    else if (segment.value.trim()) parts.push({ text: segment.value })
  }
  return parts.length ? parts : [{ text: oneSentence(value) || 'Read this step.' }]
}

function threeHints(hints: string[] | undefined): [string, string, string] {
  const clean = (hints || []).map((hint) => hint.replace(/`([^`]+)`/g, '$1').trim()).filter(Boolean)
  return [
    clean[0] || 'Read the one-line idea.',
    clean[1] || 'Compare each choice with the example.',
    clean[2] || 'Pick the choice that matches the example exactly.',
  ]
}

/** Micro lessons never invent a hint. Missing rungs stay empty so the audit can fail them. */
function exactHints(hints: string[] | undefined): [string, string, string] {
  const clean = (hints || []).map((hint) => hint.replace(/`([^`]+)`/g, '$1').trim())
  return [clean[0] || '', clean[1] || '', clean[2] || '']
}

function codeLines(value: string | undefined): string[] {
  return (value || '').replace(/\n$/, '').split('\n')
}

function teach(id: string, speech: string, example?: string): Exercise {
  const line = oneSentence(speech) || 'Read one idea, then try it.'
  return {
    id,
    type: 'teach',
    prompt: [{ text: line }],
    speech: line,
    example: example?.trim() || undefined,
    answer: '',
    explanation: line,
    hints: threeHints(undefined),
    xp: 0,
  }
}

function fence(question: string): { prompt: string; code?: string } {
  const match = question.match(/```[a-zA-Z]*\n?([\s\S]*?)```/)
  if (!match) return { prompt: question }
  const prompt = question.replace(match[0], '').trim()
  return { prompt: prompt || 'What does this print?', code: match[1].trim() }
}

function mapRecognition(
  exercise: RemoteExercise,
  lessonId: string,
  sublessonId: string | undefined
): Exercise | null {
  const type = (exercise.type || '').toLowerCase()
  const { prompt, code } = fence(exercise.question || exercise.title || 'Choose one.')
  const base = {
    id: exercise.id,
    prompt: partsFrom(prompt),
    explanation: oneSentence(exercise.explanation || exercise.micro_explanation || 'Check the example and try again.'),
    hints: threeHints(exercise.hints),
    xp: exercise.xp_reward || 10,
    answer: '' as string | string[],
    server: {
      lessonId,
      exerciseId: exercise.id,
      sublessonId,
      kind: 'choice' as const,
    },
  }

  if (['mcq', 'true_false', 'debugging', 'identify_error'].includes(type) && exercise.options?.length) {
    return { ...base, type: 'multiple_choice', options: exercise.options.slice(0, 4) }
  }
  if (type === 'short_answer' && exercise.options?.length) {
    return { ...base, type: 'multiple_choice', options: exercise.options.slice(0, 4) }
  }
  if (type === 'output_prediction' && exercise.options?.length) {
    return {
      ...base,
      type: 'predict',
      code: code || exercise.starter_code || exercise.worked_example,
      options: (exercise.options || []).slice(0, 4),
    }
  }
  if (type === 'ordering' && exercise.options?.length) {
    return {
      ...base,
      type: 'tap_to_build',
      chips: exercise.options,
      server: { ...base.server, kind: 'order' },
    }
  }
  if (type === 'select_multiple' && exercise.options?.length) {
    return {
      ...base,
      type: 'multiple_choice',
      multi: true,
      options: exercise.options.slice(0, 4),
      server: { ...base.server, kind: 'multi' },
    }
  }
  if (type === 'matching' && exercise.pairs?.length) {
    const pair = exercise.pairs[0]
    const options = Array.from(new Set(exercise.pairs.map((item) => item.right))).slice(0, 4)
    return {
      id: exercise.id,
      type: 'multiple_choice',
      prompt: partsFrom(`What matches ${pair.left}?`),
      options,
      answer: pair.right,
      explanation: oneSentence(exercise.explanation || `${pair.left} matches ${pair.right}.`),
      hints: threeHints(exercise.hints),
      xp: exercise.xp_reward || 10,
    }
  }
  if (type === 'short_answer') {
    return teach(exercise.id, prompt)
  }
  return null
}

function mapWrite(
  exercise: RemoteExercise,
  lessonId: string,
  sublessonId: string | undefined
): Exercise {
  const { prompt } = fence(exercise.question || exercise.title || 'Finish the program.')
  return {
    id: exercise.id,
    type: 'write_code',
    prompt: partsFrom(oneSentence(prompt) || 'Finish the program.'),
    example: exercise.worked_example?.trim() || undefined,
    starter: exercise.starter_code || '',
    answer: '',
    explanation: oneSentence(exercise.explanation || exercise.micro_explanation || 'Run it and read the result row.'),
    hints: threeHints(exercise.hints),
    xp: exercise.xp_reward || 10,
    server: { lessonId, exerciseId: exercise.id, sublessonId, kind: 'code' },
  }
}

const WRITE_TYPES = new Set(['code', 'tiny_coding', 'identify_mistake', 'fill_blank', 'code_completion'])
const MICRO_WRITE_TYPES = new Set(['code', 'tiny_coding'])

function isWrite(exercise: RemoteExercise): boolean {
  return WRITE_TYPES.has((exercise.type || '').toLowerCase())
}

function shell(lesson: RemoteLesson, screens: Exercise[]): PlayerLesson {
  const title = friendlyTitle(lesson.title)
  return {
    id: lesson.id,
    title,
    unitId: lesson.unit_id || 'course',
    unitTitle: lesson.unit_title ? friendlyTitle(lesson.unit_title) : 'Lesson',
    unitColor: colorFor(lesson.unit_id || lesson.id),
    sourceUrl: lesson.source?.url,
    sourceLabel: lesson.source?.name ? 'Source' : undefined,
    screens,
  }
}

function mapMicro(exercise: RemoteExercise, lesson: RemoteLesson, sublessonId: string | undefined): Exercise | null {
  const type = (exercise.type || '').toLowerCase()
  const { prompt, code } = fence(exercise.question || exercise.title || '')
  const hints = exactHints(exercise.hints)
  const explanation = oneSentence(exercise.explanation || exercise.micro_explanation || '')
  const server = {
    lessonId: lesson.id,
    exerciseId: exercise.id,
    sublessonId,
    kind: 'choice' as const,
  }

  if (type === 'teach') {
    const speech = oneSentence(exercise.question || exercise.title || '')
    return {
      id: exercise.id,
      type: 'teach',
      prompt: [{ text: speech }],
      speech,
      example: exercise.worked_example?.trim() || undefined,
      answer: '',
      explanation: explanation || speech,
      hints,
      xp: 0,
      sourceUrl: lesson.source?.url,
      sourceLabel: lesson.source?.url ? 'Source' : undefined,
    }
  }

  if (MICRO_WRITE_TYPES.has(type)) {
    return {
      id: exercise.id,
      type: 'write_code',
      prompt: partsFrom(oneSentence(prompt) || 'Finish the program.'),
      example: exercise.worked_example?.trim() || undefined,
      starter: exercise.starter_code || '',
      answer: '',
      explanation: explanation || 'Run it and read the result row.',
      hints,
      xp: exercise.xp_reward || 10,
      server: { ...server, kind: 'code' },
    }
  }

  if (type === 'fill_blank' || type === 'code_completion') {
    return {
      id: exercise.id,
      type: 'fill_blank',
      prompt: partsFrom(prompt),
      code: exercise.starter_code || code,
      chips: exercise.options || [],
      answer: '',
      explanation,
      hints,
      xp: exercise.xp_reward || 10,
      server: { ...server, kind: 'fill' },
    }
  }

  if (type === 'debugging' || type === 'identify_error') {
    return {
      id: exercise.id,
      type: 'spot_the_bug',
      prompt: partsFrom(prompt),
      lines: codeLines(exercise.starter_code || code),
      answer: '',
      explanation,
      hints,
      xp: exercise.xp_reward || 10,
      server,
    }
  }

  if (type === 'ordering') {
    return {
      id: exercise.id,
      type: 'tap_to_build',
      prompt: partsFrom(prompt),
      chips: exercise.options || [],
      answer: '',
      explanation,
      hints,
      xp: exercise.xp_reward || 10,
      server: { ...server, kind: 'order' },
    }
  }

  if (type === 'output_prediction') {
    return {
      id: exercise.id,
      type: 'predict',
      prompt: partsFrom(prompt),
      code: code || exercise.starter_code || exercise.worked_example,
      options: (exercise.options || []).slice(0, 4),
      answer: '',
      explanation,
      hints,
      xp: exercise.xp_reward || 10,
      server,
    }
  }

  if (['mcq', 'true_false', 'short_answer'].includes(type) && exercise.options?.length) {
    return {
      id: exercise.id,
      type: 'multiple_choice',
      prompt: partsFrom(prompt),
      options: exercise.options.slice(0, 4),
      answer: '',
      explanation,
      hints,
      xp: exercise.xp_reward || 10,
      server,
    }
  }

  if (type === 'select_multiple' && exercise.options?.length) {
    return {
      id: exercise.id,
      type: 'multiple_choice',
      multi: true,
      prompt: partsFrom(prompt),
      options: exercise.options.slice(0, 4),
      answer: '',
      explanation,
      hints,
      xp: exercise.xp_reward || 10,
      server: { ...server, kind: 'multi' },
    }
  }

  return null
}

/** Strict screen list. No padding, no generic hints, editor only for real code exercises. */
export function adaptMicroLesson(lesson: RemoteLesson): PlayerLesson {
  const recognition: Exercise[] = []
  const writes: Exercise[] = []
  for (const sub of lesson.sublessons || []) {
    for (const exercise of sub.exercises || []) {
      const mapped = mapMicro(exercise, lesson, sub.id)
      if (!mapped) continue
      if (mapped.type === 'write_code') writes.push(mapped)
      else recognition.push(mapped)
    }
  }
  return shell(lesson, [...recognition, ...writes])
}

/** Turn a fetched lesson from any course into the same screen sequence. */
export function adaptFetchedLesson(lesson: RemoteLesson): PlayerLesson {
  const script = playerLessons[lesson.id]
  if (script) return script
  if ((lesson.player_mode || '').toLowerCase() === 'micro') return adaptMicroLesson(lesson)

  const title = friendlyTitle(lesson.title)
  const objective = oneSentence(lesson.learning_objectives?.[0] || lesson.description || title)
  const example = (lesson.starter_code || '').trim().slice(0, 280)
  const recognition: Exercise[] = []
  const writes: Exercise[] = []

  for (const sub of lesson.sublessons || []) {
    for (const exercise of sub.exercises || []) {
      if (isWrite(exercise)) writes.push(mapWrite(exercise, lesson.id, sub.id))
      else {
        const mapped = mapRecognition(exercise, lesson.id, sub.id)
        if (mapped) recognition.push(mapped)
      }
    }
  }

  const earlyWrites = writes.slice(0, Math.max(0, writes.length - 2))
  const lateWrites = writes.slice(Math.max(0, writes.length - 2))
  for (const extra of earlyWrites) {
    recognition.push(teach(`${extra.id}-read`, extra.explanation, extra.starter?.slice(0, 280)))
  }

  const screens: Exercise[] = [teach(`${lesson.id}-idea`, objective, example || undefined), ...recognition]

  const ideas = [
    ...(lesson.learning_objectives || []),
    lesson.description || '',
  ]
    .map(oneSentence)
    .filter((line, index, all) => line && all.indexOf(line) === index)

  let ideaIndex = 0
  while (screens.length < 5) {
    const line = ideas[ideaIndex] || objective
    screens.push(teach(`${lesson.id}-idea-${screens.length}`, line, ideaIndex === 0 ? example || undefined : undefined))
    ideaIndex += 1
    if (ideaIndex > ideas.length + 2) break
  }

  if (lateWrites.length === 0 && (lesson.starter_code || '').trim()) {
    lateWrites.push({
      id: `${lesson.id}-write`,
      type: 'write_code' as ScreenType,
      prompt: partsFrom(objective || 'Finish the program.'),
      starter: lesson.starter_code,
      answer: '',
      explanation: objective || 'Run it and read the result row.',
      hints: threeHints(undefined),
      xp: 10,
      server: { lessonId: lesson.id, exerciseId: '', kind: 'code' },
    })
  }

  return shell(lesson, [...screens, ...lateWrites])
}

export function resolvePlayerLesson(lesson: LessonView | RemoteLesson): PlayerLesson {
  return playerLessons[lesson.id] ?? adaptFetchedLesson(lesson)
}
