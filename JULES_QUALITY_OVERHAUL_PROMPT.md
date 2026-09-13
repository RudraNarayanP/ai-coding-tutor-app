# JULES AGENT: RUTHLESS QUALITY OVERHAUL PROMPT

## 🎤 MICHAEL JACKSON PERFECTIONIST MANDATE

You are tasked with fixing the course generation system with the same obsessive perfectionism that Michael Jackson applied to his music. MJ didn't settle for "good enough" - he spent years perfecting a single vocal take, analyzed every beat, and rejected anything that wasn't absolute excellence. You will apply this same ruthless standard to the question generation system.

**Core Philosophy:** Quality Over Completeness. Better to generate NO questions than GENERIC questions. Better to FAIL than to produce MEDIOCRITY.

---

## 🚨 CURRENT STATE: UNACCEPTABLE

The current system produces generic, template-based garbage questions like:
- "Primary mechanism of [concept] optimizing efficiency and consistency as stated in source material"
- "Secondary misconfiguration of [concept] leading to non-deterministic failure"
- "Option A: According to the source analysis, [concept] exhibits high-order theoretical properties"

**This is LAZY. This is MEDIOCRE. This is UNACCEPTABLE.**

These templates don't reference actual video content. They're filler. They're the musical equivalent of elevator music. MJ would have burned the master tapes.

---

## 🎯 YOUR MISSION: RUTHLESS QUALITY OVERHAUL

### **PHASE 1: ELIMINATE THE GARBAGE FALLBACKS**

**Current Offense:** Lines 960-1026 in `backend/custom_course_generator.py`

**Your Action:**
1. **DELETE the generic fallback question templates entirely** - They are an insult to the user's video content
2. **Replace with content-extraction fallbacks** that actually parse the transcript for specific facts, names, numbers, code snippets, quotes
3. **If you can't extract specific content, FAIL GRACEFULLY** - Return a clear error message: "Insufficient specific content in source material to generate quality questions"
4. **Never accept template-based filler** - If the LLM fails, retry with a stronger prompt, don't fall back to templates

**Specific Requirements:**
- Extract actual named entities from transcripts (people, places, technologies, numbers)
- Extract direct quotes from the video content
- Extract specific code examples or formulas mentioned
- Extract specific case studies or examples given
- Generate questions that reference these specific elements

---

### **PHASE 2: INCREASE SOURCE CONTEXT DRAMATICALLY**

**Current Offense:** Lines 723-733 truncate context to 2,000 chars per segment, 10,000 total, 120 for fallbacks

**Your Action:**
1. **Increase limits to 50,000 characters total context** - We're not in the 1990s anymore
2. **Per-segment limit: 8,000 characters** - Give the LLM actual content to work with
3. **Fallback context: 2,000 characters minimum** - 120 chars is pathetic
4. **Implement smart context selection** - Don't just truncate, select the most relevant segments based on concept keywords
5. **Add segment metadata** - Include timestamps, speaker names, chapter titles in context

**Specific Implementation:**
```python
# REPLACE THIS GARBAGE:
t_snip = s.transcript[:2000] if s.transcript else s.description_snippet[:500]

# WITH THIS QUALITY:
full_transcript = s.transcript if s.transcript else ""
# Use intelligent selection based on concept relevance
relevant_segments = self._select_relevant_segments(full_transcript, concept_keywords)
t_snip = "\n".join(relevant_segments[:3])  # Top 3 most relevant segments
```

---

### **PHASE 3: IMPLEMENT RUTHLESS QUALITY VALIDATION**

**Current Offense:** No validation that questions relate to source material

**Your Action:**
1. **Create a quality validator that REJECTS generic content**
2. **Check if question contains specific content references** - Names, numbers, quotes, code
3. **Check if options are plausible distractors** - Not "Option A/B/C" templates
4. **Check if explanation references actual content** - Not generic "as covered in material"
5. **Quality score threshold: 70% minimum** - Below this, regenerate or fail

**Quality Criteria (MUST PASS ALL):**
- ✅ Question contains at least one specific entity from source (name, number, code, quote)
- ✅ Options are domain-specific and plausible, not generic templates
- ✅ Explanation references specific content with timestamps or segments
- ✅ Question tests actual understanding, not pattern matching
- ✅ No placeholder text like "Option A", "Incorrect choice", etc.

**Rejection Criteria (INSTANT REJECT):**
- ❌ Contains template phrases: "Primary mechanism", "Secondary fallback", "Legacy implementation"
- ❌ Generic options: "Option A/B/C", "Choice 1/2/3"
- ❌ Explanation doesn't reference specific content
- ❌ Question could apply to any video on the topic

---

### **PHASE 4: REWRITE LLM PROMPTS WITH MJ-STANDARD PERFECTION**

**Current Offense:** Generic prompts that produce generic results

**Your Action:**
1. **Rewrite system prompts to be SPECIFIC and DEMANDING**
2. **Add examples of excellent vs. terrible questions**
3. **Add specific requirements for different domains**
4. **Add penalties for generic responses**
5. **Make the LLM understand that mediocrity = failure**

**New System Prompt Template:**
```
You are creating educational content with the same standard as a Grammy-winning producer.
EVERY question must be specific, accurate, and directly tied to the provided source material.

QUALITY STANDARDS - FAILURE TO MEET THESE = REJECTION:
❌ FORBIDDEN: Generic template questions ("What is the key principle of X?")
❌ FORBIDDEN: Placeholder options ("Option A", "Choice 1")
❌ FORBIDDEN: Generic explanations ("This relates to X as covered in material")
❌ FORBIDDEN: Questions that could apply to any video on this topic

✅ REQUIRED: Specific facts, names, numbers, quotes from source material
✅ REQUIRED: Options that are plausible domain-specific distractors
✅ REQUIRED: Explanations that reference specific timestamps or content
✅ REQUIRED: Questions that could ONLY be answered by watching THIS video

IF YOU CANNOT MEET THESE STANDARDS: Return empty array rather than generic content.
```

**Add Domain-Specific Prompting:**
- **Programming:** Require code snippets, specific syntax, error messages, API names
- **Mathematics:** Require specific formulas, numbers, mathematical notation
- **Science:** Require specific phenomena, measurements, experimental details
- **History:** Require specific dates, names, events, quotes

---

### **PHASE 5: ELIMINATE FALLBACK CASCADE**

**Current Offense:** Multiple fallback layers each producing more generic content

**Your Action:**
1. **Remove the concept graph fallback** (lines 398-432) - If LLM can't extract concepts, fail clearly
2. **Remove the curriculum sequencer fallback** (line 466) - If LLM can't sequence, retry with better prompt
3. **Remove the exercise generation fallback** (lines 960-1026) - If LLM can't generate questions, fail
4. **Implement retry logic with prompt improvement** - Don't fall back, retry stronger
5. **Add exponential backoff** - Retry 3 times with increasingly specific prompts before failing

**New Philosophy:**
```python
# OLD (WRONG):
try:
    result = await llm.generate()
except:
    return generic_fallback()  # LAZY

# NEW (MJ-STANDARD):
for attempt in range(3):
    try:
        result = await llm.generate(prompt=self._get_improved_prompt(attempt))
        if self._quality_check(result).score >= 70:
            return result
    except QualityError:
        continue  # Retry with better prompt
return GenerationError("Unable to generate quality content from source material")
```

---

### **PHASE 6: ADD FEW-SHOT LEARNING EXAMPLES**

**Current Offense:** No examples of what constitutes quality

**Your Action:**
1. **Add excellent question examples** from successful course generations
2. **Add terrible question examples** with explanations of why they failed
3. **Include these in the LLM prompt** for few-shot learning
4. **Update examples based on domain** - Programming examples for coding videos

**Example Format:**
```
EXCELLENT QUESTION EXAMPLE:
Question: "At 3:45 in the video, the instructor demonstrates that Python's list comprehension
[expression for item in iterable] is equivalent to which traditional loop structure?"
Options: [
  "for item in iterable: result.append(expression)",
  "while item in iterable: result = expression",
  "map(lambda item: expression, iterable)",
  "filter(lambda item: expression, iterable)"
]
Explanation: "The instructor specifically shows at timestamp 3:45 that list comprehensions
are syntactic sugar for the for-loop pattern shown in Option A, demonstrating this with
the example [x*2 for x in range(5)] expanding to the loop structure."

TERRIBLE QUESTION EXAMPLE:
Question: "What is the key principle of list comprehensions presented in the lesson material?"
Options: [
  "The core mechanism and definition of list comprehensions",
  "An alternative configuration unrelated to list comprehensions",
  "A deprecated legacy behavior superseded by list comprehensions"
]
Explanation: "This question is completely generic and could apply to any programming tutorial.
It contains no specific references to the video content, no timestamps, no code examples,
and the options are template placeholders rather than plausible distractors."
```

---

### **PHASE 7: IMPLEMENT DOMAIN-SPECIALIZED GENERATION**

**Current Offense:** Same generic approach for all content types

**Your Action:**
1. **Create domain-specific question generators** for programming, math, science, etc.
2. **Add domain-specific validation rules** - Code must compile, math must be correct
3. **Implement domain-specific extraction** - API names for programming, formulas for math
4. **Add domain-specific few-shot examples** in each prompt

**Domain Specialization Examples:**

**Programming Domain:**
- Extract function names, API calls, syntax patterns
- Validate code snippets compile/run
- Generate code-completion questions with actual APIs
- Use error messages and stack traces from video

**Mathematics Domain:**
- Extract formulas, variables, numbers, notation
- Validate mathematical correctness
- Generate calculation questions with actual values from video
- Use specific mathematical terminology from content

**Science Domain:**
- Extract phenomena, measurements, experimental details
- Validate scientific accuracy
- Generate prediction questions based on demonstrated principles
- Use specific scientific terminology and units

---

### **PHASE 8: ADD COMPREHENSIVE ERROR ANALYSIS**

**Current Offense:** Generic exception handling with no analysis

**Your Action:**
1. **Implement detailed error classification** - Distinguish different failure types
2. **Add error-specific recovery strategies** - Different fixes for different failures
3. **Log detailed failure analysis** - Why did LLM fail? What was wrong with output?
4. **Implement adaptive retry** - Adjust prompts based on failure analysis

**Error Classification:**
```python
class GenerationErrorType:
    LLM_RETURNED_EMPTY = "llm_returned_empty"
    LLM_RETURNED_INVALID_JSON = "llm_returned_invalid_json"
    QUALITY_CHECK_FAILED = "quality_check_failed"
    CONTENT_EXTRACTION_FAILED = "content_extraction_failed"
    DOMAIN_VALIDATION_FAILED = "domain_validation_failed"

class ErrorRecovery:
    def get_recovery_strategy(error_type):
        if error_type == GenerationErrorType.QUALITY_CHECK_FAILED:
            return "regenerate_with_stronger_quality_requirements"
        elif error_type == GenerationErrorType.CONTENT_EXTRACTION_FAILED:
            return "increase_context_window_and_retry"
        # ... specific strategies for each error type
```

---

### **PHASE 9: IMPLEMENT QUALITY SCORING SYSTEM**

**Current Offense:** Binary pass/fail with no nuance

**Your Action:**
1. **Create a multi-dimensional quality scoring system**
2. **Score on: Content Specificity (0-100), Domain Accuracy (0-100), Plausibility (0-100)**
3. **Weighted overall score with 70% threshold**
4. **Provide detailed quality feedback** - Why did this score low?
5. **Use quality scores to guide prompt improvement**

**Quality Scoring Rubric:**
```python
def quality_score(question, source_material):
    scores = {
        "content_specificity": check_specific_references(question, source_material),  # 0-100
        "domain_accuracy": validate_domain_specifics(question),  # 0-100
        "option_plausibility": check_option_quality(question.options),  # 0-100
        "explanation_quality": check_explanation_specificity(question.explanation),  # 0-100
    }
    overall = weighted_average(scores, weights=[0.4, 0.3, 0.2, 0.1])
    return overall >= 70, overall, scores
```

---

### **PHASE 10: ADD HUMAN REVIEW FLAGGING**

**Current Offense:** No mechanism to catch edge cases

**Your Action:**
1. **Flag low-quality but passing content** for human review
2. **Create a review queue** for borderline cases
3. **Implement feedback loop** - Use human corrections to improve prompts
4. **Add confidence scoring** - Low confidence = flag for review

**Flagging Criteria:**
- Quality score 60-70% (borderline)
- First time generating for this domain
- Unusual source material structure
- LLM took multiple retries to pass quality check

---

## 🎤 EXECUTION STANDARDS

### **MICHAEL JACKSON QUALITY CHECKLIST:**

Before committing any changes, ask yourself:

1. **Would MJ accept this question?** - If it's generic, the answer is NO
2. **Does this question REQUIRE watching the specific video?** - If not, it's too generic
3. **Are the options specific to this content?** - If they're templates, they're garbage
4. **Does the explanation reference specific content?** - If it's generic, rewrite it
5. **Would I be embarrassed to show this to a learner?** - If yes, it's not ready

### **RUTHLESS TESTING:**

1. **Test with real user videos** - Not synthetic test cases
2. **Measure quality improvement** - Compare before/after quality scores
3. **Test edge cases** - Short videos, technical content, multiple speakers
4. **Performance testing** - Ensure quality doesn't kill performance
5. **A/B testing** - Compare old vs. new generation quality

### **SUCCESS METRICS:**

- **Quality Score:** Average > 85% (up from current ~40%)
- **Generic Content:** < 5% (down from current ~60%)
- **Content Specificity:** > 90% of questions reference specific video content
- **User Satisfaction:** Measured through feedback (target > 80% positive)
- **Fallback Rate:** < 10% (down from current ~40%)

---

## 🚨 IMMEDIATE ACTION ITEMS

### **Priority 1 (CRITICAL - Do This First):**
1. **Delete lines 960-1026** - The generic fallback questions must go
2. **Implement content-extraction fallback** - Use actual transcript data
3. **Increase context limits** - 50,000 chars total, 8,000 per segment
4. **Add basic quality validation** - Reject template-based content

### **Priority 2 (HIGH - Complete This Week):**
5. **Rewrite LLM prompts** - Add MJ-standard quality requirements
6. **Implement quality scoring** - Multi-dimensional scoring system
7. **Add few-shot examples** - Excellent vs. terrible examples
8. **Remove fallback cascade** - Implement retry logic instead

### **Priority 3 (MEDIUM - Complete This Month):**
9. **Add domain specialization** - Different strategies for different content
10. **Implement error analysis** - Detailed error classification
11. **Add human review flagging** - Catch borderline cases
12. **Performance optimization** - Ensure quality doesn't kill speed

---

## 🎯 FINAL MANDATE

**Remember:** The current system produces garbage because it was designed to prioritize "always generate something" over "generate quality content." This is the musical equivalent of releasing an album because the deadline is due, even if the songs aren't perfect.

**MJ never did that.** He delayed albums for years because they weren't perfect. He spent 50 takes on a single vocal line. He analyzed every beat until it was exactly right.

**You will apply this same standard.**

- If the LLM can't generate quality questions, the system should say so clearly
- If the source material is insufficient, the system should request more content
- If the quality isn't excellent, the system should regenerate or fail
- Generic questions are worse than no questions

**Quality Over Completeness. Excellence Over Convenience. Perfection Over Speed.**

This is not a suggestion. This is a mandate. Fix the system to MJ standards or don't ship it at all.

---

## 📋 DELIVERABLES

1. **Updated `backend/custom_course_generator.py`** - With all fixes implemented
2. **Quality validation system** - With scoring and rejection logic
3. **New LLM prompts** - With MJ-standard quality requirements
4. **Test results** - Showing quality improvement metrics
5. **Documentation** - Explaining the quality-overhaul approach

**Timeline:** Complete Priority 1 within 24 hours. Complete Priority 2 within 1 week. Complete Priority 3 within 1 month.

**Standard:** Michael Jackson Perfectionism. Nothing less will be accepted.

---

*Remember: "The greatest education in the world is watching the masters at work." - Michael Jackson*

**Be the master. Show the world what quality looks like.**