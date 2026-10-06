# AI Memory Engine

Your Personal Second Brain.

AI Memory Engine is a context-aware personal knowledge system. Phase 1 establishes the production foundation: Docker services, FastAPI, PostgreSQL with pgvector, Neo4j connectivity settings, Alembic migrations, JWT authentication, password hashing, and a strict Next.js app shell.

## Architecture

- `backend/`: FastAPI API, SQLAlchemy models, Alembic migrations, service-oriented auth.
- `frontend/`: Next.js, React, TypeScript, Tailwind CSS application shell.
- `docker-compose.yml`: PostgreSQL + pgvector, Neo4j, Redis, and backend.

All user-owned data models include `user_id` where applicable. API routes that access user-owned data must depend on the authenticated user and scope queries by that ID.

## Prerequisites

- Docker Desktop
- Python 3.12+
- Node.js 20+

## Environment Setup

Copy `.env.example` to `.env` and replace secrets:

```bash
cp .env.example .env
```

Use a long random `JWT_SECRET`. API keys are read only by the backend and must never be exposed through frontend environment variables.

## Docker Setup

```bash
docker compose up postgres neo4j redis
```

Run migrations:

```bash
cd backend
alembic upgrade head
```

Run the backend:

```bash
uvicorn app.main:app --reload
```

Or run the backend through Docker:

```bash
docker compose up backend
```

Swagger API documentation is available at `http://localhost:8000/docs`.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Testing

Backend:

```bash
cd backend
pip install -e ".[dev]"
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run test
```

## Phase 1 Status

Implemented:

- Project structure
- Docker Compose
- PostgreSQL models and indexes
- Alembic migration
- JWT registration, login, and `/auth/me`
- Secure password hashing with bcrypt
- Protected route dependency
- Centralized API error handling
- Frontend auth shell
- Backend auth tests

Next phase: document upload, extraction, chunking, and PostgreSQL storage.
