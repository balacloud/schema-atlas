# Roadmap

## Phase 0: prove it on real data (first week)
- Run the extractor on a dev Postgres and a dev Oracle schema; fix SQL differences.
- Check 10 tables by hand against the database.
- Collect feedback from 3 developers.

## Phase 1: make it team-ready
- Sign-in (SSO) and HTTPS; per-user audit log of who connected to what.
- Save and share a snapshot with a link; keep snapshot history.
- Confirm or reject inferred links in the UI and write them back to `links.json`.
- Schema diff between two snapshots (dev vs prod, last month vs now).

## Phase 2: deeper understanding
- Oracle: scan procedure/package/view source text for table and column references (catalog dependencies only show object level).
- Column-level lineage for views.
- Usage heat (table size, last analyzed) as an overlay.
- Export: Markdown docs, Mermaid, PNG.

## Phase 3: more sources
- MySQL and SQL Server (catalog pattern is the same).
- GraphQL via introspection (deterministic, URL plus token).
- MongoDB: sampled schema, clearly labelled "sampled" and not deterministic unless sampling rules are fixed.

## Phase 4: optional AI layer
- Plain-English table explanations from extracted facts only; show the exact input.
- "Ask the schema" questions that answer from the model and cite the tables used.
- Never let AI add or change relationships without a person confirming.
