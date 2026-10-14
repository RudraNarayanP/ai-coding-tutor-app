import { describe, expect, it } from 'vitest'
import { adaptFetchedLesson } from './resolveLesson'

const javaLesson = {
  id: 'java-variables-step-1',
  title: '1. Hello Java & String Variables',
  description: 'Create a class Solution with a static method getLanguage() returning Java.',
  starter_code: 'public class Solution {\n    public static String getLanguage() {\n        return null;\n    }\n}\n',
  learning_objectives: ['Declare a Java class and return a String literal'],
  unit_id: 'java-basics',
  unit_title: 'Java Basics & Variables',
  sublessons: [
    {
      id: 'java-var-sub-1',
      exercises: [
        {
          id: 'java-ex-1a',
          type: 'mcq',
          question: 'Which keyword sends a value back to the caller of a Java method?',
          options: ['yield', 'output', 'return', 'send'],
          hints: ['Methods hand a value back.', 'It is a Java keyword.', 'The word is return.'],
          explanation: 'In Java, return sends a result back from a method.',
        },
        {
          id: 'java-ex-1b',
          type: 'fill_blank',
          question: 'Complete the return statement so the method gives back the language name.',
          starter_code: 'return ___;',
          hints: ['Java strings use double quotes.', 'The language name is Java.', 'return "Java";'],
          explanation: 'Java String literals use double quotes.',
        },
      ],
    },
  ],
}

describe('adaptFetchedLesson for every course', () => {
  it('uses the real question and keeps the editor off the first five screens', () => {
    const lesson = adaptFetchedLesson(javaLesson)
    expect(lesson.title).toBe('Hello Java & String Variables')
    expect(lesson.unitTitle).toBe('Java Basics & Variables')
    expect(lesson.screens.length).toBeGreaterThanOrEqual(6)
    lesson.screens.slice(0, 5).forEach((screen) => {
      expect(screen.type).not.toBe('write_code')
    })
    const mcq = lesson.screens.find((screen) => screen.id === 'java-ex-1a')
    expect(mcq?.type).toBe('multiple_choice')
    expect(mcq?.options).toContain('return')
    expect(mcq?.server?.lessonId).toBe('java-variables-step-1')
    expect(JSON.stringify(mcq?.prompt)).not.toContain('`')
    const write = lesson.screens.filter((screen) => screen.type === 'write_code')
    expect(write.length).toBe(1)
    expect(write[0].id).toBe('java-ex-1b')
    expect(write[0].starter).toContain('___')
    expect(lesson.screens.some((screen) => JSON.stringify(screen).includes('You will not type yet'))).toBe(false)
  })

  it('keeps a legacy lesson on the padded adapter', () => {
    const lesson = adaptFetchedLesson({
      ...javaLesson,
      player_mode: 'legacy',
      learning_objectives: ['Declare a Java class and return a String literal'],
    })
    expect(lesson.screens.filter((screen) => screen.type === 'teach').length).toBeGreaterThan(1)
    expect(lesson.screens.some((screen) => screen.hints.includes('Read the one-line idea.'))).toBe(true)
  })

  it('maps a micro lesson without padding, generic hints, or an early editor', () => {
    const lesson = adaptFetchedLesson({
      id: 'variables-step-1',
      title: '1. Store text in a name',
      player_mode: 'micro',
      source: { url: 'https://docs.python.org/3/tutorial/introduction.html', name: 'Python docs' },
      sublessons: [
        {
          id: 'vars',
          exercises: [
            {
              id: 'teach-1',
              type: 'teach',
              question: 'One equals sign stores a value in a name.',
              worked_example: 'language = "Python"',
              hints: ['A name can hold text.', 'The store happens on one line.', 'language = "Python"'],
              explanation: 'One equals sign stores a value in a name.',
            },
            {
              id: 'fill-1',
              type: 'fill_blank',
              question: 'Fill the symbol that stores the text.',
              starter_code: 'language ___ "Python"',
              options: ['=', '==', ':=', '->'],
              hints: ['The blank is the store symbol.', 'A comparison uses two of them.', '='],
              explanation: 'One equals sign stores the text in the name.',
            },
            {
              id: 'bug-1',
              type: 'debugging',
              question: 'This should print Python. Tap the broken line.',
              starter_code: 'language == "Python"\nprint(language)\n',
              hints: ['The print is fine if the name exists.', 'The first line compares.', 'Line 1 should store.'],
              explanation: 'Line 1 compares instead of storing.',
            },
            {
              id: 'write-1',
              type: 'code',
              question: 'Store the text, then print the name.',
              starter_code: 'language = ___\nprint(language)\n',
              hints: ['The blank is the text.', 'Quotes go around the letters.', 'language = "Python"'],
              explanation: 'Print shows the text that was stored.',
            },
          ],
        },
      ],
    })
    expect(lesson.screens.map((screen) => screen.type)).toEqual([
      'teach',
      'fill_blank',
      'spot_the_bug',
      'write_code',
    ])
    expect(lesson.screens[0].speech).toBe('One equals sign stores a value in a name.')
    expect(lesson.screens[0].sourceUrl).toContain('docs.python.org')
    expect(lesson.screens[1].type).toBe('fill_blank')
    expect(lesson.screens[1].server?.kind).toBe('fill')
    expect(lesson.screens[2].lines).toEqual(['language == "Python"', 'print(language)'])
    expect(lesson.screens.some((screen) => screen.hints.includes('Read the one-line idea.'))).toBe(false)
    expect(JSON.stringify(lesson.screens)).not.toContain('`')
    expect(lesson.screens.findIndex((screen) => screen.type === 'write_code')).toBe(3)
  })

  it('still serves the hand-authored boolean lesson', () => {
    const lesson = adaptFetchedLesson({
      id: 'booleans-step-3',
      title: '4. Meet the not Operator',
      description: 'ignored',
    })
    expect(lesson.title).toBe('Flip it with not')
    expect(lesson.screens[0].type).toBe('teach')
    expect(lesson.screens.at(-1)?.type).toBe('write_code')
  })
})
