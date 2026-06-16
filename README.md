# GitHub-Dashboard

A dashboard to show the engagement of students on GitHub at an academic institution. It provides insights into organization-level metrics, repository activity, contributors, and commit trends.

## Features

- **Organization Overview**: Real-time stats for the GitHub organization.
- **Activity Feed**: Track recent events across all repositories.
- **Contributor Analytics**: Visualize contribution distributions.
- **Commit Trends**: Monitor activity over time.
- **Optimized for Large Orgs**: Handles organizations with many repositories through efficient caching.

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

## Scripts & Development

### Backend (FastAPI)
- **Run Locally**: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
- **API Docs**: Once running, visit [http://localhost:8000/docs](http://localhost:8000/docs) for the Swagger UI.

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
└── todo.md             # Project roadmap
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_TOKEN` | GitHub PAT with repo/read:org scope | **Required** |
| `GITHUB_ORG` | The GitHub organization to track | **Required** |
| `CACHE_TTL_SECONDS` | General cache expiration | 300 |
| `MAX_REPOS` | Max repositories to fetch | 1000 |

## Tests

- TODO: Add backend unit tests using pytest.
- TODO: Add frontend component tests using Vitest or Jest.

## License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
