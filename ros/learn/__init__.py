"""The learning engine: when to review (``schedule``), where the learner's edge is (``probe``), and what to do next
(``policy``). Each reads the record and returns a decision; only ``tutor`` writes, and only events."""
