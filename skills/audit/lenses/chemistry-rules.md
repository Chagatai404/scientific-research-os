# Chemistry protocol (v0.9.5)

How the Research OS learns, teaches and reviews chemistry. It adds domain knowledge and checks to the existing workflows; it does not
change evidence rules (`SOURCE_POLICY.md`), research stages and approval (`RESEARCH_PROTOCOL.md`) or learning evidence
(`LEARNING_PROTOCOL.md`). Executable checks are in `VERIFICATION_PROTOCOL.md`.

## Teach the three levels, and say which one you are on

A chemical idea has a macroscopic level (what you observe: colour change, gas, temperature), a particulate level (atoms, ions,
molecules, bonds) and a symbolic level (formulas, equations, mechanism arrows, graphs), often called Johnstone's triangle. Most
confusion is moving between them without saying so. A teaching block names the level it is on and, when it crosses, says so. A
visual states which level it shows (a drawn molecule is a model of the particulate level, not a photograph of it).

## Quantities and units

The mole counts entities; molar mass converts between moles and grams; molarity is moles per litre of **solution**. Never treat
grams, moles and molecules as interchangeable. State the temperature (in kelvin in equations), pressure, state symbols and the
standard state a value refers to. Keep units through every step (`dimensional` check; it knows `mol`, `L`, `M`, `cal`, `atm`, `bar`).
Significant figures follow the least precise input; do not report more digits than the data carry.

## Equations and stoichiometry

A reaction equation conserves each element and the net charge. Check this by computation, not by eye (`formula-balance`). Coefficients
are ratios of amounts, not masses. A yield claim names the limiting reagent and distinguishes theoretical, actual and percent yield
(`stoichiometry`). A balanced equation says nothing about whether the reaction occurs, how fast, or by what mechanism.

## Mechanism, thermodynamics, kinetics

Keep three questions apart: *can* it happen (thermodynamics: free energy), *how fast* (kinetics: barriers, catalysts) and *by what
path* (mechanism: electron flow, intermediates). A favourable free energy does not imply a fast reaction; a catalyst changes the
rate, not the equilibrium position; mechanism arrows show movement of electrons, not atoms. Equilibrium constants are defined with
activities, which concentrations approximate only in dilute ideal conditions: state when that approximation is made.

## Misconceptions to probe (not to assume)

The mole is a mass; equilibrium means equal concentrations; breaking a bond releases energy (it absorbs it); a catalyst shifts
equilibrium; strong means concentrated; an ionic formula is a molecule; conservation of mass means conservation of moles; "the
products are more stable so it is fast". Probe the misconception with a contract question; a correct recitation of the rule is
not evidence it is gone.

## Sources and authority

Prefer, for the claim being made: the primary paper; IUPAC recommendations and the Gold Book for terms and nomenclature; CIAAW for
atomic weights; NIST (the Chemistry WebBook and CODATA constants) for thermochemical data and constants; PubChem or ChEBI for compound
identity, confirmed by InChI or InChIKey rather than by name; a textbook for pedagogy. Record the database, the entry identifier and the
retrieval date. **Check each database's terms before copying its content; link or cite instead.** A value for one temperature,
solvent or phase is a transfer to another, not a fact (`regime-match`).

## What can and cannot be verified by a program

Can: that an equation balances, a molar mass sums correctly, a yield follows from mole ratios, units are consistent, a numerical
limit or integral is right. Cannot: that a mechanism is the real one, that a reaction proceeds under stated conditions, that a
computed energy is accurate, that a compound is what a label says. Reviewers state both lists. Computational chemistry (electronic
structure, molecular dynamics) also follows `COMPUTATIONAL_PROTOCOL.md`: method, basis or force field, convergence, versions and seeds
are declared, and a calculation is not an experiment.

## Safety boundary

Teach mechanisms, analysis, published methods and how to work safely. Do **not** supply synthesis routes, scale-up or purification
instructions for chemical weapons agents, explosives or illicit drugs; guidance on acquiring controlled precursors or avoiding
controls; or ways to defeat a safety review. For any procedure that would be carried out, refer the researcher to the safety data
sheets, their institution's safety officer and approved protocols, and treat missing hazard analysis (incompatible reagents, ventilation,
protective equipment, quenching, scale, waste) as an A-class blocker in review. A refusal here is a scope decision, not a judgement
of the researcher.
