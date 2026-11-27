# Security checklist

## Database account
Create a dedicated read-only user.
- **Postgres:** `CREATE ROLE atlas LOGIN PASSWORD '...'; GRANT CONNECT ON DATABASE app TO atlas; GRANT USAGE ON SCHEMA public TO atlas;` (catalog reads work without table SELECT, but row estimates may be limited).
- **Oracle:** `CREATE USER atlas IDENTIFIED BY "..."; GRANT CREATE SESSION TO atlas;` then grant `SELECT_CATALOG_ROLE` or per-object access so `ALL_*` views show the schema objects. Do not grant DBA or RESOURCE.
- Remember `ALL_DEPENDENCIES` only shows objects the account can see.

## Service
- Serve over HTTPS only; credentials travel in the request.
- Put it behind company sign-in before sharing. The prototype has none.
- Keep `ALLOWED_HOSTS` to the databases you intend; the default allows only localhost. This prevents the tool being used to probe internal networks.
- Never log request bodies. Error messages mask the user and password.
- Run the server in a network zone that can reach the databases but not the internet.

## Data handling
- The extractor reads structure only, never rows.
- `schema.json` still reveals your table and column names, so treat it as internal.
- If AI is added, send only extracted facts, use a vendor approved by your company, and keep the exact payload visible to the user.
