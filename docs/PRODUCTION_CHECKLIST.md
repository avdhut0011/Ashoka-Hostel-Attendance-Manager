# Production checklist

Follow LOCAL_PRODUCTION_DEPLOYMENT.md for the current local-server deployment.

- Install the locked runtime into .venv-production; build with npm ci and npm run build.
- Preserve the session duration and keep backend/.env private.
- Configure explicit LAN host/origin values and production mode.
- Use only the guarded schema-only migration runner for existing HostelAttendance. Never reset checkpoints, seed users, or rewrite attendance to deploy this update.
- Epush must remain SELECT-only. Verify database grants when administrative access is available.
- Supervise API and worker separately; check WebSockets, worker lag, account scope, and exports after the scheduled restart.
- Verify backup restoration, SQL memory headroom, disk capacity, log rotation, and the real 15-user workload.
- Resolve documented HTTP/SQL certificate limitations before claiming verified encrypted transport.
