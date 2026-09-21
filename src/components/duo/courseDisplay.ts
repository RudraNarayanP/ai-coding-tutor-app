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

export type UnitGroup<T> = { id: string; title: string; sectionTitle?: string; lessons: T[] }

/**
 * Group a course's lessons into the units the backend reports them in.
 *
 * Shared by the path view and the unit route on purpose: the URL carries a unit
 * id, so the grouping that produced it has to be the same grouping that reads it
 * back. Two copies would let `/course/x/unit/y` disagree with the map.
 *
 * `unit_id` comes from the curriculum module (`basics`, `linear-regression`, …).
 * The positional fallback only applies to a lesson that reports no unit at all.
 */
export function groupLessonsIntoUnits<T extends UnitKeys>(lessons: T[]): UnitGroup<T>[] {
  const grouped = new Map<string, UnitGroup<T>>()
  lessons.forEach((item, idx) => {
    const unitId = item.unit_id || `unit-${Math.floor(idx / 4) + 1}`
    const unitTitle = item.unit_title || `Unit ${Math.floor(idx / 4) + 1}`
    if (!grouped.has(unitId)) {
      grouped.set(unitId, { id: unitId, title: unitTitle, sectionTitle: item.section_title, lessons: [] })
    }
    grouped.get(unitId)!.lessons.push(item)
  })
  return Array.from(grouped.values())
}

type UnitKeys = { unit_id?: string; unit_title?: string; section_title?: string }
