import { describe, it, expect } from 'vitest'
import { compactText, isTranscriptDump, milestoneDescription, whyExplanation, sourceExcerpt } from './learnerCopy'

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
