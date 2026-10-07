# Domain docs

This repo uses a single-context layout.

## Before exploring

Read root `GLOSSARY.md` for domain vocabulary.
Read `CONTEXT.md` when naming player commands, interpretations,
positions, or pending state.
Read relevant decisions in `docs/adr/`.

If a glossary or ADR file is absent, proceed silently.
Domain documentation is created when terms or decisions are resolved.

## Layout

- `GLOSSARY.md` contains the project glossary.
- `docs/adr/` contains architectural decision records.

## Vocabulary and decisions

Use glossary terms in issues, proposals, hypotheses, and test names.
Avoid synonyms the glossary explicitly rejects.

If a needed term is missing, reconsider whether it belongs to the
domain or note the gap for the domain-modeling skill.

Identify any conflict with an existing ADR explicitly.
Name the ADR and explain why its decision should be reconsidered.
