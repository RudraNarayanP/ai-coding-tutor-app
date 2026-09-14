# Requirements: AI Course Generator

## Introduction

The AI Course Generator (feature name: `ai-course-generator`) replaces the Characters/Syntax Reference page as a primary navigation destination in Patchwork. Users can supply any learning material — a YouTube video or playlist, pasted transcript or notes, or an uploaded file — and Patchwork's AI transforms it into a structured, interactive, mastery-based course. The generated course integrates fully into the existing Patchwork learning engine, including the lesson engine, exercise engine, grading, XP, progress tracking, checkpoints, AI tutor, and course map. The product principle is: "AI turns anything you want to learn into a structured interactive mastery path."

---

## Requirements

### Requirement 1 — Primary Navigation Restructure

**User Story:** As a learner, I want the primary navigation to feature a CREATE option so that I can quickly access the AI Course Builder without hunting through secondary menus.

#### Acceptance Criteria
1. GIVEN the user opens the Patchwork app WHEN they view the primary navigation bar THEN the nav items shown are LEARN, CREATE, LEADERBOARDS, QUESTS, and PROFILE in that order.
2. GIVEN the old CHARACTERS nav item WHEN the feature is deployed THEN the CHARACTERS item is removed from primary navigation and replaced by CREATE.
3. GIVEN the user clicks CREATE WHEN the page loads THEN the AI Course Builder interface is displayed.
4. GIVEN the Characters/mascots WHEN displayed in the app THEN they appear only as companions inside the learning experience, not as a primary nav destination.

---

### Requirement 2 — Contextual Guidebook (Syntax Reference Relocation)

**User Story:** As a learner, I want access to syntax and concept reference material from within a lesson so that I can look things up in context without leaving my learning flow.

#### Acceptance Criteria
1. GIVEN the user is inside an active lesson WHEN they open the Guidebook THEN they see syntax/reference content relevant to the current lesson's topic.
2. GIVEN the old Characters/Syntax Reference standalone page WHEN the feature is deployed THEN it is no longer accessible as a top-level route or primary nav destination.
3. GIVEN the Guidebook WHEN opened from any lesson THEN it displays without navigating away from the current lesson (e.g., as a sidebar, drawer, or modal).

---

### Requirement 3 — Course Material Input

**User Story:** As a learner, I want to provide a YouTube URL, playlist, pasted text, or uploaded file as source material so that Patchwork can generate a course from content I have already found.

#### Acceptance Criteria
1. GIVEN the user is on the CREATE page WHEN they enter a single YouTube video URL THEN the system accepts it as valid input and begins analysis.
2. GIVEN the user is on the CREATE page WHEN they enter a YouTube playlist URL THEN the system accepts it as valid input and processes all videos in the playlist.
3. GIVEN the user is on the CREATE page WHEN they paste plain-text transcript or notes into the input field THEN the system accepts the text as course source material.
4. GIVEN the user is on the CREATE page WHEN they upload a supported file containing learning material THEN the system accepts the file as course source material.
5. GIVEN any input type WHEN the user submits it THEN the system validates the input before starting generation and rejects invalid input with a clear, user-friendly error message.

---

### Requirement 4 — Input Validation and Error Handling

**User Story:** As a learner, I want clear feedback when my input is invalid or the source material cannot be used so that I understand what went wrong and how to fix it.

#### Acceptance Criteria
1. GIVEN the user submits a URL WHEN the URL is invalid or unsupported THEN the system displays a user-friendly error message explaining the issue.
2. GIVEN the user submits a YouTube URL WHEN the video is private or deleted THEN the system displays a message indicating the video is unavailable.
3. GIVEN the user submits a YouTube URL WHEN no transcript is available THEN the system informs the user and offers alternatives (e.g., paste transcript manually).
4. GIVEN the user submits a YouTube playlist WHEN the playlist exceeds the system's size limit THEN the system notifies the user and either processes the first N videos or asks them to reduce the selection.
5. GIVEN generation is in progress WHEN the AI generation fails or times out THEN the system displays a user-friendly error and allows the user to retry.
6. GIVEN the user submits source material WHEN the content is insufficient to generate a course (too short, no educational content) THEN the system explains why generation cannot proceed.

---

### Requirement 5 — YouTube and Playlist Analysis

**User Story:** As a learner, I want the AI to intelligently understand the educational structure of my YouTube source material so that the generated course reflects how the content is actually organized, not just a 1-to-1 mapping of videos to lessons.

#### Acceptance Criteria
1. GIVEN a single YouTube video URL WHEN the system analyzes it THEN it extracts: major topics, subtopics, prerequisites, repeated concepts, examples, estimated difficulty, and logical sections.
2. GIVEN a YouTube playlist WHEN the system analyzes it THEN it extracts: video titles, ordering, available transcripts, major topics, subtopics, prerequisites, repeated concepts, examples, cross-video progression, and estimated difficulty.
3. GIVEN analysis of a 90-minute single video WHEN generating the course THEN the system may produce a unit with multiple lessons rather than a single lesson.
4. GIVEN multiple short videos covering the same concept WHEN generating the course THEN the system may combine them into a single unit rather than mapping each video to its own lesson.
5. GIVEN the analysis results WHEN building the curriculum structure THEN the system uses educational understanding of the content, not a blind sequential mapping.

---

### Requirement 6 — AI Curriculum Generation

**User Story:** As a learner, I want the AI to generate a complete, mastery-based course structure from my source material so that I get a professional learning experience, not just a summary.

#### Acceptance Criteria
1. GIVEN analyzed source material WHEN the AI generates the curriculum THEN the output follows the hierarchy: Course → Section → Unit → Concept → Bite-sized Exercises → Practice → Review → Checkpoint.
2. GIVEN a generated course WHEN exercise types are assigned THEN the system selects from: MCQ, true/false, fill-in-the-blank, matching, ordering, classification, output prediction, code completion, debugging, identify-the-mistake, select-multiple, short answer, tiny coding exercise, review, checkpoint, and mastery challenge.
3. GIVEN source material on a programming topic WHEN exercises are generated THEN code-oriented exercise types (code completion, debugging, output prediction, tiny coding) are used where appropriate.
4. GIVEN source material on a non-programming topic WHEN exercises are generated THEN conceptual exercise types (MCQ, matching, ordering, short answer) are used where appropriate.
5. GIVEN generated exercises WHEN reviewed THEN they are original content that tests mastery of the source material, not verbatim reproductions of the source transcript.

---

### Requirement 7 — Source Fidelity and Content Originality

**User Story:** As a learner and content creator, I want Patchwork to teach from source material without copying it wholesale so that the learning experience is transformative and pedagogically sound.

#### Acceptance Criteria
1. GIVEN source material WHEN the AI generates lesson content THEN it distinguishes between source-derived knowledge and AI-generated pedagogical scaffolding.
2. GIVEN any source transcript WHEN exercises and explanations are generated THEN they are original formulations, not verbatim reproductions of the source text.
3. GIVEN a YouTube video as source WHEN the course is generated THEN the system understands, restructures, and teaches the material rather than cloning it.

---

### Requirement 8 — Generation Progress UI

**User Story:** As a learner, I want to see meaningful progress stages while my course is being generated so that I know the system is working and understand what it is doing.

#### Acceptance Criteria
1. GIVEN course generation is triggered WHEN the user is waiting THEN the UI displays a progress indicator with named stages.
2. GIVEN the generation pipeline WHEN progressing through stages THEN the UI shows at minimum these labeled stages: Reading source → Understanding topics → Building prerequisites → Designing units → Creating exercises → Creating checkpoints → Finalizing course.
3. GIVEN any stage WHEN it is actively processing THEN the current stage is visually highlighted or animated.
4. GIVEN generation completes successfully WHEN the final stage finishes THEN the user is automatically transitioned to the Course Preview screen.

---

### Requirement 9 — Course Preview Before Creation

**User Story:** As a learner, I want to preview the generated course before committing to it so that I can confirm it matches my learning goals before starting.

#### Acceptance Criteria
1. GIVEN course generation completes WHEN the preview is displayed THEN the user sees: course title, source name/URL, estimated number of units, estimated number of lessons, estimated number of practice sets, estimated number of checkpoints, and a list of topics covered.
2. GIVEN the preview screen WHEN rendered THEN it includes a START LEARNING button and an EDIT COURSE button.
3. GIVEN the user clicks START LEARNING WHEN on the preview screen THEN the course is saved and the user begins the first lesson.
4. GIVEN the user clicks EDIT COURSE WHEN on the preview screen THEN the course editing interface is shown before the course is started.

---

### Requirement 10 — Course Editing Before Start

**User Story:** As a learner, I want to customize the generated course before starting it so that the course matches my preferences for depth, pacing, and topic focus.

#### Acceptance Criteria
1. GIVEN the course editing interface WHEN displayed THEN the user can rename the course title.
2. GIVEN the course editing interface WHEN displayed THEN the user can reorder units via drag-and-drop or equivalent interaction.
3. GIVEN the course editing interface WHEN displayed THEN the user can remove individual topics or units they do not want to study.
4. GIVEN the course editing interface WHEN displayed THEN the user can set difficulty level: beginner, intermediate, or advanced.
5. GIVEN the course editing interface WHEN displayed THEN the user can choose lesson length (e.g., short, medium, long).
6. GIVEN the course editing interface WHEN displayed THEN the user can adjust the balance between theory and practice content.
7. GIVEN the user requests regeneration of a specific exercise WHEN in the editing interface THEN the AI regenerates only that exercise without regenerating the full course.
8. GIVEN the user saves edits WHEN changes are confirmed THEN the updated course definition is used when START LEARNING is clicked.

---

### Requirement 11 — Duplicate Course Detection

**User Story:** As a learner, I want the system to detect when I am importing source material I have used before so that I don't accidentally create duplicate courses.

#### Acceptance Criteria
1. GIVEN the user submits a source URL or material WHEN the same source has been imported previously THEN the system detects the duplicate before generation begins.
2. GIVEN a duplicate is detected WHEN the user is notified THEN the system presents three options: OPEN EXISTING (load the previously generated course), REGENERATE (replace it with a fresh generation), CREATE NEW VERSION (keep the old course and generate a new one alongside it).
3. GIVEN the user selects OPEN EXISTING WHEN confirmed THEN they are taken directly to their existing course without triggering generation.
4. GIVEN the user selects REGENERATE WHEN confirmed THEN the old course is replaced and generation begins.
5. GIVEN the user selects CREATE NEW VERSION WHEN confirmed THEN both the original and the new version appear in the course library.

---

### Requirement 12 — Generated Course Persistence

**User Story:** As a learner, I want my AI-generated courses to persist between sessions so that my progress and course content survive browser refreshes and app restarts.

#### Acceptance Criteria
1. GIVEN a course is successfully generated and started WHEN the user refreshes the browser THEN the course and all progress are intact.
2. GIVEN a generated course WHEN stored THEN it is saved to the backend, not only in React/client-side state.
3. GIVEN multiple generated courses WHEN the user views their library THEN all previously generated courses are listed.
4. GIVEN the backend restarts WHEN the user returns to the app THEN generated courses and progress are fully restored from persistent storage.

---

### Requirement 13 — Generated Course Integration with Existing Engine

**User Story:** As a learner, I want AI-generated courses to feel identical to native Patchwork courses so that I get the same polished, gamified learning experience regardless of the source.

#### Acceptance Criteria
1. GIVEN a generated course WHEN the user is in a lesson THEN it uses the same lesson engine as native courses.
2. GIVEN a generated course WHEN exercises are completed THEN the exercise engine grades them using the same grading logic as native courses.
3. GIVEN a generated course WHEN the user completes exercises THEN XP is awarded using the same XP rules as native courses.
4. GIVEN a generated course WHEN progress is made THEN progress tracking and the course map update in the same way as native courses.
5. GIVEN a generated course WHEN the user reaches a checkpoint THEN checkpoint logic and mastery evaluation use the same system as native courses.
6. GIVEN a generated course WHEN the user asks the AI tutor a question THEN the tutor responds with awareness of: the source material, the generated curriculum, the current unit, the current concept, the current exercise, and the learner's progress.
7. GIVEN a generated course WHEN displayed in the course library THEN it appears under a "My AI Courses" section.

---

### Requirement 14 — Architecture Reuse

**User Story:** As a developer, I want the AI course generation pipeline to reuse existing Patchwork modules so that generated courses are consistent with native courses and we avoid duplicating infrastructure.

#### Acceptance Criteria
1. GIVEN the generation pipeline WHEN producing a course definition THEN it outputs a format compatible with the existing curriculum loader (`backend/curriculum_loader.py`).
2. GIVEN the generated course definition WHEN loaded THEN it uses the existing lesson definitions and exercise definitions from the lesson models (`backend/lesson_models.py`, `backend/lesson_engine.py`).
3. GIVEN the generation pipeline WHEN implemented THEN it follows the stage sequence: Source → Ingestion → Extraction → Curriculum Analyzer → Curriculum Generator → Generated Course Definition → Existing Lesson Engine.
4. GIVEN the existing `backend/custom_course_generator.py` stub WHEN the feature is implemented THEN it is expanded into the full generation pipeline rather than replaced with a parallel system.
5. GIVEN the existing AI provider abstraction (`backend/ai_provider.py`, `backend/ai_models.py`) WHEN the generator calls an LLM THEN it routes through the existing provider layer.
6. GIVEN the existing tutor service (`backend/tutor_service.py`) WHEN the AI tutor is used in a generated course THEN the same tutor service handles requests with extended context for the generated curriculum.

---

### Requirement 15 — Security and Rate Limiting

**User Story:** As a platform operator, I want all user-provided input to be validated and API usage to be bounded so that the system cannot be abused and API keys remain secure.

#### Acceptance Criteria
1. GIVEN any user-provided URL WHEN received by the backend THEN it is validated and sanitized before any external HTTP request is made.
2. GIVEN any uploaded file WHEN received by the backend THEN it is validated for type and size before processing.
3. GIVEN all LLM and external API keys WHEN the system operates THEN they are stored and used exclusively on the backend and never exposed to the frontend or client.
4. GIVEN a single user WHEN submitting generation requests THEN the system enforces a reasonable per-user rate limit on course generation requests.
5. GIVEN a YouTube playlist WHEN submitted WHEN it exceeds the configured maximum video count THEN the request is rejected or capped with an appropriate message.
6. GIVEN pasted transcript or notes WHEN submitted THEN the system enforces a maximum input size limit.
7. GIVEN generated courses WHEN counted per user THEN the system enforces a reasonable cap on total generated lessons to prevent runaway AI usage.
