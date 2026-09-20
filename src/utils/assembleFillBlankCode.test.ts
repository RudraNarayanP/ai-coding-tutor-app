import { describe, it, expect } from 'vitest'
import {
  allBlanksFilled,
  assembleFillBlankCode,
  blankCount,
  buildFillBlankTemplate,
  extractAnswersFromEdited,
  isFillBlankCodeComplete,
} from './assembleFillBlankCode'

describe('assembleFillBlankCode', () => {
  it('replaces blanks with learner answers', () => {
    const code = assembleFillBlankCode('ticket_total = ticket_price * ___', ['num_tickets'])
    expect(code).toBe('ticket_total = ticket_price * num_tickets')
  })

  it('counts blanks and validates completion', () => {
    expect(blankCount('a = ___ + ___')).toBe(2)
    expect(allBlanksFilled('a = ___', ['x'])).toBe(true)
    expect(allBlanksFilled('a = ___', [''])).toBe(false)
  })

  it('builds inline blank templates from starter_code + blanks', () => {
    expect(
      buildFillBlankTemplate('language = "Python"', ['"Python"'])
    ).toBe('language = ___')

    expect(
      buildFillBlankTemplate(
        'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * num_tickets',
        ['num_tickets']
      )
    ).toBe('ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * ___')

    expect(
      buildFillBlankTemplate('', [], 'Complete variable assignment: x = ___ (assign value 10)')
    ).toBe('x = ___')
  })

  it('extracts answers from a full editor buffer', () => {
    const template = 'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * ___'
    const edited = 'ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * num_tickets'
    expect(extractAnswersFromEdited(template, template)).toEqual([''])
    expect(extractAnswersFromEdited(template, edited)).toEqual(['num_tickets'])
    expect(isFillBlankCodeComplete(template, edited)).toBe(true)
    expect(isFillBlankCodeComplete(template, template)).toBe(false)
  })
})
