import { describe, expect, it } from 'vitest'
import { fileIcon, languageExt, slugFilename } from './languageFile'

describe('languageExt', () => {
  it('accepts both language tags and course ids', () => {
    expect(languageExt('python')).toBe('py')
    expect(languageExt('javascript')).toBe('js')
    expect(languageExt('typescript')).toBe('ts')
    expect(languageExt('java')).toBe('java')
    expect(languageExt('cpp')).toBe('cpp')
    expect(languageExt('sql')).toBe('sql')
    // Courses taught in Python must not fall through to a wrong extension.
    expect(languageExt('dsa')).toBe('py')
    expect(languageExt('ml')).toBe('py')
    expect(languageExt('ml-math')).toBe('py')
    expect(languageExt('ai')).toBe('py')
    expect(languageExt('fullstack')).toBe('py')
  })

  it('defaults safely instead of inventing a language', () => {
    expect(languageExt(undefined)).toBe('py')
    expect(languageExt('klingon')).toBe('py')
    expect(languageExt('JAVA')).toBe('java')
  })
})

describe('slugFilename', () => {
  it('slugifies the lesson title with the right extension', () => {
    expect(slugFilename('DOM & Event Fundamentals', 'javascript')).toBe(
      'dom_event_fundamentals.js'
    )
    expect(slugFilename('Step 2: Hash Maps', 'python')).toBe('hash_maps.py')
  })

  it('falls back to a usable name for an empty title', () => {
    expect(slugFilename('', 'sql')).toBe('exercise.sql')
    expect(slugFilename('', 'sql', 'practice')).toBe('practice.sql')
  })

  it('keeps long titles inside the tab', () => {
    const name = slugFilename('A'.repeat(80), 'python')
    expect(name.length).toBeLessThanOrEqual(31) // 28 + ".py"
  })
})

describe('fileIcon', () => {
  it('matches the file type instead of always showing a snake', () => {
    expect(fileIcon('create_button.js')).not.toBe('🐍')
    expect(fileIcon('sum.py')).toBe('🐍')
    expect(fileIcon('guidebook.md')).toBe('📘')
    expect(fileIcon('mystery')).toBe('📄')
  })
})
