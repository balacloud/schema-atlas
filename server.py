"""Intake API for Schema Atlas. Credentials live in memory for one request only: never stored, never logged.
Run:  pip install -r requirements.txt   then   ALLOWED_HOSTS=db1.corp,db2.corp python server.py   ->  http://localhost:8000
"""
import os, re
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import extractor as X

app = FastAPI()
HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED = [h.strip().lower() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()] or ["localhost", "127.0.0.1"]
SUPPORTED = {"oracle", "postgres"}
PREFIXES = [("oracle://", "oracle"), ("postgresql://", "postgres"), ("postgres://", "postgres"),
            ("mongodb+srv://", "mongodb"), ("mongodb://", "mongodb"), ("mysql://", "mysql")]

class Req(BaseModel):
    url: str
    type: str | None = None
    owners: str = ""
    schemas: str = "public"

def detect(url: str):
    u = url.strip().lower()
    for p, t in PREFIXES:
        if u.startswith(p): return t
    if u.startswith(("http://", "https://")) and "graphql" in u: return "graphql"
    return None

def check_host(url: str):
    host = (urlparse(url).hostname or "").lower()
    if not host: raise HTTPException(400, "That does not look like a valid connection string.")
    if host not in ALLOWED: raise HTTPException(403, f"Host '{host}' is not on the allowed list (set ALLOWED_HOSTS).")

SAFE_ORACLE = {"CREATE SESSION", "SET CONTAINER"}
RISKY_ORACLE = re.compile(r"^(CREATE|ALTER|DROP|INSERT ANY|UPDATE ANY|DELETE ANY|EXECUTE ANY|GRANT ANY|DBA|SYSDBA)", re.I)
def evaluate_privileges(kind: str, f: dict) -> dict:
    warn = []
    if kind == "postgres":
        if f.get("superuser"): warn.append("This account is a superuser.")
        if f.get("can_create"): warn.append("This account can create objects in the database.")
        if f.get("write_grants", 0): warn.append(f"This account has {f['write_grants']} INSERT/UPDATE/DELETE grants.")
    else:
        bad = sorted({p for p in f.get("sys_privs", []) if RISKY_ORACLE.match(p) and p.upper() not in SAFE_ORACLE})
        if bad: warn.append("Powerful system privileges: " + ", ".join(bad[:6]) + ("…" if len(bad) > 6 else ""))
        if {"DBA", "RESOURCE"} & {r.upper() for r in f.get("roles", [])}: warn.append("This account holds the DBA or RESOURCE role.")
        if f.get("write_grants", 0): warn.append(f"This account has {f['write_grants']} INSERT/UPDATE/DELETE grants.")
    return dict(read_only=not warn, warnings=warn)

def probe_postgres(url):
    import psycopg
    with psycopg.connect(url, connect_timeout=8, options="-c default_transaction_read_only=on -c statement_timeout=8000") as c:
        cur = c.cursor()
        sup = cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user").fetchone()[0]
        cr = cur.execute("SELECT has_database_privilege(current_user, current_database(), 'CREATE')").fetchone()[0]
        wg = cur.execute("SELECT count(*) FROM information_schema.table_privileges WHERE grantee=current_user AND privilege_type IN ('INSERT','UPDATE','DELETE')").fetchone()[0]
        n = cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')").fetchone()[0]
    return dict(superuser=sup, can_create=cr, write_grants=wg), n

def probe_oracle(url):
    import oracledb
    u = urlparse(url)
    c = oracledb.connect(user=u.username, password=u.password, dsn=f"{u.hostname}:{u.port or 1521}/{u.path.lstrip('/')}", tcp_connect_timeout=8)
    cur = c.cursor()
    privs = [r[0] for r in cur.execute("SELECT privilege FROM session_privs")]
    roles = [r[0] for r in cur.execute("SELECT role FROM session_roles")]
    wg = cur.execute("SELECT COUNT(*) FROM user_tab_privs WHERE grantee=USER AND privilege IN ('INSERT','UPDATE','DELETE')").fetchone()[0]
    n = cur.execute("SELECT COUNT(*) FROM all_tables").fetchone()[0]; c.close()
    return dict(sys_privs=privs, roles=roles, write_grants=wg), n

def resolve(req: Req):
    kind = req.type or detect(req.url)
    if kind not in SUPPORTED: raise HTTPException(400, f"'{kind}' is not supported yet. Supported now: Oracle and PostgreSQL.")
    check_host(req.url); return kind

def safe(fn):
    try: return fn()
    except HTTPException: raise
    except Exception as e: raise HTTPException(502, "Could not connect: " + re.sub(r"://[^@\s]*@", "://***@", str(e))[:300])

@app.post("/api/detect")
def api_detect(req: Req):
    t = detect(req.url); return dict(type=t, supported=t in SUPPORTED)

@app.post("/api/test")
def api_test(req: Req):
    kind = resolve(req)
    facts, n = safe(lambda: probe_postgres(req.url) if kind == "postgres" else probe_oracle(req.url))
    return dict(type=kind, reachable=True, tables_visible=n, **evaluate_privileges(kind, facts))

@app.post("/api/extract")
def api_extract(req: Req):
    kind = resolve(req)
    def run():
        raw = X.fetch_postgres(req.url, req.schemas.split(",")) if kind == "postgres" else X.fetch_oracle(req.url, [o for o in req.owners.split(",") if o])
        return X.build_model([raw], [])
    return safe(run)

@app.get("/", response_class=HTMLResponse)
def home(): return open(os.path.join(HERE, "intake.html"), encoding="utf-8").read()

@app.get("/atlas", response_class=HTMLResponse)
def atlas(): return open(os.path.join(HERE, "schema_atlas.html"), encoding="utf-8").read()

if __name__ == "__main__":
    import uvicorn; uvicorn.run(app, host="127.0.0.1", port=8000)
