---
name: course-study
description: Study a university course through syllabus mapping, lecture preparation or review, concept learning, problem solving, homework support, exam preparation, cumulative review, and prerequisite repair. Use for ordinary coursework without requiring a research workflow.
---

# Course study

Read `references/COURSE_LEARNING_PROTOCOL.md` and
`references/LEARNING_PROTOCOL.md` before setup. In this repository shared references
live at `../../references/`; installation bundles them under `references/`.

Learner questions can interrupt any lesson or probe. Use the nested checkpoint and
shared assessment-budget contract in `references/TUTOR_PLANNING.md`; learner questions
do not consume probe units, while tutor assessments inside branches do. For
consequential course methods/tools, select opt-in schema-3 method understanding,
tool operation and implementation navigation profiles separately from conceptual
and transfer evidence. Preserve actual answer/action, assistance and honest verdict;
explanations and questions alone never establish mastery. Resume the saved lesson
after answering and verifying the branch as needed.

1. Identify the course, available syllabus/outcomes and immediate study need.
2. Reuse existing capability records and inspect evidence and prerequisites.
3. Follow the course cycle: map, check knowledge, study, practice, retrieve/apply,
   use assessment feedback, and update the derived course map.
4. Use official course material and assigned sources first; prepare facts and
   questions before a bounded live probe. Teach and repair only relevant gaps.
5. Preserve attempts and assistance honestly. Respect existing retention targets;
   discuss consequential changes with the learner. Exam preparation does not imply
   lifelong memorization of every detail.
6. Offer the optional course/session templates or use chat/the chosen workspace.
   Keep one evidence record across course, project and goal contexts.

Ordinary course study does not require research agents, experiment design,
adversarial review or research approval. If the learner explicitly moves into a
substantive research question, use `references/RESEARCH_PROTOCOL.md` and
`references/SOURCE_POLICY.md` for that work. Do not silently promote notes.


## Mandatory session artifacts

When this workflow creates or continues a substantive session, follow
`references/HTML_SESSION_PROTOCOL.md`: use the centralized
`scripts/html_sessions.py` API, preserve Markdown backlinks, produce HTML and
structured state, and validate the artifacts. Before creating or resuming, run
`scripts/html_sessions.py context <session>`: it lists unchecked answers and open
questions and loads the project's research and knowledge graphs, which remain the
memory; the page is only a view. Post questions, checks and teaching through the
live loop in that protocol so the session reads in order and updates without reload. Ordinary notes, evidence records and source files retain
their canonical formats. Browser feedback never automatically establishes mastery.
