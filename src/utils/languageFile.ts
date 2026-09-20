/**
 * One place that decides what a learner's file is called.
 *
 * Every editor surface (lesson workspace, inline exercise panel, practice
 * hub) used to hardcode its own extension, which is how a JavaScript lesson
 * ended up titled `exercise.py`. Course ids are accepted too, because the app
 * tracks the active course, not an ISO language tag.
 */

const EXT_BY_KEY: Record<string, string> = {
  python: 'py',
  py: 'py',
  dsa: 'py',
  ml: 'py',
  'ml-math': 'py',
  ai: 'py',
  fullstack: 'py',
  javascript: 'js',
  js: 'js',
  typescript: 'ts',
  ts: 'ts',
  java: 'java',
  cpp: 'cpp',
  'c++': 'cpp',
  sql: 'sql',
}

const ICON_BY_EXT: Record<string, string> = {
  py: '🐍',
  js: '📜',
  ts: '🟦',
  java: '☕',
  cpp: '⚙️',
  sql: '🗄️',
  md: '📘',
}

export function languageExt(language?: string | null): string {
  return EXT_BY_KEY[(language || 'python').toLowerCase()] || 'py'
}

export function fileIcon(filename: string): string {
  if (!filename.includes('.')) return '📄'
  const ext = filename.split('.').pop()!.toLowerCase()
  return ICON_BY_EXT[ext] || '📄'
}

/** `create_button.js`, `hash_map.java` — never a fixed `exercise.py`. */
export function slugFilename(title: string, language?: string | null, fallback = 'exercise'): string {
  const slug = (title || '')
    .toLowerCase()
    .replace(/^step\s*[a-z0-9]+:\s*/i, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 28)
  return `${slug || fallback}.${languageExt(language)}`
}
