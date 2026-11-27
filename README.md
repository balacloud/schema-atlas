# Schema Atlas

**Point it at a read-only database account and get a clear, explorable map of the structure:** tables, views, keys, relationships, sequences, and "what breaks if I change this?". Built for developers who inherit big legacy databases.

Everything on screen comes from **code reading the database catalog**. No AI decides anything. AI is an optional, clearly separated explainer at the very end.

## Try it in 30 seconds (no database needed)
```bash
python -m http.server 8000
```
Open http://localhost:8000/intake.html. Demo mode is on. Paste `oracle://u:p@db.corp:1521/SVC`, click **Test connection**, then **Extract**, then **Open Atlas**.
Other demo scenarios are listed on the page (risky account, blocked host, unreachable, unsupported type).
To skip the intake, open `schema_atlas.html` directly: it loads a built-in sample insurance schema (Oracle legacy + Postgres micro-service).

## What is in the box
| File | What it is | Status |
|---|---|---|
| `intake.html` | Choose source, paste connection string, safety check, extract | Works in demo mode; real mode needs `server.py` |
| `schema_atlas.html` | The visualizer: focus graph, search, impact, join paths, AI tab (stub) | Works with sample or real output |
| `extractor.py` | Deterministic Oracle + Postgres extractor and relationship builder | Logic unit-tested on mock data; **SQL not yet run against real DBs** |
| `server.py` | Small FastAPI service: detect, test, extract; host allowlist; read-only check | Logic tested; **needs a real run** |
| `sample_schema.json` | Example output (19 objects) so anyone can see the format | Mock |
| `links.example.json` | How people confirm cross-database links | Example |
| `tests/` | 8 unit tests, no database needed | Passing |
| `docs/` | Idea one-pager, architecture, roadmap, security | Read these |

## Run it for real
1. `pip install -r requirements.txt`
2. Create a **read-only** DB account (see `docs/SECURITY.md`).
3. `ALLOWED_HOSTS=your-db-host python server.py` then open http://localhost:8000
4. Untick **Demo mode**, paste the connection string, test, extract.

Or use the command line only:
```bash
python extractor.py --oracle "oracle://ro:pw@host:1521/SVC" --owners LEGACY \
                    --postgres "postgresql://ro:pw@host/db" --schemas public \
                    --links links.json --out schema.json
```
Then open `schema_atlas.html` and click **Load schema.json**.

## Where to start (suggested order for whoever builds this)
1. Run the demo and the tests (`python -m unittest discover tests`).
2. Run the extractor against a **dev** Postgres. Fix any SQL surprises. Compare output to the database by hand for 3 tables.
3. Do the same for Oracle with a dev schema. Check that sequences, triggers and views appear.
4. Edit `DOMAIN_RULES` in `extractor.py` so colours match your business areas.
5. Add confirmed cross-database links in `links.json`.
6. Put it behind your company sign-in and HTTPS (see `docs/SECURITY.md`) before sharing.
7. Pick items from `docs/ROADMAP.md`.

## Design rules (please keep them)
- **Deterministic first.** Same database, same output, byte for byte. The `fingerprint` proves it.
- **Evidence for every line.** Each relationship says why it exists (declared, inferred with reasons, or confirmed by a person).
- **Structure only.** The extractor never reads table rows.
- **AI last.** AI only explains facts already extracted, in its own tab, and can never change the diagram.

## Known limits (be honest with users)
- Not yet run against real Oracle or Postgres; expect small SQL fixes.
- Oracle sequences are linked only through trigger dependencies. Sequences used directly by app code are not linked.
- Inferred links are guesses by naming and type rules. They are dashed and show a confidence score.
- Oracle and Postgres cannot be joined in one SQL statement. The path finder says so.
- GraphQL, MongoDB and others are not built (see roadmap).
- The AI explainer is a stub (it shows exactly what would be sent).
