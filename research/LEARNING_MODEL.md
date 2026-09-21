# Patchwork Learning Model — Research, Diagnosis and Design

Research phase for the Duolingo-for-programming transformation. Written before any
code change; nothing here is implemented yet.

Evidence tags used throughout:

- **[documented]** — the vendor's own engineering/product writing says it.
- **[partial]** — vendor states the behaviour, omits the algorithm.
- **[strong] / [moderate] / [mixed] / [weak]** — peer-reviewed evidence strength.
- **[vendor-claim]** — company efficacy marketing, not peer-reviewed.
- **[inferred]** — my reasoning, not a source's finding.
- **[myth]** — widely repeated, unsupported.

Corrections made during verification (I re-fetched the primary source rather than
trusting the research passes): half-life regression is **Settles & Meeder, ACL 2016,
"A Trainable Spaced Repetition Model for Language Learning"** — one pass had
attributed it to "Settles & Fain". The Duolingo **Session Generator** is confirmed as
a real named service that decides "which exercises should a user see and in what
order", rewritten with latency falling from 750 ms to 14 ms. Duolingo's Energy post
is confirmed to state beginners were twice as likely to run out of hearts
mid-lesson, and that reviewing mistakes at the end of a lesson costs nothing.

---

## 0. The diagnosis, measured

The current product is an examiner, not a teacher. Counts over the shipped
curriculum (334 lessons, 11 languages, 60 exercises total):

| Measurement | Value |
|---|---|
| Lessons with **zero** exercises | 283 / 334 |
| Lessons with no exercise **and** no mastery exam — a prompt plus an empty editor | **278 (83%)** |
| Starter code containing `# TODO` | 231 (69%) |
| Starter code whose body is a bare `pass` | 216 (64%) |
| Lessons with no static hints | 325 / 334 |
| Lessons with teaching content (`worked_example` / `micro_explanation` / `deep_dive`) | 7 / 8 / 2 items |

The unit named in the brief is the worst case, not an outlier: all five lessons in
`curriculum/ml/modules/linear_regression.json` have zero steps. `linreg-predict` is
literally `def predict(x, w, b): # TODO / pass` with a hidden test asserting
`predict(2, 3, 1) == 7`.

Crucially, **the substrate already exists and is unused**. `ExerciseDefinition`
carries `micro_explanation`, `worked_example`, `worked_example_takeaway` and
`deep_dive`, and both exercise surfaces already render them. So the shortfall is
content and sequencing, not a missing UI layer. That reframes the build (see §13).

---

## 1. How Duolingo's system is actually built

**Guided path.** The linear path replaced the skill tree to *remove choice*, not
because a retention win was published: their announcement says learners "aren't
sure whether they're using Duolingo the 'correct' way" and the path now guarantees
each step "is truly the best step". No completion/retention/churn figures came with
it. Only later did an efficacy summary claim the new path produced higher reading and
listening scores, with no linked study. [documented] → [partial]; the circulating
"we measured less decision fatigue" story is **[myth]**.
(<https://blog.duolingo.com/new-duolingo-home-screen-design/>,
<https://blog.duolingo.com/results-duolingo-efficacy-studies/>)

**Structure today.** Courses are re-authored against CEFR with sections for
tracking; crowns are gone, replaced by unit-level "Legendary" and, as the mastery
proxy, the 0–160 **Duolingo Score**. 2026 added **mini-units** (~8-node sequences
for intermediate learners) driven by feedback that long units "could feel repetitive
and abstract". New-versus-review ordering inside a node is still unspecified.
[documented/partial]
(<https://blog.duolingo.com/how-are-duolingo-courses-evolving/>,
<https://blog.duolingo.com/duolingo-score/>,
<https://blog.duolingo.com/intermediate-mini-units/>)

**Authoring pipeline.** Designers decide what to teach and when; models then
generate candidate exercises from that raw content (about ten candidates per
prompt, humans pick and edit and "always have the final say"). So: **the curriculum
is authored; generation only fans out already-decided teaching intent.**
[documented]
(<https://blog.duolingo.com/how-duolingo-experts-work-with-ai/>,
<https://blog.duolingo.com/large-language-model-duolingo-lessons/>)

**Session generator.** Named, disclosed as a service, undisclosed as an algorithm.
Exercise counts, "two halves", difficulty tiers and replay rules for missed items
have never been published; community models are reverse-engineering. **[myth]** if
stated as fact. (<https://blog.duolingo.com/rewriting-duolingos-engine-in-scala/>)

**Birdbrain.** A per-item model predicting the probability *this* learner gets
*this* exercise right, feeding item selection and lesson construction; personalising
over 20% of lessons by Oct 2020. Duolingo says difficulty tweaks "consistently
helped our learners learn more" without a metric. [documented, self-assessed] It
scores difficulty; it does not choose the curriculum — that myth inverts their
division of labour. (<https://blog.duolingo.com/learning-how-to-help-you-learn-introducing-birdbrain/>)

**Spaced repetition.** The only published algorithm is half-life regression (ACL
2016): a trained model predicting per-item recall half-life from learning history,
deployed for strength meters and weak-skill practice, reported at about half the
practice error rate of a Leitner baseline and +9.5% retention on practice sessions.
Current documented behaviour is looser — personalised practice chooses items "using
spaced repetition (along with accuracy)", and the surfaces HLR originally powered
were later removed. Note the implication: **Leitner was the baseline it beat**, so
"Duolingo uses SM-2/Anki scheduling" is **[myth]**. Item-level intervals are
undisclosed. (<https://aclanthology.org/P16-1174/>,
<https://blog.duolingo.com/how-we-learn-how-you-learn/>,
<https://blog.duolingo.com/spaced-repetition-for-learning/>)

**Feedback and hints.** Their stated method is staying at "the edge of what you
know", balancing familiar against challenging, bite-sized lessons, hints as feedback.
"Explain My Answer" moved from paid to free — explicitly because knowing the *why* is
the learning. (<https://blog.duolingo.com/duolingo-teaching-method/>,
<https://blog.duolingo.com/explain-my-answer-now-free/>)

**Penalty reversal — the finding that most affects Patchwork.** Hearts were
originally justified as making learners "take a breather and review previous
lessons" (2020). In July 2025 Duolingo said hearts were "not the most effective way
to support learning": beginners were **2× more likely to run out mid-lesson**, and
**reviewing mistakes at the end of a lesson costs nothing**. [documented, and
reversed by the same vendor]
(<https://blog.duolingo.com/duolingo-energy/>)

**Motivation mechanics, honestly labelled.** Streaks, milestone animations, leagues,
gems are engagement devices with vendor-reported engagement numbers (milestone
animation +1.7% seven-day usage; doubling streak freezes +0.38% daily activity;
seven-day-streak users 3.6× likelier to finish a course — all self-reported
**[vendor-claim]**). XP has no published learning purpose. The one metric they frame
as learning is the Duolingo Score. Leagues are disableable; gems buy
retention-protection, not instruction.
(<https://blog.duolingo.com/how-duolingo-streak-builds-habit/>,
<https://blog.duolingo.com/duolingo-leagues-leaderboards/>)

**New subjects.** Math/Music/Chess reuse "our signature teaching method" and the
same XP/streak machinery; Chess is documented as ~75% puzzle-based with a coach
persona, guided→independent progression, spaced repetition applied to *moves*, and
penalty-free correction. Duolingo claims **continuity**, not a pedagogy change, so
"their method adapted for non-language subjects" is **[partial]** at best. The
strongest available signal is that they dropped the penalty system while keeping the
loop — which happens to be what a coding product needs too.
(<https://blog.duolingo.com/new-subjects/>, <https://blog.duolingo.com/chess-course/>)

---

## 2. What coding products converge on

Best-documented learning model is **Exercism**: concept exercises teach an explicit
concept set, are named after a story rather than the concept, and are deliberately
*not* mentored (automated checks only); practice exercises are mentored and
iterative; difficulty calibrated to about ten minutes for a fluent developer. Test
files and the exemplar solution stay hidden until you pass; analyzers emit
mentor-style commentary. [documented]

**Khan Academy** has the clearest mastery semantics in the industry: Attempted
(<70%) → Familiar (70–99%) → Proficient (100%) → **Mastered** (Proficient *plus*
correct on a mixed-skill assessment). Visualisations precede implementation; projects
are rubric-and-peer graded precisely because code varies too much to auto-grade.
**Codecademy** tiers quizzes (unlimited retakes, 70%, counts) / assessments
(optional, hidden wrong answers, 24 h retake) / exams (mandatory gate).
**DataCamp** states an assess-learn-practice-apply loop and — unusually concrete —
authoring rules: no back-to-back multiple choice, per-course caps, and **authored
success and error messages per option**. **freeCodeCamp** names block types
`workshop, lab, lecture, review, quiz, warm-up` and shows assertion *expected vs
actual* on failure; certification is project sets with an academic-honesty policy.
**Mimo** is the least documented: store copy and testimonials, nothing on review
scheduling or hint staging.

Where sources conflict: Codecademy says progress can never be removed while <70%
means "needs review"; DataCamp counts a skipped course toward the track while
withholding certificate and XP; Exercism's unlocking doc contradicts its reputation
for strict gating.

Nine converged constraints a Duolingo-style loop must not break:

1. Only single-step, bounded responses are auto-graded. Novel programs are graded by
   tests plus rubric/human, never string equality.
2. Read/trace precedes write, but writing is kept — otherwise learners can't author.
3. Failure must be informative: expected-vs-actual, per-option error text.
4. Answers are gated; hint use is recorded as a cost, not neutral.
5. Thresholds cluster at 70% for "passed"; 100% **plus a mixed-skill assessment** for
   "mastered". "Completed" and "mastered" are different states everywhere.
6. Review lives on a parallel surface. **Nobody publishes an algorithm that
   resurfaces items inside the path** — so our in-path review insertion is design
   inference, not inherited practice.
7. Projects come after micro-skills and *are* the certificate.
8. Skipping is by demonstrated ability, not by clicking.
9. Points are being demoted as the success metric (Khan switched its headline metric
   from time to "skills to proficient"; DataCamp caps XP to discourage grinding).

---

## 3. Programming pedagogy: what has evidence

| Technique | Verdict | Strength |
|---|---|---|
| Retrieval practice | 61% vs 40% recall after a week; no benefit at two days — a *retention* effect. Failed retrieval still helps **if feedback follows**. | [strong] |
| Spacing | 184 studies / 317 experiments; optimal gap grows with retention interval, with diminishing returns at long lags. SIGCSE quasi-experiment (684 students): +2.36 points course grade, mediated by ~3.8 extra days of spacing. | [strong] |
| Worked examples / fading | Full guidance beats minimal guidance for novices; advantage recedes with prior knowledge. CS: subgoal labels cut load and failure/withdrawal in CS1. | [strong] maths, [moderate] programming |
| Parsons / reordering | Equal learning in roughly half the time — **not** superior learning. Speed advantage vanished when blocks didn't match students' own solutions; one three-arm RCT found no post-test difference. Distractors cost −26% success, +14% time. Faded Parsons beat writing and tracing for pattern learning (N=237). | [mixed] |
| Self-explanation | g ≈ 0.55 across 64 studies; open-ended beats multiple-choice prompts. CS replications small and low-powered. | [moderate] / [weak] in CS |
| Code tracing | Tracing is a distinct, measurable skill, but the reading→tracing→writing **hierarchy failed to replicate** in 600+ students. Predict-then-learn beat traditional instruction (N=121), gap widening on harder items. | [moderate] |
| Debugging instruction | 43 interventions: gains in accuracy/efficiency/self-efficacy that **frequently evaporate when scaffolds are removed**; few move students to systematic strategies. | [moderate] |
| Productive failure / problem-solving-before-instruction | g = 0.36 overall (0.37–0.58 at high fidelity), **reversed for novices and general skills**; CS replications tiny and short-lived. | [mixed] |
| Interleaving | Blocks look better *during* the lesson; mixing roughly doubles delayed scores in maths; hurts early declarative learning and low-achieving novices. CS-specific evidence essentially absent. | [mixed] |
| Notional machine / misconceptions | Novices aren't missing syntax, they run a **wrong interpreter**. Catalogue of ~198–247 statements in ~10 categories (κ≈0.81): assignment-vs-equality, uninitialised variables, aliasing, scope/shadowing, off-by-one, parameter passing, immutability, recursion base case. | [strong] descriptively |
| Transfer | Far transfer is rare and needs overt similarity plus explicit bridging; near transfer between languages carries concepts but not idioms. "Programming improves general thinking" is **[weak/contested]**. | [mixed] |
| Editor scaffolds | Medium scaffolding beat both more and less for tracing (N=97); a scaffold whose solution diverges from the learner's own plan produces unsuccessful hybrids. Autocomplete raised authoring performance without hurting immediate modification, but **unguarded AI produced deskilling** on later unaided tests in a ~1,000-student field experiment; guard-railed AI did not. Syntax highlighting: little to no comprehension benefit. | [moderate]; highlighting [weak] |
| Hint ladders | Cognitive-tutor logs: learners skimmed **68% of hint levels in under a second**; hint frequency correlated negatively with gains; explanatory hints improved efficiency, not post-tests. Of seven LLM techniques, "lead-and-reveal" (never full code) best matched perceived to actual ability. | [moderate] |
| Gamification | Cognitive outcomes g = 0.49, motivational g = 0.36, behavioural g = 0.25 (motivational/behavioural less stable in subsets). Single-context warning: points/badges/leaderboards predicted **lower** exam performance and lower intrinsic motivation over a semester. Adaptive-mastery platforms alone beat instruction by g = 0.05; as a supplement, 0.43 — **the mechanic is not the pedagogy**. | [moderate] / [mixed] |

No controlled evidence at all was found for two practices this repo treats as
article of faith: **line numbers** and **`# TODO` starter hygiene**. Both are sound
engineering taste; they are not validated learning interventions, and shouldn't be
sold as such.

---

## 4. Session UX, and the strongest argument against copying Duolingo

- **Progress must not lie.** Append adaptive items as bonus segments *past* the
  finish line; never expand the denominator mid-bar and never move the fill
  backwards. People accelerate near a goal, and framing progress as already started
  raises completion — so "extra practice added" is a feature, as long as the count of
  *done* work only ever increases. [strong]
- **One interaction per screen.** Decision time scales with simultaneous options;
  interesting-but-irrelevant material measurably hurts comprehension. A code
  exercise legitimately breaks the rule (prompt + starter + editor + tests is one
  workspace), so compensate with **one primary verb** and hide everything else until
  asked. [strong]
- **Don't hand over the answer on first failure.** Verification feedback repairs the
  item but leaves it error-prone within the session and buys little durable learning;
  terminal feedback after an attempt beats continuous drip during it. Ladder: fail →
  interpreted diagnosis → retry → second fail → hint → third fail → model solution.
  [moderate]
- **Celebrate sparingly and specifically.** Process-specific praise ("you found the
  off-by-one yourself"), 2–3 seconds, skippable, never a gate. Praise can backfire by
  implying low ability or externalising motive. Evidence supports return-visit, not
  code retention. [strong for the caveat]
- **Spend the animation budget on the notional machine.** Sound should be
  informational (one distinct tone for pass/fail), off while typing, respecting
  reduced motion. Decorative extras hurt; showing *how code runs* is the animation
  that pays. [strong]
- **Errors: interpret first, then show the raw form.** Novices extract little from
  compiler output; short jargon-free messages naming the construct and locating it
  improve whether students can repair the problem. Layout decides the order code
  actually gets read in, so keep task, editor and failing test in one visual field
  (split-attention). [moderate]
- **Skipping needs two signals.** Expertise reversal justifies removing guidance as
  prior knowledge grows, but a one-shot multiple-choice pretest is weak evidence of
  durable skill; the defensible validity check is whether test-exempted learners do
  as well *later*. [strong for reversal, moderate for method]
- **Desirable difficulties, correctly.** Effort within capacity is good — retrieval,
  spacing, fading hints. Difficulty from bad UI, unclear wording or punished errors
  is not, and fluency feelings must not be the criterion. Tell learners why hard
  beats smooth. [strong]

**The critique to keep in the room: metric substitution.** Every layer being copied
makes *attendance* observable and *learning* optional, so learners optimise the
visible number — easy reviews, hint-farming, pasting AI output — while the daily
goal, streak, hearts and XP are the loss-aversion machinery that keeps them doing it.
This is analysed as gamified dark patterns, and mirrored in Duolingo's own inflated
efficacy history (the 34-hours-to-a-CEFR-level claim and its rebuttals). The
mitigation is not to delete the mechanics; it is to make the headline metric a
**learning** quantity and to never let a mechanic be satisfiable without retrieval.

---

## 5. The critical question: what the loop becomes when the subject is Python

Language learning and programming differ in one structural way that decides the
design: in a language, *production* is the goal and recognition is a rung to it; in
programming, production is only one of several competencies, and the thing novices
actually lack is a working **notional machine**. So the mapping is not
phrase→code, it is *interpretation→execution*.

```
LANGUAGE                          PATCHWORK (code)
see phrase            →           read a fragment; predict what it does
recognise phrase      →           recognise the construct / spot which line matters
construct phrase      →           reorder into working code (Parsons), fill a blank
produce phrase        →           write the body from a signature
use in context        →           use it in a new program, then debug it
                                    (a rung programming has and language does not)
```

Two additions are programming-specific and must be first-class: **predict-before-run**
(executing a mental model) and **debugging as its own skill** rather than an
aftermath of failure.

Per subject:

- **Python / JavaScript** — transfer almost unchanged. Bite-size recognition →
  construction → production works, with two substitutions: "audio" becomes
  *output*, and word-level SRS becomes concept-level (shadowing, aliasing,
  off-by-one). JavaScript needs a runtime-model emphasis (`this`, event loop)
  because its misconceptions are about execution order, not syntax.
- **SQL** — transfers well, arguably better than any language: it is declarative, so
  "predict the result table" *is* the notional machine, and result-set comparison is
  a fair auto-grader. Ordering is a genuine Parsons problem. Set semantics
  (duplicate rows, `NULL` comparisons) are the misconception mine.
- **C++** — transfers least. Ownership, aliasing, undefined behaviour and memory
  layout need **diagrammatic** worked examples and tracing before any editor time,
  and auto-grading is unsafe for a large fraction of outcomes (a program can pass its
  tests and still be wrong). Expect more human/rubric-graded items here than in
  Python.
- **Machine learning** — least like a language at all. The unit of knowledge is a
  *quantity and its direction of change*, so the loop becomes
  **formula → compute by hand → predict the trend → implement → break it**:
  weight up ⇒ error down? what happens when the learning rate is too big? Here the
  numeric-calculation and predict-the-graph modalities do the work that translation
  does in Spanish, and the "code" is a one-line reduction — so scaffolding is cheap
  and the pedagogy is mostly about making the quantity *felt*.

**What does not transfer:** Duolingo's assumption that a wrong answer is a local
slip. In code a wrong answer is evidence about a *model of execution*, so feedback
must name the misconception rather than the diff. And Duolingo's per-item half-life
model assumes items are independent retrievable facts; a skill like "loop bounds"
is one durable construct exercised by many items, so our scheduling unit should be
the **concept**, not the exercise id.

---

## 6. Patchwork design principles

1. **Teach before you test, and let the ladder be walked, not skipped.** No concept
   reaches an independent-editor step without at least one worked example and one
   zero-stakes interaction. Guidance is *faded*, not withdrawn.
2. **The session, not the exercise, is the product.** A session is an ordered step
   list with mixed modalities, generated per learner from an authored pool.
3. **Free first contact, cost only at assessment.** Charging a heart for a step you
   have never been taught is the exact failure Duolingo documented and reversed.
   Teaching steps are unfail-able; only independent/transfer attempts spend
   anything, and review is always free.
4. **Deterministic and explainable before clever.** Rules over models; every
   generator decision must be printable as a reason string. The evidence says an
   adaptive mechanic alone buys g = 0.05 — the authored sequence is what teaches.
5. **Multiple representations, no editor spam.** Never three editor items in a row;
   DataCamp's "no back-to-back multiple choice" rule generalises to
   "no back-to-back same-modality".
6. **Distractors come from the misconception catalogue and must be executed** — never
   invented. (Our own experience: mechanical generation of these types yielded ~0
   fair items; that matches the vendor's own pipeline — humans decide, models fan
   out.)
7. **Mastery is a set of evidence types, not a percentage.** Guided, independent,
   debugged, transferred, and later recalled. Hint-assisted success alone cannot
   complete the set, and a revealed answer requires a fresh analogous attempt.
8. **Progress bars tell the truth about learning.** Headline metric becomes concepts
   demonstrated, not minutes or XP; review appears as added length past the goal,
   never as a shrinking bar.
9. **Preserve what exists.** Lesson ids, ordering, XP economy (one unit ≈ 100 XP ≈
   one level) and the routing layer are load-bearing. The session model sits on top
   of them; it does not replace them.

---

## 7. Proposed architecture

```
CURRICULUM (course → unit → skill)            authored, CEFR-style intent
   │  skill = concept cluster + objective + misconception ids
   ▼
STEP POOL (per skill, authored)               intro · worked_example · trace ·
   │                                          recognise · calculate · parsons ·
   │                                          fill_blank · guided_code · debug ·
   │                                          independent_code · transfer · review
   ▼
LEARNER MODEL (per concept)                   stage_reached · evidence set ·
   │                                          success/fail run · hint dependence ·
   │                                          last_recall · interval estimate
   ▼
SESSION GENERATOR  (pure function, rules)     generate_session(skill, learner,
   │                                          pool, recent) → ordered steps + reasons
   ▼
STEP RUNNER → EXERCISE ENGINE → GRADER        existing widgets + sandbox unchanged
   │
   ├──► FEEDBACK  (interpreted first, raw second, misconception-named)
   └──► LEARNER MODEL UPDATE → next step → session state → completion evidence
```

The loop the repo has today (curriculum → display exercise → submit → next) is
preserved as a degenerate case: a 0-step lesson still renders exactly as it does
now, so migration is incremental and reversible.

## 8. Proposed data model

Additive only; every new field optional, absent meaning "behave as today".

```jsonc
// curriculum/<lang>/modules/<unit>.json
{
  "id": "linear-regression",
  "skills": [{                        // NEW: a concept cluster between unit and lesson
    "id": "linear-prediction",
    "title": "Linear Prediction",
    "objective": "Compute and explain y = w·x + b",
    "concepts": ["weight", "bias", "prediction"],
    "misconceptions": ["assignment-vs-equality", "variable-as-box"],
    "story": { "why_next": "measuring-error" }   // curriculum as causal narrative
  }],
  "lessons": [{
    "id": "linreg-predict",           // UNCHANGED: ids/order never move
    "skill": "linear-prediction",     // NEW link
    "steps": [{                       // NEW: authored pool, generator-ordered
      "id": "lp-intro-1",
      "stage": "introduce",           // NEW: the ladder rung
      "type": "intro",                // a non-graded step kind
      "content": { "lines": ["A model can use an input to make a prediction."],
                   "symbols": { "x": "input", "w": "weight", "b": "bias" },
                   "formula": "prediction = w * x + b" },
      "action": "Let's see it"
    }, {
      "id": "lp-worked-1", "stage": "show", "type": "worked_example",
      "content": { "given": "x=3, w=2, b=1",
                   "steps": ["prediction = 2 * 3 + 1", "         = 7"] },
      "takeaway": "weight scales the input; bias shifts the result"
    }, {
      "id": "lp-predict-1", "stage": "interact", "type": "mcq",
      "question": "x = 4, w = 3, b = 2. Prediction?", "options": ["14","9","6"],
      "misconception_targeted": "formula_error",
      "feedback": { "14": "You added b twice — b shifts once.", "9": "…" },
      "stakes": "free"                // NEW: free | charged — teaching steps are free
    }, { "id": "lp-fill-1",   "stage": "guided",    "type": "fill_blank",    "stakes": "free" },
      { "id": "lp-code-1",   "stage": "scaffolded", "type": "code_completion", "stakes": "free" },
      { "id": "lp-indep-1",  "stage": "independent","type": "code",           "stakes": "charged" },
      { "id": "lp-debug-1",  "stage": "explain",   "type": "identify_error",
        "buggy_code": "def predict(x,w,b):\n    return x * b + w",
        "misconception_targeted": "wrong_variable" },
      { "id": "lp-transfer-1","stage": "transfer",  "type": "code", "stakes": "charged" }
    ]
  }]
}
```

Backend additions: `StepDefinition` (superset of the existing exercise fields plus
`stage`, `stakes`, `content`, `feedback` per option, `misconception_targeted`,
`prerequisite_of`); a `learner_concept_state` store keyed by **concept** (interval,
evidence set, hint dependence, last recall); and `progress["next_action"]` extended
with a step-level directive. Frontend gains a `stepRunner` that maps `stage`/`type`
to widgets — reusing the existing single-source-of-truth type registry, which is
already mirrored between Python and TS with a drift test.

## 9. Proposed UI flow

Session shell: `● ● ● ○ ○ ○` plus a separate, honest "+2 extra practice added" pill
that appears *past* the end. One card, one primary verb.

```
introduce   tiny statement + one symbol table      [Let's see it]
show        worked example, arithmetic on screen   [Continue]
interact    "what if x becomes 4?"  [9][8][7]      tap → interpreted feedback
guided      prediction = ___ * ___ + ___           free; wrong = name the slip
scaffolded  def predict(x,w,b): return w*___ + b   free; hints gated by a keystroke
independent def predict(...): # your code          charged; tests listed, raw
                                                   traceback behind a disclosure
explain     find the bug in these three lines
transfer    same concept, new surface (cost model)
mastery     mixed-step check, no hints, evidence recorded
```

Every failure path is the same shape: **diagnosis first, evidence second, next
action always single.** Test output reads "`result` is `None` — nothing assigns it
inside the loop", with the raw traceback collapsible underneath, never a bare
`AssertionError`. Completion names what you can now do and why the next concept
exists ("predictions can be wrong → let's measure how wrong").

## 10. Implementation plan

**Phase 0 — research.** Done (this document).

**Phase 1 — architecture, one seam at a time.** `StepDefinition` + generator as a
pure Python module with a `reason` trace; `learner_concept_state` store; step→widget
routing reusing the existing type registry; a `/lesson/{id}/session` response that is
*additive* to today's progress payload. Legacy lessons render unchanged.

**Phase 2 — the Linear Prediction vertical slice** (the only build phase that adds
content): author ~10 steps for `linreg-predict` across 7 modalities; make the
generator produce introduce→show→interact→guided→scaffolded→independent→explain→
transfer for a fresh learner and a visibly shorter ladder for a demonstrated-ready
one; wire completion evidence and the new completion screen; acceptance test from a
**fresh learner state** on an isolated `PATCHWORK_STATE_DIR`, graded both ways by the
existing verification scripts.

**Phase 3 — MSE.** Second skill, and the first real test of generalisation: MSE's
session must *retrieve* linear prediction as review, introduce residuals with a
worked example, and keep the same step kinds — proof that the architecture, not the
content, did the work.

**Phases 4–7 —** generalise the skill/step model to the remaining ML unit and one
Python unit; then adaptive difficulty (rules: repeated success → fewer rungs,
repeated failure → more scaffolding + prerequisite revisit, hint dependence → delay
mastery); then the concept-level spaced scheduler (interval doubling on strong
recall, shortening on miss, review inserted as bonus segments); then projects/
transfer and the diagnostic test-out with two independent signals.

**Explicitly not in v1:** no learner-neural model, no FSRS-vs-SM-2 contest, no
bulk generation, no wholesale rewrite of 334 lessons, no path reordering, and no
new visual identity borrowed from Duolingo.

## 11. Decisions taken (2026-09-21)

1. **Hearts on teaching steps — resolved: free to fail while learning.** Steps carry
   `stakes: "free" | "charged"`. Introduce, show, interact, guided and scaffolded
   rungs never cost a heart or block progress; independent, transfer and mastery
   attempts are charged; review stays free.
2. **Headline metric — resolved: concepts demonstrated.** XP, streaks and leagues
   remain as supporting engagement layers; the primary number becomes concepts the
   learner has demonstrated *independently* (guided success does not count).
3. **Slice location — `linreg-predict`**, the brief's own example, on the least
  -trafficked track: proved there first, generalised after.
