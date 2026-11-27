# The idea in one page

## Problem
Developers inherit databases with hundreds or thousands of tables, few documented relationships, and years of triggers, views and packages. Onboarding takes weeks. Changes are risky because nobody knows what depends on what. A modern service often sits beside a legacy system, and the link between them lives in people's heads.

## Idea
A tool where someone provides a **read-only connection** and gets, in minutes:
- a searchable catalog of tables, views, columns, keys and sequences;
- an interactive relationship map that starts small (one table and its neighbours) and grows on demand;
- **impact analysis**: "if I change this table, which tables, views, procedures and packages are affected?";
- the shortest **join path** between two tables, with ready-to-copy SQL;
- a single view across **legacy Oracle and modern Postgres**, with human-confirmed links between them.

## What makes it different
1. **Deterministic.** Facts come from database catalogs, not from an AI guessing. Same input gives the same output, and the output carries a fingerprint.
2. **Honest about certainty.** Declared keys are solid lines. Guessed links are dashed with a confidence score and written reasons. Human-confirmed links are marked as such.
3. **AI is the last layer, not the foundation.** It explains tables in plain English using only the extracted facts, never row data.
4. **Safe by design.** Structure only, read-only sessions, host allowlist, credentials never stored.

## Who it is for
Developers, new joiners, architects, QA, data engineers, and anyone doing a migration or modernization.

## Success measures
- Time for a new developer to find the right tables for a task.
- Number of "what depends on this?" questions answered without asking a senior person.
- Incidents caused by unknown dependencies (should fall).
- Share of relationships confirmed by people over time.

## Current state
A working prototype: intake screen, visualizer, extractor logic with tests, and a small API. Demo mode runs without any database. The database queries still need a first run against real dev databases.
