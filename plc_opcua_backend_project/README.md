# PLC OPC UA Monitoring Backend

A starter project for a **read-only** Siemens PLC monitoring pipeline:

`PLC → OPC UA server → Python OPC UA collector → PostgreSQL → FastAPI → Dashboard`

This project does not write values to the PLC. Have your PLC/OT engineer approve the endpoint, certificates, security policy, and NodeIds before connecting to a production machine.

## 1. Requirements

- Windows 10/11 or Windows Server
- Python 3.12 or 3.13 recommended for broad dependency compatibility
- PostgreSQL installed and running (local or reachable server)
- OPC UA endpoint and approved certificates from the PLC/OT engineer
- Exact NodeIds for the machine variables to monitor

Python 3.14 may work depending on package-wheel availability. If installation fails, use Python 3.12 or 3.13 for this project.

## 2. Create and activate a virtual environment

Open PowerShell in the project folder:

```powershell
cd C:\Users\Sahil\plc_opcua_backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If Python 3.12 is not installed, install it or use `py -3.13` instead. Do not mix global Python packages with this project's virtual environment.

## 3. Configure environment

Copy the example environment file:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `DATABASE_URL`, OPC UA endpoint, certificate paths, credentials if required, and the comma-separated `OPCUA_NODE_IDS`.

Certificate paths are relative to the project root unless absolute paths are supplied. Put approved certificate/key files in `certificates\` or update the paths.

Example NodeIds in `.env.example` are illustrative only. Do not use them as real machine NodeIds unless your PLC engineer confirms them.

If a password contains URL-reserved characters (for example `@`, `:`, `/`, or `#`), URL-encode those characters in `DATABASE_URL`.

## 4. Create PostgreSQL database and user

Use pgAdmin's Query Tool while connected as a PostgreSQL administrator, or use `psql`. Replace the example password with a strong unique password. Run these statements as separate commands if your SQL client does not allow `CREATE DATABASE` inside a transaction:

```sql
CREATE USER plc_app WITH PASSWORD 'REPLACE_WITH_A_STRONG_PASSWORD';
CREATE DATABASE plc_monitoring OWNER plc_app;
```

Then set `DATABASE_URL` in `.env` to match that password.

The application creates its initial `readings` table on startup. For production deployments, use a migration tool such as Alembic rather than relying on automatic table creation.

## 5. Start the API

From the project root, with `.venv` activated:

```powershell
python -m uvicorn app.main:app --reload
```

Open:
- API home: http://127.0.0.1:8000/
- Swagger documentation: http://127.0.0.1:8000/docs
- Dashboard: http://127.0.0.1:8000/dashboard/
- Database health: http://127.0.0.1:8000/health/db

The API can start with the collector disabled if `OPCUA_NODE_IDS` is blank. This lets you test the API/database before the PLC details are ready.

## 6. Configure OPC UA

Your PLC/OT engineer must provide/confirm:
- OPC UA endpoint reachable from this PC
- Approved client certificate and private key
- Trusted server certificate in a format supported by the installed `asyncua` version
- Security policy and message security mode
- Username/password, if required
- Exact NodeIds and their meanings

The starter uses `Basic256Sha256` with `SignAndEncrypt`. Change that only to a policy approved by your OT/security team and supported by the server and library. The configured certificate paths must exist.

Once the endpoint, certificates, and NodeIds are configured, restart the API. The collector will connect, subscribe to the configured nodes, and retry after connection failures.

## 7. API endpoints

- `GET /` — service information
- `GET /health/db` — database connectivity
- `GET /plc/test` — read-only OPC UA server-time test (node `i=2258`; this is not a machine variable)
- `GET /readings/latest?limit=100` — latest stored readings
- `GET /readings/history?node_id=ns%3D3%3Bs%3DMachine.Speed&limit=100` — recent history for one NodeId

## 8. Dashboard

The included dashboard is a minimal same-origin HTML page that refreshes readings every 3 seconds. It displays the most recent stored values; it does not itself connect to the PLC.

## 9. Security and production notes

- Keep `.env`, private keys, and passwords out of Git and shared archives.
- Do not expose OPC UA or the API to the public internet.
- Use network segmentation/firewall rules and least-privilege database permissions.
- The collector is read-only; no PLC write functionality is implemented.
- Test with a non-production PLC or approved test endpoint first.
- Before Windows-service deployment, disable development reload, configure service recovery, rotate logs, monitor service health, and decide retention/backup policies.
- This is a starter implementation, not a certified industrial control system. Validate behavior with your OT engineer before production use.
