# GitHub-Dashboard

A dashboard to show the engagement of students on GitHub at an academic institution. It provides insights into organization-level metrics, repository activity, contributors, and commit trends.

## Features

- **Organization Overview**: Real-time stats for the GitHub organization.
- **Activity Feed**: Track public repository events, with optional private/internal activity for protected deployments.
- **Contributor Analytics**: See the top 10 contributors and their profile pictures on the home and TV screens.
- **Commit Trends**: Monitor activity over time.
- **Public Data by Default**: Anonymous dashboard APIs expose public data unless restricted activity or the member leaderboard is explicitly enabled.
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
| `INCLUDE_PRIVATE_ACTIVITY` | Include private/internal repository activity in the unauthenticated activity API | `false` |
| `MEMBER_CONTRIBUTION_LEADERBOARD` | Rank organization members by GitHub-wide contribution-calendar totals | `false` |

### Private activity

Only set `INCLUDE_PRIVATE_ACTIVITY=true` after protecting **both** the dashboard
and `/api/activity` with deployment-level access controls. The application does
not authenticate visitors. Anyone who can reach the API can see private and
internal repository names, authors, commit messages, and issue/PR titles.
The configured GitHub token must have access to those repositories, including
any required SSO authorization.

The feed combines public events with GitHub search results for commits and
newly opened issues and pull requests in private and internal repositories.
Search indexing can be delayed, results are limited to what the token can
access, commit searches cover only default branches and use commit dates rather
than push dates, and other private event
types (such as reviews and releases) are not included. Internal commit searches
depend on the repository scan and its `MAX_REPOS` limit. Private activity is
stored in the local SQLite cache; secure the
cache and its backups as well. Disabling the setting stops serving that cache
but does not erase it.

### GitHub-wide member leaderboard

Set `MEMBER_CONTRIBUTION_LEADERBOARD=true` only when the dashboard and
`/api/contributors` are protected by deployment-level access controls. The API
does not authenticate visitors and this mode can disclose private organization
membership and activity totals. Secure the SQLite cache and backups; disabling
the setting stops serving the member cache but does not erase it.

This mode ranks organization members by their GitHub contribution-calendar
totals for the last 12 months, rather than commits in organization repositories.
GitHub token permissions and each user's privacy settings can limit the members
and contributions visible. A classic token needs `read:org` to list private
members and may require `read:user` and SSO authorization. Contribution
calendar totals follow GitHub's rules and are not a complete count of all
possible GitHub activity. The top 10 appear on both home and TV screens.

## Admin Diagnostics

Debug and member-wide statistics endpoints are not exposed by the public
dashboard. `/api/health` is available for service health checks.

## Tests

- TODO: Add backend unit tests using pytest.
- TODO: Add frontend component tests using Vitest or Jest.

## License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
