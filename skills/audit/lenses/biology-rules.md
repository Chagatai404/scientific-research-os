# Biology rules

How the Research OS learns, teaches and reviews biology. It adds domain knowledge and checks to the existing workflows; it does not
change evidence rules (`references/EVIDENCE.md`), research stages and approval (`references/RESEARCH.md`) or learning evidence
(`references/TEACHING.md`). Executable checks are attached to verdicts as evidence; statistics follow the statistics lens and the
statistics reviewer.

## Levels of explanation, and mechanism versus correlation

Biological claims sit at a level (molecule, cell, tissue, organism, population, ecosystem) and answer a kind of question: how it works
now (mechanism), how it developed, what it is for, how it evolved. Name the level and the question. A correlation between a gene,
a pathway or a measurement and an outcome is not a mechanism: a mechanism claim needs a perturbation (knockdown, knockout, rescue,
dose-response, intervention) or a stated reason none was possible, and the claim's wording must match what was done.

## Experimental design

Every design states, before the work:

- the question, the hypothesis, and what result would count against it;
- **controls**: negative, positive and vehicle or mock, each with its purpose;
- **replication**: biological replicates (independent organisms, cultures, litters or donors) are not technical replicates (repeated
  measures of one sample). Treating the second as the first is pseudoreplication; check with `resampling-unit`;
- **randomization and blinding**, and how allocation and outcome assessment were protected from the experimenter's expectation;
- **sample size** and how it was chosen, **exclusion criteria** fixed in advance, and batch or day effects handled in the design;
- the **analysis plan** fixed before looking at outcomes, with multiplicity addressed when many things are tested.

Declare each as an assumption and check that it is declared (`assumption-declared`, with ids such as `negative-control`,
`biological-replicates-independent`, `blinded-assessment`). Small samples need exact or resampling methods and honest intervals
(`rate-interval` for proportions), not asymptotic ones.

## Model systems and scope

State the system: species and strain or cell line, passage and authentication, in vitro, in vivo or in silico. A result in one is a
hypothesis in another; extrapolating (cell line to patient, mouse to human, culture to ecosystem) is a transfer to be argued
(`regime-match`), not assumed. Use unique identifiers for reagents and organisms where they exist (strain, cell line and antibody
identifiers, catalogue numbers).

## Sequences, structures and coordinates

A sequence has an alphabet, a molecule type, an accession **with version**, and a numbering convention (0- or 1-based; residue numbers
in a structure file often differ from those of the reference sequence). Genomic coordinates are meaningless without the assembly build.
Executable checks cover what rules decide: valid alphabet, length, reverse complement, transcript, translation under the standard code
and frame, GC content (`sequence-check`). They do not decide that a sequence is the right gene, that an annotation is correct, or
that a variant is pathogenic. A structure is a model fitted to data with a method and a resolution; a predicted structure is a
prediction with its own confidence measures, not an observation. Cite the entry identifier and version.

## Sources and authority

Prefer, for the claim: the primary paper; curated databases for what they curate (UniProt for protein entries, the PDB for
experimental structures, NCBI resources for sequences and literature, Ensembl for annotation) with identifier, version and retrieval
date; reviews and textbooks for background. **Check each database's terms and licence before copying its content; link or cite
instead.** A statement in a database is a curated claim with its own evidence level, not ground truth.

## Misconceptions to probe (not to assume)

Evolution is goal-directed or progress toward a goal; "fittest" means strongest; a gene "for" a trait determines it; the central
dogma means one gene, one protein, one trait; dominant means common or better; correlation of expression with phenotype shows cause;
absence of a band or signal shows absence of the thing. A correct recitation is not evidence the misconception is gone.

## Wet-lab design annex (used by `the research skill's planning step`)

For an experiment that will be done at a bench or with living material, the plan also lists: materials with identifiers and sources;
the protocol and its version; controls and replicates as above; randomization and blinding; sample-size justification and exclusion
rules; the pre-specified analysis; data and metadata management; **approvals** (ethics board or animal-care committee, human-subjects
review, biosafety committee) with their references; the biosafety level and containment; waste handling. An experiment without its
approvals is not ready for the human approval gate, and the plan says so.

## Safety boundary

Teach concepts, analysis, published methods and biosafety. Do **not** provide protocols to culture, produce, enhance or increase the
transmissibility or lethality of dangerous pathogens or toxins, gain-of-function methods, or ways to evade biosecurity screening of
sequences or orders. Experiments on people or animals need the institution's approvals before any plan reaches the approval gate.
Refer hazardous-procedure and dual-use questions to the institutional biosafety committee and treat a missing hazard or approval
assessment as an A-class blocker in review. A refusal here is a scope decision, not a judgement of the researcher.
