# NEXUS
N.E.X.U.S: Network for ElevenLabs X-call User Scheduling.

## Repository layout

- **Root** — `.cursorrules`, `docker-compose.yml`, `.env.example`, `.gitignore`. Run `docker compose up` from here; use a single `.env` at root (copy from `.env.example`).
- **`nexus-backend/`** — FastAPI backend (Poetry, Dockerfile, `pyproject.toml`, `app/`). See [README_BACKEND.md](README_BACKEND.md) for setup.
- **`docs/`** — Architecture and design docs.
