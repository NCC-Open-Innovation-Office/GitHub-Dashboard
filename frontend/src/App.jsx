import { useState, useEffect, useCallback } from 'react'
import { FiRefreshCw, FiGithub } from 'react-icons/fi'
import {
  getOrg,
  getRepos,
  getContributors,
  getActivity,
  getCommitActivity,
  refreshOrg,
  refreshRepos,
  refreshContributors,
  refreshActivity,
  refreshCommitActivity,
} from './services/api'
import OrgHeader from './components/OrgHeader'
import StatsGrid from './components/StatsGrid'
import RepoTable from './components/RepoTable'
import ContributorsChart from './components/ContributorsChart'
import CommitActivity from './components/CommitActivity'
import ActivityFeed from './components/ActivityFeed'
import LoadingSpinner from './components/LoadingSpinner'
import ErrorBanner from './components/ErrorBanner'

function useRemoteData(fetchFn) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(
    async (fn) => {
      setLoading(true)
      setError(null)
      try {
        const res = await fn()
        setData(res.data)
      } catch (err) {
        setError(err?.response?.data?.detail ?? err.message ?? 'Unknown error')
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    load(fetchFn)
  }, [])

  return { data, loading, error, reload: (refreshFn) => load(refreshFn) }
}

function Section({ title, loading, error, children, onRefresh, refreshing }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          {title}
        </h2>
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            title="Refresh this section"
            className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200 disabled:opacity-40"
          >
            <FiRefreshCw className={`text-sm ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>
      {error ? (
        <ErrorBanner message={error} />
      ) : loading ? (
        <LoadingSpinner />
      ) : (
        children
      )}
    </div>
  )
}

export default function App() {
  const org = useRemoteData(getOrg)
  const repos = useRemoteData(getRepos)
  const contributors = useRemoteData(getContributors)
  const activity = useRemoteData(getActivity)
  const commitActivity = useRemoteData(getCommitActivity)

  const [globalRefreshing, setGlobalRefreshing] = useState(false)

  const refreshAll = async () => {
    setGlobalRefreshing(true)
    await Promise.allSettled([
      org.reload(refreshOrg),
      repos.reload(refreshRepos),
      contributors.reload(refreshContributors),
      activity.reload(refreshActivity),
      commitActivity.reload(refreshCommitActivity),
    ])
    setGlobalRefreshing(false)
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* Top nav */}
      <nav className="sticky top-0 z-10 border-b border-slate-700 bg-slate-900/95 backdrop-blur">
        <div className="mx-auto flex max-w-screen-2xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2 text-slate-300">
            <FiGithub className="text-xl" />
            <span className="font-semibold">Org Dashboard</span>
            {org.data && (
              <span className="text-slate-500">/ {org.data.login}</span>
            )}
          </div>
          <button
            onClick={refreshAll}
            disabled={globalRefreshing}
            className="flex items-center gap-2 rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-300 transition-colors hover:border-indigo-500 hover:text-indigo-300 disabled:opacity-40"
          >
            <FiRefreshCw className={globalRefreshing ? 'animate-spin' : ''} />
            Refresh All
          </button>
        </div>
      </nav>

      <main className="mx-auto max-w-screen-2xl space-y-5 px-6 py-6">
        {/* Org header */}
        {org.error ? (
          <ErrorBanner message={`Could not load organization: ${org.error}`} />
        ) : org.loading ? (
          <LoadingSpinner label="Loading organization…" />
        ) : (
          org.data && <OrgHeader org={org.data} />
        )}

        {/* Stats cards */}
        <StatsGrid
          org={org.data}
          repos={repos.data}
        />

        {/* Commit activity chart — full width */}
        {(commitActivity.data || commitActivity.loading || commitActivity.error) && (
          <Section
            title="Commit Activity"
            loading={commitActivity.loading}
            error={commitActivity.error}
            onRefresh={() => commitActivity.reload(refreshCommitActivity)}
            refreshing={commitActivity.loading}
          >
            <CommitActivity data={commitActivity.data} />
          </Section>
        )}

        {/* Repos + Contributors side by side */}
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <Section
              title="Repositories"
              loading={repos.loading}
              error={repos.error}
              onRefresh={() => repos.reload(refreshRepos)}
              refreshing={repos.loading}
            >
              <RepoTable repos={repos.data?.repos} />
            </Section>
          </div>

          <Section
            title="Top Contributors"
            loading={contributors.loading}
            error={contributors.error}
            onRefresh={() => contributors.reload(refreshContributors)}
            refreshing={contributors.loading}
          >
            <ContributorsChart data={contributors.data} />
          </Section>
        </div>

        {/* Activity feed */}
        <Section
          title="Recent Activity"
          loading={activity.loading}
          error={activity.error}
          onRefresh={() => activity.reload(refreshActivity)}
          refreshing={activity.loading}
        >
          <ActivityFeed data={activity.data} />
        </Section>
      </main>
    </div>
  )
}
