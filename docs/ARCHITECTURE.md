# Architecture

```
 User --> intake.html --> server.py --> extractor.py --> Oracle / Postgres (catalog views only)
                              |                |
                              |                +-- builds schema.json (sorted, fingerprinted)
                              v
                      schema_atlas.html  <-- sessionStorage / "Load schema.json"
                              |
                              +-- (optional) AI tab --> LLM, facts only
```

## Layers
1. **Source adapters** (`fetch_oracle`, `fetch_postgres`): run catalog queries, return one raw shape.
2. **Normalizer** (`normalize`): tables, views, columns, keys, sequences, dependents.
3. **Relationship builder**: declared FKs, inferred links (fixed scoring), view dependencies, manual links.
4. **Model**: `schema.json`, version 2, with `meta.fingerprint` and `meta.ai_used`.
5. **Viewer**: reads the model only. It never talks to databases.

## Where the facts come from
| Fact | Oracle | Postgres |
|---|---|---|
| Tables, comments | ALL_TABLES, ALL_TAB_COMMENTS | pg_class, obj_description |
| Columns | ALL_TAB_COLUMNS | information_schema.columns |
| Keys | ALL_CONSTRAINTS + ALL_CONS_COLUMNS | pg_constraint |
| Sequences to tables | ALL_TRIGGERS + ALL_DEPENDENCIES | pg_depend (owned by) |
| Views and their sources | ALL_VIEWS + ALL_DEPENDENCIES | pg_rewrite + pg_depend |
| Code that touches a table | ALL_DEPENDENCIES | not covered yet |

## Inference rules (exact)
A column that is not a key gets a possible link to another table in the same database when: its name equals that table's single-column primary key name (+50), data types are compatible (+20), target has a single-column key (+10), name ends in _ID/_NO/_CD/_KEY (+10). Generic names (ID, CODE, NAME, STATUS, TYPE) are skipped. Links need a score of 70 or more. Views are never part of inference.

## Model shape (abridged)
```json
{"meta":{"fingerprint":"...","schema_version":2,"ai_used":false},
 "tables":[{"id":"ORA.LEGACY.POLICIES","name":"POLICIES","kind":"table|view","db":"ORA","columns":[],
            "sequence_details":[{"name":"SEQ_POLICY_NO","via":"trigger TRG_POLICIES_BI"}],
            "dependents":[{"type":"PACKAGE","name":"PKG_CLAIMS"}]}],
 "edges":[{"from":"...","fromCols":["CUST_ID"],"to":"...","toCols":["CUST_ID"],
           "kind":"declared|inferred|manual|dependency","confidence":100,"reasons":["..."]}]}
```
