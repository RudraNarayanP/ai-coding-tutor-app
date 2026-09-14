import type { CourseSummary } from '../../api'

export function courseShortTitle(title: string): string {
  return title.replace(/ Foundations$/i, '').replace(/ Path$/i, '').trim()
}

export function coursePathTitle(selectedLanguage: string, courses: CourseSummary[]): string {
  const match = courses.find((c) => c.language === selectedLanguage || c.id === selectedLanguage)
  if (match) return `${courseShortTitle(match.title)} Path`
  if (selectedLanguage === 'cpp') return 'C++ Path'
  if (selectedLanguage === 'java') return 'Java Path'
  if (selectedLanguage === 'python') return 'Python Path'
  return `${selectedLanguage} Path`
}

export function isSelectedCourse(course: CourseSummary, selectedLanguage: string): boolean {
  return selectedLanguage === course.language || selectedLanguage === course.id
}
