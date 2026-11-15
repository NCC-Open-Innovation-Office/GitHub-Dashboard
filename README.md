# GitHub-Dashboard

A dashboard to show the engagement of students on GitHub at an academic institution. It provides insights into organization-level metrics, repository activity, contributors, and commit trends.

## Features

- **Organization Overview**: Real-time stats for the GitHub organization.
- **Activity Feed**: Track recent events across all repositories.
- **Contributor Analytics**: Visualize contribution distributions.
- **Commit Trends**: Monitor activity over time.
- **Optimized for Large Orgs**: Handles organizations with many repositories through efficient caching.
- **Database-backed Stats Cache**: API responses are served from a local SQLite cache refreshed in the background.

## Tech Stack

- **Backend**: FastAPI (Python 3.12+)
- **Frontend**: React, Vite, Tailwind CSS, Recharts
- **Containerization**: Docker, Docker Compose
- **Proxy/Web Server**: Nginx

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- A [GitHub Personal Access Token (classic)](https://github.com/settings/tokens) with `repo` and `read:org` scopes.

## Setup & Run

### 1. Environment Configuration

Create a `.env` file in the root directory (refer to [backend/.env.example](backend/.env.example) if it exists, or use the template below):

```env
GITHUB_TOKEN=your_github_token_here
GITHUB_ORG=your_organization_name
CACHE_TTL_SECONDS=300
MAX_REPOS=1000
STATS_DB_PATH=data/stats_cache.db
STARTUP_FULL_REFRESH=false
MEMBER_WIDE_MODE_ENABLED=false
MEMBER_WIDE_MAX_MEMBERS=250
MEMBER_WIDE_REPO_LIMIT_PER_MEMBER=100
```

### 2. Run with Docker Compose

To start the entire stack (Production-like):

```bash
docker-compose up --build
```

The dashboard will be available at [http://localhost:3000](http://localhost:3000).

### 3. Development Mode

To run with hot-reload enabled for the backend:

```bash
docker-compose -f docker-compose.dev.yml up --build
```

The backend API will be available at [http://localhost:8000](http://localhost:8000).

## Production Deployment

The repository includes a GitHub Actions workflow that builds the backend image
and pushes it to GitHub Container Registry as `ghcr.io/ncc-open-innovation-office/github-dashboard:latest`
on every push to `main`.

To deploy from the published image instead of rebuilding locally, use:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The production compose file uses the GHCR image directly and maps the app to
`http://localhost:3000`.

If your GHCR package is private, log in first:

```bash
docker login ghcr.io
```

You can also trigger the image build manually from the Actions tab using the
`Build and Push Docker Image` workflow.

## Scripts & Development

### Backend (FastAPI)
- **Run Locally**: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
- **API Docs**: Once running, visit [http://localhost:8000/docs](http://localhost:8000/docs) for the Swagger UI.
- **Smoke Test**: `./scripts/smoke-test.ps1`

### Frontend (React + Vite)
- **Install**: `cd frontend && npm install`
- **Dev Server**: `npm run dev`
- **Build**: `npm run build`

## Project Structure

```text
├── backend/            # FastAPI application
│   ├── app/            # Source code
│   │   ├── routers/    # API endpoints
│   │   ├── services/   # Business logic (GitHub API, caching)
│   │   └── main.py     # Application entry point
│   └── static/         # Vanilla JS fallback frontend
├── frontend/           # React application
│   ├── src/            # Components and services
│   └── index.html      # Main HTML entry
├── docker-compose.yml  # Production deployment
├── docker-compose.prod.yml # Production deployment from GHCR
├── .github/workflows/  # CI/CD workflows
└── todo.md             # Project roadmap
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_TOKEN` | GitHub PAT with repo/read:org scope | **Required** |
| `GITHUB_ORG` | The GitHub organization to track | **Required** |
| `CACHE_TTL_SECONDS` | General cache expiration | 300 |
| `MAX_REPOS` | Max repositories to fetch | 1000 |
| `STATS_DB_PATH` | SQLite path for persisted stats cache | `data/stats_cache.db` |
| `STARTUP_FULL_REFRESH` | If true, enqueue full refresh on app startup | `false` |
| `MEMBER_WIDE_MODE_ENABLED` | Enable member-wide stats mode | `false` |
| `MEMBER_WIDE_MAX_MEMBERS` | Max org members scanned for member-wide stats | `250` |
| `MEMBER_WIDE_REPO_LIMIT_PER_MEMBER` | Max repos fetched per scanned member | `100` |

## Admin Diagnostics

- Cache status overview: `GET /api/debug/cache-stats`
- Cache age/expiry per dataset: `GET /api/debug/cache-age`

### Optional Member-wide Stats

- Org-only contributors (default): `GET /api/contributors`
- Member-wide stats: `GET /api/contributors/member-wide`

Member-wide mode is opt-in and uses current org members as the subject set,
then aggregates stats across repositories visible to the configured token.
Private repositories outside token visibility are excluded.

The cache-age endpoint reports whether each dataset is present in the
persistent cache plus update age and expiry timing metadata.

## Tests

- TODO: Add backend unit tests using pytest.
- TODO: Add frontend component tests using Vitest or Jest.

## License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
