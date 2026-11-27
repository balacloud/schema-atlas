"""Deterministic DB metadata extractor (Oracle + Postgres). No AI, no row data.
Same database state -> byte-identical schema.json (the fingerprint proves it).

What it reads (catalog views only):
  * tables, columns, primary keys, declared foreign keys
  * Oracle sequences tied to tables via TRIGGER -> SEQUENCE dependencies (ALL_DEPENDENCIES + ALL_TRIGGERS)
  * views / materialized views as nodes (kind="view") with "dependency" edges
  * procedures, functions, packages, triggers that touch a table -> table["dependents"]
  * Postgres: owned-by sequences (pg_depend), view dependencies (pg_rewrite + pg_depend)
  * inferred links (fixed scoring rules) and person-confirmed cross-DB links (links.json)

Usage: python extractor.py --oracle "oracle://ro_user:pw@host:1521/SVC" --owners LEGACY \
                           --postgres "postgresql://ro_user:pw@host/db" --schemas public \
                           --links links.json --out schema.json
"""
import json, hashlib, re, argparse
from urllib.parse import urlparse, unquote

ORACLE_SQL = {
 "tables":  "SELECT t.owner, t.table_name, t.num_rows, c.comments FROM all_tables t LEFT JOIN all_tab_comments c ON c.owner=t.owner AND c.table_name=t.table_name WHERE t.owner IN ({owners})",
 "columns": "SELECT owner, table_name, column_name, data_type, nullable, column_id FROM all_tab_columns WHERE owner IN ({owners})",
 "keys":    "SELECT c.owner, c.table_name, c.constraint_name, c.constraint_type, c.r_owner, c.r_constraint_name, cc.column_name, cc.position FROM all_constraints c JOIN all_cons_columns cc ON cc.owner=c.owner AND cc.constraint_name=c.constraint_name WHERE c.constraint_type IN ('P','R') AND c.owner IN ({owners})",
 "sequences": "SELECT sequence_owner, sequence_name FROM all_sequences WHERE sequence_owner IN ({owners})",
 "views":   "SELECT v.owner, v.view_name, c.comments FROM all_views v LEFT JOIN all_tab_comments c ON c.owner=v.owner AND c.table_name=v.view_name WHERE v.owner IN ({owners})",
 "mviews":  "SELECT owner, mview_name FROM all_mviews WHERE owner IN ({owners})",
 "triggers": "SELECT owner, trigger_name, table_owner, table_name FROM all_triggers WHERE base_object_type='TABLE' AND owner IN ({owners})",
 "deps":    "SELECT owner, name, type, referenced_owner, referenced_name, referenced_type FROM all_dependencies WHERE owner IN ({owners}) AND referenced_owner IN ({owners}) AND referenced_type IN ('TABLE','VIEW','MATERIALIZED VIEW','SEQUENCE')",
}
PG_SQL = {
 "tables":  "SELECT n.nspname, c.relname, c.reltuples::bigint, obj_description(c.oid), c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind IN ('r','p','v','m') AND n.nspname = ANY(%s)",
 "columns": "SELECT table_schema, table_name, column_name, data_type, is_nullable, ordinal_position FROM information_schema.columns WHERE table_schema = ANY(%s)",
 "keys":    """SELECT n.nspname, t.relname, con.conname, con.contype, fn.nspname, ft.relname,
   (SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(con.conkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.num),
   (SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(con.confkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=con.confrelid AND a.attnum=k.num)
   FROM pg_constraint con JOIN pg_class t ON t.oid=con.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
   LEFT JOIN pg_class ft ON ft.oid=con.confrelid LEFT JOIN pg_namespace fn ON fn.oid=ft.relnamespace
   WHERE con.contype IN ('p','f') AND n.nspname = ANY(%s)""",
 "sequences": """SELECT s.schemaname, s.sequencename, tn.nspname, t.relname
   FROM pg_sequences s
   LEFT JOIN pg_class sc ON sc.relname=s.sequencename AND sc.relnamespace=(SELECT oid FROM pg_namespace WHERE nspname=s.schemaname)
   LEFT JOIN pg_depend d ON d.objid=sc.oid AND d.deptype IN ('a','i') AND d.refclassid='pg_class'::regclass
   LEFT JOIN pg_class t ON t.oid=d.refobjid LEFT JOIN pg_namespace tn ON tn.oid=t.relnamespace
   WHERE s.schemaname = ANY(%s)""",
 "deps":    """SELECT DISTINCT vn.nspname, v.relname, v.relkind, tn.nspname, t.relname, t.relkind
   FROM pg_rewrite r JOIN pg_class v ON v.oid=r.ev_class JOIN pg_namespace vn ON vn.oid=v.relnamespace
   JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass AND d.refclassid='pg_class'::regclass
   JOIN pg_class t ON t.oid=d.refobjid AND t.oid<>v.oid JOIN pg_namespace tn ON tn.oid=t.relnamespace
   WHERE v.relkind IN ('v','m') AND t.relkind IN ('r','p','v','m') AND vn.nspname = ANY(%s)""",
}
PG_KIND = {"r": "TABLE", "p": "TABLE", "v": "VIEW", "m": "MATERIALIZED VIEW"}

def fetch_oracle(url, owners):
    import oracledb
    u = urlparse(url)
    con = oracledb.connect(user=unquote(u.username), password=unquote(u.password), dsn=f"{u.hostname}:{u.port or 1521}/{u.path.lstrip('/')}")
    cur = con.cursor(); cur.execute("SET TRANSACTION READ ONLY")
    ph = ",".join(f":o{i}" for i in range(len(owners))); b = {f"o{i}": o.upper() for i, o in enumerate(owners)}
    q = lambda k: cur.execute(ORACLE_SQL[k].format(owners=ph), b).fetchall()
    tables = [dict(schema=o, name=n, rows=r or 0, comment=c or "") for o, n, r, c in q("tables")]
    views = [dict(schema=o, name=n, comment=c or "") for o, n, c in q("views")]
    cols = [dict(schema=o, table=t, name=c, type=d, nullable=(nl == "Y"), pos=p) for o, t, c, d, nl, p in q("columns")]
    rows = q("keys"); pk, fkc, byname = {}, {}, {}
    for o, t, cn, ty, ro, rc, col, pos in rows:
        if ty == "P": pk.setdefault((o, t), []).append((pos, col)); byname[(o, cn)] = (o, t)
    for o, t, cn, ty, ro, rc, col, pos in rows:
        if ty == "R": fkc.setdefault((o, t, cn, ro, rc), []).append((pos, col))
    pks = [dict(schema=o, table=t, cols=[c for _, c in sorted(v)]) for (o, t), v in pk.items()]
    fks = []
    for (o, t, cn, ro, rc), v in fkc.items():
        rt = byname.get((ro, rc))
        if rt: fks.append(dict(schema=o, table=t, cols=[c for _, c in sorted(v)], r_schema=rt[0], r_table=rt[1], r_cols=[c for _, c in sorted(pk[rt])]))
    seqs = [dict(schema=o, name=n) for o, n in q("sequences")]
    trig = [dict(schema=o, name=n, table_schema=to, table=tn) for o, n, to, tn in q("triggers")]
    deps = [dict(schema=o, name=n, type=ty, r_schema=ro, r_name=rn, r_type=rt) for o, n, ty, ro, rn, rt in q("deps")]
    return dict(source="ORA", tables=tables, views=views, columns=cols, pks=pks, fks=fks, sequences=seqs, triggers=trig, deps=deps)

def fetch_postgres(url, schemas):
    import psycopg
    con = psycopg.connect(url, options="-c default_transaction_read_only=on -c statement_timeout=15000")
    cur = con.cursor(); q = lambda k: cur.execute(PG_SQL[k], (schemas,)).fetchall()
    tables, views = [], []
    for s, n, r, c, k in q("tables"):
        (tables if k in ("r", "p") else views).append(dict(schema=s, name=n, rows=max(r, 0), comment=c or ""))
    cols = [dict(schema=s, table=t, name=c, type=d, nullable=(nl == "YES"), pos=p) for s, t, c, d, nl, p in q("columns")]
    pks, fks = [], []
    for s, t, cn, ty, fs, ft, cc, fc in q("keys"):
        if ty == "p": pks.append(dict(schema=s, table=t, cols=list(cc)))
        else: fks.append(dict(schema=s, table=t, cols=list(cc), r_schema=fs, r_table=ft, r_cols=list(fc)))
    seqs = [dict(schema=s, name=n, table_schema=ts, table=tn, via="owned by column") for s, n, ts, tn in q("sequences")]
    deps = [dict(schema=vs, name=vn, type=PG_KIND[vk], r_schema=ts, r_name=tn, r_type=PG_KIND[tk]) for vs, vn, vk, ts, tn, tk in q("deps")]
    return dict(source="PG", tables=tables, views=views, columns=cols, pks=pks, fks=fks, sequences=seqs, triggers=[], deps=deps)

FAMILY = [("num", r"NUMBER|INT|NUMERIC|DECIMAL|FLOAT|DOUBLE|REAL"), ("str", r"CHAR|TEXT|CLOB"), ("time", r"DATE|TIME"), ("uuid", r"UUID")]
def family(t):
    for f, rx in FAMILY:
        if re.search(rx, t.upper()): return f
    return t.lower()

# EDIT ME: first matching rule wins. Colours the diagram by business area.
DOMAIN_RULES = [(r"CUSTOMER|ADDRESS|AGENT|PROFILE", "Customer"), (r"POLIC|COVERAGE|VEHICLE|QUOTE", "Policy"),
                (r"CLAIM", "Claims"), (r"BILL|PAYMENT", "Billing"), (r"LOOKUP|CODE", "Reference"), (r"NOTIFICATION|DOCUMENT", "Digital")]
def domain_of(name):
    for rx, d in DOMAIN_RULES:
        if re.search(rx, name.upper()): return d
    return "Other"

GENERIC = {"ID", "CODE", "NAME", "STATUS", "TYPE", "DESCR", "DESCRIPTION"}
def tid(src, schema, table): return f"{src}.{schema}.{table}"

def link_oracle_sequences(raw):
    """Sequence -> table via trigger dependencies. Pure function: returns a new sequence list."""
    trg = {(t["schema"], t["name"]): (t["table_schema"], t["table"]) for t in raw.get("triggers", [])}
    out, seen, linked = [], set(), set()
    for d in sorted(raw.get("deps", []), key=lambda x: (x["schema"], x["name"], x["r_schema"], x["r_name"])):
        if d["type"] == "TRIGGER" and d["r_type"] == "SEQUENCE" and (d["schema"], d["name"]) in trg:
            ts, tn = trg[(d["schema"], d["name"])]; key = (d["r_schema"], d["r_name"], ts, tn)
            if key not in seen:
                seen.add(key); linked.add((d["r_schema"], d["r_name"]))
                out.append(dict(schema=d["r_schema"], name=d["r_name"], table_schema=ts, table=tn, via="trigger " + d["name"]))
    for s in raw.get("sequences", []):
        if s.get("table"): out.append(s)
        elif (s["schema"], s["name"]) not in linked: out.append(dict(schema=s["schema"], name=s["name"], table=None))
    return out

def normalize(raw):
    src = raw["source"]; tabs = {}
    seq_rows = link_oracle_sequences(raw) if src == "ORA" else raw.get("sequences", [])
    def add(s, n, rows, comment, kind):
        tabs[(s, n)] = dict(id=tid(src, s, n), name=n, db=src, schema=s, kind=kind, rows=rows, comment=comment,
                            domain=domain_of(n), columns=[], sequences=[], sequence_details=[], dependents=[])
    for t in sorted(raw["tables"], key=lambda x: (x["schema"], x["name"])): add(t["schema"], t["name"], t["rows"], t["comment"], "table")
    for v in sorted(raw.get("views", []), key=lambda x: (x["schema"], x["name"])): add(v["schema"], v["name"], 0, v.get("comment", ""), "view")
    for c in sorted(raw["columns"], key=lambda x: (x["schema"], x["table"], x["pos"])):
        if (c["schema"], c["table"]) in tabs:
            tabs[(c["schema"], c["table"])]["columns"].append(dict(name=c["name"], type=c["type"], nullable=c["nullable"], pk=False))
    for p in raw["pks"]:
        t = tabs.get((p["schema"], p["table"]))
        for col in (t["columns"] if t else []):
            if col["name"] in p["cols"]: col["pk"] = True
    for s in sorted(seq_rows, key=lambda x: (x["schema"], x["name"], x.get("table") or "")):
        t = tabs.get((s.get("table_schema", s["schema"]), s["table"])) if s.get("table") else None
        if t and s["name"] not in t["sequences"]:
            t["sequences"].append(s["name"]); t["sequence_details"].append(dict(name=s["name"], via=s.get("via", "")))
    edges = []
    for f in sorted(raw["fks"], key=lambda x: (x["schema"], x["table"], x["cols"])):
        edges.append(dict(**{"from": tid(src, f["schema"], f["table"])}, fromCols=f["cols"], to=tid(src, f["r_schema"], f["r_table"]),
                          toCols=f["r_cols"], kind="declared", confidence=100, reasons=["declared foreign key constraint"]))
    seen = set()
    for d in sorted(raw.get("deps", []), key=lambda x: (x["schema"], x["name"], x["type"], x["r_schema"], x["r_name"])):
        tgt = tabs.get((d["r_schema"], d["r_name"]))
        if not tgt or d["r_type"] not in ("TABLE", "VIEW", "MATERIALIZED VIEW"): continue
        if d["type"] in ("VIEW", "MATERIALIZED VIEW"):
            v = tabs.get((d["schema"], d["name"]))
            if v and v is not tgt and (v["id"], tgt["id"]) not in seen:
                seen.add((v["id"], tgt["id"]))
                edges.append(dict(**{"from": v["id"]}, fromCols=[], to=tgt["id"], toCols=[], kind="dependency", confidence=100,
                                  reasons=["view definition reads from this object (catalog dependency)"]))
        elif d["type"] in ("PROCEDURE", "FUNCTION", "PACKAGE BODY", "TRIGGER"):
            item = dict(type="PACKAGE" if d["type"] == "PACKAGE BODY" else d["type"], name=d["name"])
            if item not in tgt["dependents"]: tgt["dependents"].append(item)
    for t in tabs.values(): t["dependents"].sort(key=lambda x: (x["type"], x["name"]))
    return list(tabs.values()), edges

def infer(tables, edges, threshold=70):
    declared = {(e["from"], tuple(e["fromCols"])) for e in edges}
    targets = {}
    for t in tables:
        if t["kind"] != "table": continue
        pk = [c for c in t["columns"] if c["pk"]]
        if len(pk) == 1 and (pk[0]["name"].upper() not in GENERIC or t["db"] == "PG"):
            targets.setdefault(pk[0]["name"].upper(), []).append((t, pk[0]))
    out = []
    for t in tables:
        if t["kind"] != "table": continue
        for c in t["columns"]:
            n = c["name"].upper()
            if c["pk"] or n in GENERIC or (t["id"], (c["name"],)) in declared: continue
            for tt, tc in targets.get(n, []):
                if tt["id"] == t["id"] or tt["db"] != t["db"]: continue
                score, why = 50, ["column name equals target primary key name"]
                if family(c["type"]) == family(tc["type"]): score += 20; why.append("compatible data types")
                score += 10; why.append("target has a single-column primary key")
                if re.search(r"(_ID|_NO|_CD|_KEY)$", n): score += 10; why.append("key-style suffix")
                if score >= threshold:
                    out.append(dict(**{"from": t["id"]}, fromCols=[c["name"]], to=tt["id"], toCols=[tc["name"]], kind="inferred", confidence=min(score, 99), reasons=why))
    return sorted(out, key=lambda e: (e["from"], e["fromCols"], e["to"]))

def manual_links(links):
    return [dict(**{"from": l["from"]}, fromCols=l["fromCols"], to=l["to"], toCols=l["toCols"], kind="manual", confidence=100,
                 reasons=["confirmed by a person" + (": " + l["note"] if l.get("note") else "")]) for l in links]

def build_model(raws, links):
    tables, edges = [], []
    for r in raws:
        t, e = normalize(r); tables += t; edges += e + infer(t, e)
    edges += manual_links(links)
    tables.sort(key=lambda t: t["id"]); edges.sort(key=lambda e: (e["kind"], e["from"], e["fromCols"], e["to"]))
    body = dict(tables=tables, edges=edges)
    fp = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    return dict(meta=dict(fingerprint=fp, schema_version=2, ai_used=False), **body)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle"); ap.add_argument("--owners", default=""); ap.add_argument("--postgres"); ap.add_argument("--schemas", default="public")
    ap.add_argument("--links"); ap.add_argument("--out", default="schema.json"); a = ap.parse_args(); raws = []
    if a.oracle: raws.append(fetch_oracle(a.oracle, a.owners.split(",")))
    if a.postgres: raws.append(fetch_postgres(a.postgres, a.schemas.split(",")))
    links = json.load(open(a.links)) if a.links else []
    json.dump(build_model(raws, links), open(a.out, "w"), indent=1, sort_keys=True); print("wrote", a.out)
