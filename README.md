# N.E.X.U.S.

**Network for ElevenLabs X-call User Scheduling**

Agentic Voice AI for autonomous appointment scheduling — built for the **CallPilot Challenge** (ElevenLabs). NEXUS orchestrates parallel voice agents that call providers, negotiate slots, check your calendar, and return a ranked shortlist for confirmation.

---

## Table of Contents

- [Motivation & Goal](#motivation--goal)
- [Core Features (MVP)](#core-features-mvp)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Repository Layout](#repository-layout)
- [Configuration](#configuration)
- [Development Setup](#development-setup)
- [Production Deployment](#production-deployment)
- [API Overview](#api-overview)
- [Workflow Diagrams](#workflow-diagrams)
- [Campaign State Machine (RFC)](#campaign-state-machine-rfc)
- [Evaluation Criteria](#evaluation-criteria)
- [Stretch Goals & Roadmap](#stretch-goals--roadmap)
- [License](#license)

---

## Motivation & Goal

Booking an appointment — at a doctor’s office, car repair shop, or hairdresser — is still one of the most time-consuming micro-tasks in daily life: call, wait on hold, negotiate a time, realize it doesn’t fit your calendar, call the next place, repeat. A single appointment can easily take 20–30 minutes.

**Goal:** Build an agentic Voice AI receptionist powered by ElevenLabs that:

- **Calls** service providers
- **Negotiates** appointment slots in natural conversation
- **Selects** the best match using calendar, location, and preferences
- **Uses** ElevenLabs Agentic Functions (tool calling) to orchestrate multi-call campaigns and decide in real time

NEXUS implements this as a production-ready system with a React dashboard, FastAPI backend, PostgreSQL, Redis, and optional Google Calendar + Places integration.

---

## Core Features (MVP)

| Challenge requirement | Implementation |
|----------------------|----------------|
| **2.1 Single-call booking** | User requests appointment via dashboard; agent calls provider via ElevenLabs; books slot; calendar integration (Google Calendar) checks availability in real time. |
| **2.2 Agentic Functions** | ElevenLabs tool calling: `check_availability`, `report_slot_offer`, `book_slot`, `end_call`, `get_distance`. Backend exposes `/api/check-availability`, `/api/book-slot`, etc.; agent asks clarifying questions and adapts. |
| **2.3 Multi-call parallel (“Swarm”)** | Up to 15 providers called in parallel; each call is an independent voice agent; results aggregated with scoring (earliest 50%, rating 30%, distance 20%); ranked shortlist returned for confirmation. |
| **2.4 Preference & calendar matching** | Real-time calendar checks prevent double booking; scoring uses rating, distance, and availability; user weighting configurable (RFC 3.2). |

---

## Architecture

### System overview

```
    +------------------+     +------------------+     +------------------+
    |   React SPA      |     |   FastAPI API    |     |  ElevenLabs      |
    |   (Vite)         |---->|   (nexus-api)    |     |  Conversational  |
    |   :5173          |     |   :8000          |     |  AI (Voice)      |
    +------------------+     +--------+---------+     +--------+---------+
             |                         |                       |
             |                         |                       |
             v                         v                       v
    +------------------+     +--------+---------+     +--------+---------+
    |   Browser        |     |  PostgreSQL     |     |  Twilio (outbound|
    |   Session cookie  |     |  (users,        |     |  calls to        |
    |   (OAuth)        |     |   campaigns,    |     |  providers or    |
    |                  |     |   call_tasks,   |     |  TARGET_PHONE)    |
    |                  |     |   appointments)|     +------------------+
    +------------------+     +--------+---------+
                                      |
                              +-------+-------+
                              |  Redis        |
                              |  (soft locks) |
                              +---------------+
```

### Component roles

- **Frontend:** Dashboard, auth (redirect to backend OAuth), campaign creation, live swarm view, appointment list, audit trail, settings. All secrets and API keys stay in backend/env.
- **Backend:** Auth (Google OAuth, session cookie), campaign CRUD, orchestration (intent analysis, provider lookup, spawn call tasks), tool endpoints for ElevenLabs, calendar and provider services.
- **ElevenLabs:** Voice agent; receives tool definitions and calls backend over HTTPS (ngrok/cloudflared in dev).
- **PostgreSQL:** Users, campaigns, call_tasks, appointments. Single source of truth.
- **Redis:** Soft-lock keys for slot holds (e.g. `hold:{user_id}:{date}:{time}`).

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Framer Motion, React Router v6, Lucide React |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic, structlog |
| **Voice & telephony** | ElevenLabs Conversational AI (agentic functions), Twilio (outbound) |
| **AI / orchestration** | OpenAI (intent analysis, brain instructions), ElevenLabs (voice + tools) |
| **Data** | PostgreSQL 15, Redis 7 |
| **Deployment** | Docker Compose (api, frontend, db, redis; optional ngrok/cloudflared profile) |

---

## Repository Layout

```
NEXUS-fork/
├── .env                    # Copy from .env.example; never commit secrets
├── .env.example             # Template with variable names only (no real secrets)
├── .gitignore
├── docker-compose.yml       # api, frontend, db, redis; optional expose profile
├── README.md                # This file
├── nexus-backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── poetry.lock
│   └── app/
│       ├── main.py          # FastAPI app, lifespan, CORS, health/ready
│       ├── config.py        # Pydantic Settings from env
│       ├── api/
│       │   ├── auth.py      # GET /api/auth/login, /api/auth/callback, session
│       │   └── routes.py    # Campaigns, tools, appointments, confirm, cancel
│       ├── core/
│       │   ├── database.py # User, Campaign, CallTask, Appointment; async engine
│       │   ├── redis.py
│       │   └── crypto.py   # Encrypt/decrypt refresh token
│       ├── models/
│       │   └── schemas.py   # Pydantic request/response models
│       ├── services/
│       │   ├── orchestrator.py  # create_campaign_and_swarm, state machine, call agents
│       │   ├── tools.py        # check_availability, report_slot_offer, book_slot, end_call
│       │   ├── calendar_service.py
│       │   ├── google_calendar.py
│       │   └── provider_service.py
│       └── utils/
│           └── date_parse.py
└── nexus-frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── index.css
        ├── lib/
        │   ├── api.ts       # api(), getLoginUrl(); uses VITE_API_URL
        │   └── entityExtract.ts
        ├── context/         # Auth, Theme, UserProfile, AuditTrail
        ├── components/      # NexusHeader, Layout, AuditTrailSidebar
        └── pages/           # Auth, Dashboard, CampaignDetail, Appointments, Settings, Admin
```

---

## Configuration

All configuration is via **environment variables**. No secrets are hardcoded in the repo; use a single `.env` at the repo root (copy from `.env.example` and fill in values).

### Required for minimal run

- `NEXUS_MODE` — `mock_human` | `mock_ai` | `live`
- `DATABASE_URL` — PostgreSQL (e.g. `postgresql+asyncpg://user:pass@host:5432/db`)
- `REDIS_URL` — Redis (e.g. `redis://host:6379/0`)
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (and `ELEVENLABS_AGENT_ID` for conversational agent)
- `OPENAI_API_KEY`
- For `mock_human`: `TARGET_PHONE_NUMBER` (E.164) so all outbound calls go to your phone for testing

### Optional

- **Google OAuth:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (or `GOOGLE_OAUTH_*`) for Sign in with Google and calendar.
- **Google APIs:** `GOOGLE_API_KEY` for Places / geocoding when not using mock providers.
- **Frontend:** `FRONTEND_ORIGIN` (e.g. `http://localhost:5173`) for CORS and post-login redirect.
- **Session:** `SESSION_SECRET_KEY`, `ENCRYPTION_KEY`; in production set these and use HTTPS.
- **Expose for ElevenLabs webhooks:** `NGROK_AUTHTOKEN` or run `docker compose --profile expose up` and use ngrok/cloudflared URL in ElevenLabs agent tools.

See `.env.example` for the full list and comments.

---

## Development Setup

### Prerequisites

- Docker and Docker Compose (or Node 20+, Python 3.12+, PostgreSQL 15, Redis 7 for local runs)
- Accounts and keys: Twilio, ElevenLabs, OpenAI; optional Google Cloud (OAuth + APIs)

### Steps

1. **Clone and enter repo**

   ```bash
   git clone <repo-url>
   cd NEXUS-fork
   ```

2. **Create environment file**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set at least:

   - `NEXUS_MODE=mock_human`
   - `DATABASE_URL`, `REDIS_URL` (for Docker use `nexus-db:5432` and `nexus-redis:6379` as in `.env.example`)
   - Twilio, ElevenLabs, OpenAI credentials
   - `TARGET_PHONE_NUMBER` (E.164) for mock_human
   - `FRONTEND_ORIGIN=http://localhost:5173`
   - For Google login: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (backend callback URL, e.g. `http://localhost:8000/api/auth/callback`)

3. **Start stack with Docker**

   ```bash
   docker compose up --build
   ```

   - API: **http://localhost:8000**
   - Frontend: **http://localhost:5173**
   - Docs: **http://localhost:8000/docs**

4. **Optional: expose API for ElevenLabs webhooks**

   ```bash
   docker compose --profile expose up
   ```

   Then inspect logs for ngrok/cloudflared URL and configure your ElevenLabs agent’s tool base URL to that HTTPS endpoint.

5. **Run frontend only (no Docker)**

   Backend must be running (e.g. Docker). From repo root:

   ```bash
   cd nexus-frontend
   npm install
   npm run dev
   ```

   Use `VITE_API_URL=http://localhost:8000` if the app is not proxying to the API.

6. **Run backend only (no Docker)**

   Set `DATABASE_URL` and `REDIS_URL` to your local Postgres and Redis. Then:

   ```bash
   cd nexus-backend
   poetry install
   poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

---

## Production Deployment

- Use a **single `.env`** (or secure secret store) with production values; never commit `.env`.
- Set **SESSION_SECRET_KEY** and **ENCRYPTION_KEY** to strong, unique values.
- Use **HTTPS** and set **SESSION_COOKIE_SECURE=True**; set **FRONTEND_ORIGIN** to your frontend URL.
- **Database:** Run migrations if you add any; ensure PostgreSQL and Redis are backed up and reachable.
- **Scaling:** Run multiple API workers behind a reverse proxy; share same PostgreSQL and Redis.
- **ElevenLabs:** Point agent tools to your public API URL (e.g. `https://api.yourdomain.com`).

---

## API Overview

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (DB + Redis) |
| GET | `/api/auth/login` | Redirect to Google OAuth |
| GET | `/api/auth/callback` | OAuth callback; upsert user; set session cookie |
| POST | `/api/campaigns` | Create campaign; spawn swarm (auth required) |
| GET | `/api/campaigns/{id}` | Campaign detail |
| GET | `/api/campaigns/{id}/stream` | SSE stream for live updates |
| GET | `/api/campaigns/{id}/results` | Ranked offers |
| POST | `/api/campaigns/{id}/confirm` | Confirm slot |
| POST | `/api/campaigns/{id}/cancel` | Cancel campaign |
| GET | `/api/appointments` | List appointments (auth required) |
| POST | `/api/check-availability` | Tool: check calendar and hold slot (ElevenLabs) |
| POST | `/api/book-slot` | Tool: confirm and book (ElevenLabs) |
| POST | `/api/report-slot-offer` | Tool: report offered slot (ElevenLabs) |
| POST | `/api/end-call` | Tool: end call (ElevenLabs) |
| POST | `/api/get-distance` | Tool: distance (ElevenLabs) |

All credentials and keys are read from the environment; nothing is hardcoded in the API.

---

## Workflow Diagrams

### User and auth flow (ASCII)

```
    User                Frontend              Backend               Google
      |                     |                     |                     |
      |  Click "Sign in"    |                     |                     |
      |-------------------->|                     |                     |
      |                     |  Redirect to        |                     |
      |                     |  /api/auth/login   |                     |
      |                     |-------------------->|                     |
      |                     |                     |  Redirect to       |
      |                     |                     |  Google OAuth      |
      |                     |                     |-------------------->|
      |                     |                     |                     |
      |  User consents      |                     |                     |
      |<--------------------------------------------------------------|
      |                     |                     |  Callback + code    |
      |                     |                     |<--------------------|
      |                     |                     |  Token exchange    |
      |                     |                     |  UserInfo          |
      |                     |                     |  Upsert User,       |
      |                     |                     |  set session cookie |
      |                     |                     |                     |
      |  Redirect to        |                     |                     |
      |  FRONTEND_ORIGIN    |                     |                     |
      |<--------------------|                     |                     |
      |                     |  (Cookie sent on    |                     |
      |                     |   subsequent API    |                     |
      |                     |   requests)         |                     |
```

### Campaign creation and swarm flow (ASCII)

```
    User                Frontend              Backend                ElevenLabs
      |                     |                     |                        |
      |  "Find dentist      |                     |                        |
      |   next Tuesday"     |                     |                        |
      |-------------------->|  POST /campaigns    |                        |
      |                     |  (session cookie)  |                        |
      |                     |-------------------->|                        |
      |                     |                     |  Validate user in DB   |
      |                     |                     |  Insert Campaign      |
      |                     |                     |  CREATED ->           |
      |                     |                     |  PROVIDER_LOOKUP      |
      |                     |                     |  Intent (OpenAI)      |
      |                     |                     |  Provider list        |
      |                     |                     |  DIALING              |
      |                     |                     |  Spawn 15 call tasks  |
      |                     |                     |  (Twilio outbound     |
      |                     |                     |   to providers or     |
      |                     |                     |   TARGET_PHONE)       |
      |                     |                     |------------------------->|
      |                     |                     |                        | Voice
      |                     |  SwarmPlan          |                        | agents
      |                     |<--------------------|                        | call
      |  Redirect to        |                     |                        | tools
      |  /campaigns/:id     |                     |<------------------------|
      |<--------------------|                     |  POST /check-availability
      |                     |                     |  POST /report-slot-offer
      |                     |                     |  POST /book-slot      |
      |                     |                     |  POST /end-call       |
```

### Agentic tool flow (ASCII)

```
    ElevenLabs Agent           Backend API                PostgreSQL / Redis
    (during voice call)             |                              |
            |                       |                              |
            |  POST /check-availability                             |
            |  (date, time, user_id, campaign_id, call_task_id)     |
            |---------------------->|  check_and_hold_slot         |
            |                       |  (calendar conflict,         |
            |                       |   Redis soft lock)           |
            |                       |----------------------------->|
            |                       |<-----------------------------|
            |  JSON: held | conflict|                              |
            |<----------------------|                              |
            |                       |                              |
            |  POST /report-slot-offer (provider, date, time)      |
            |---------------------->|  Update CallTask, score,     |
            |                       |  campaign -> RANKING          |
            |                       |----------------------------->|
            |  JSON: ranking_position                              |
            |<----------------------|                              |
            |                       |                              |
            |  POST /book-slot (...) |  confirm_and_book            |
            |---------------------->|  (calendar + DB appointment)  |
            |                       |----------------------------->|
            |  JSON: success        |<-----------------------------|
            |<----------------------|                              |
            |  POST /end-call       |  Update CallTask status      |
            |---------------------->|----------------------------->|
```

---

## Campaign State Machine (RFC)

Campaign status is driven by the orchestrator (RFC 3.1). Transitions:

```
    CREATED
        |
        v
    PROVIDER_LOOKUP   (intent analysis, provider search)
        |
        v
    DIALING          (spawn call tasks; Twilio outbound)
        |
        v
    NEGOTIATING      (agents in call)
        |
        v
    RANKING          (slot offers reported; scores computed)
        |
        v
    CONFIRMED        (user confirmed a slot; book_slot succeeded)
```

Alternative terminal states: **FAILED**, **CANCELLED**.

Match quality (Challenge 2.3): **Earliest 50%**, **Rating 30%**, **Proximity 20%** (configurable weights in DB).

---

## Evaluation Criteria

| Criterion | How NEXUS addresses it |
|-----------|--------------------------|
| **Conversational quality** | ElevenLabs Conversational AI; low-latency tool responses; backend timeouts (e.g. 10s) to keep agent responsive. |
| **Agentic functions** | Full tool orchestration: check_availability, report_slot_offer, book_slot, end_call, get_distance; agent instructions enforce order and calendar/booking consistency. |
| **Optimal match quality** | Weighted scoring (time, rating, distance); ranked shortlist; user confirms one slot; calendar prevents double booking. |
| **Parallelization** | Up to 15 concurrent call tasks per campaign; each task independent; failures don’t block others; stale campaign monitor for cleanup. |
| **User experience** | Single flow: describe request → initiate swarm → watch live status → see ranked offers → confirm → view appointments; Google sign-in; audit trail and settings. |

---

## Stretch Goals & Roadmap

- **Multilingual:** Language detection and per-call language (future).
- **Rescheduling / cancellation:** Agent flows for “reschedule” or “cancel” (future).
- **Live user-in-the-loop:** Transcript streaming and “intervene” already in UI; deeper control (future).
- **Hallucination-aware handover:** Confidence thresholds and handoff to human (future).
- **Domain experts:** Routed expert agents (future).
- **Waitlist & retry:** Waitlist registration and retry when slots open (future).

---

## License

See [LICENSE](LICENSE) in the repository.

---

**NEXUS** — *Network for ElevenLabs X-call User Scheduling* — CallPilot Challenge (ElevenLabs). No secrets in code; configure via `.env` only.
