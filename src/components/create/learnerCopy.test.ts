import { describe, it, expect } from 'vitest'
import { compactText, completionClaim, isTranscriptDump, milestoneDescription, whyExplanation, sourceExcerpt } from './learnerCopy'

const DUMP =
  "hello everybody welcome back going from tensor flow to pytorch Friendly and so it's much easier " +
  'to load and work with huggingface transformers so import Transformers and then we can load the ' +
  'model with from_pretrained and so we start by writing the neural net so define a class called GPT ' +
  'and then implement the forward method so that it returns the logits'

describe('Create Course learnerCopy', () => {
  it('detects giant raw transcripts and keeps concise copy', () => {
    expect(isTranscriptDump(DUMP)).toBe(true)
    expect(isTranscriptDump('Load the transformers library so you can use the model.')).toBe(false)
    expect(compactText(DUMP)).toBe('')
    expect(compactText('Load the transformers library so you can use the model.')).toContain('transformers')
  })

  it('prefers a concise description and never returns a caption dump', () => {
    expect(
      milestoneDescription({
        source_grounded_description: DUMP,
        teach: 'Load the library and add the import.',
        title: 'Import Transformers',
      })
    ).toBe('Load the library and add the import.')
    expect(milestoneDescription({ source_grounded_description: DUMP, teach: DUMP, title: 'Import Transformers' })).toBe(
      ''
    )
  })

  it('Why falls back to a short explanation instead of dumping the source', () => {
    const why = whyExplanation({ why: DUMP, title: 'Import Transformers' })
    expect(why.toLowerCase()).not.toContain('tensor flow to pytorch')
    expect(why).toMatch(/Import Transformers/)
    expect(sourceExcerpt(DUMP)).toBe('')
    expect(sourceExcerpt('import transformers')).toBe('import transformers')
  })
})

describe('completionClaim', () => {
  // The dialog used to assert "verified against the source" for every completion, and a
  // workspace of `class Value: pass` files earned that sentence. The grader now records
  // whether a step watched the program run, read only its shape, or could not run it.
  it('claims only that the program ran when a step executed', () => {
    expect(completionClaim({ evidence_executed: 1, evidence_structural: 3 }, 'Micrograd'))
      .toMatch(/built .Micrograd. end-to-end, and the program ran/)
  })

  it('says so when nothing was ever executed', () => {
    const claim = completionClaim({ evidence_executed: 0, evidence_structural: 4 }, 'Flask')
    expect(claim).toMatch(/code's shape/)
    expect(claim).toMatch(/nothing here ran the program/)
  })

  it('says so when the sandbox could not run the project at all', () => {
    const claim = completionClaim({ evidence_executed: 0, evidence_unverified: 1 }, 'Httpx')
    expect(claim).toMatch(/never ran here/)
    expect(claim).toMatch(/nothing has checked that it works/i)
  })

  it('claims nothing about verification for a project stored before the distinction', () => {
    expect(completionClaim({}, 'Old')).toMatch(/finished every step/)
    expect(completionClaim(null, 'Old')).toMatch(/finished every step/)
    expect(completionClaim(undefined)).toMatch(/You finished every step of The project/)
  })
})
