import { useState, useEffect, useCallback, useMemo } from 'react'
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

const TV_SECTION_ORDER = ['stats', 'commit', 'repos', 'contributors', 'activity']
const TV_ROTATION_MS = 30000

function useRemoteData(fetchFn) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(
    async (fn, options = {}) => {
      const silent = options.silent === true
      if (!silent) {
        setLoading(true)
      }
      setError(null)
      try {
        const res = await fn()
        setData(res.data)
      } catch (err) {
        setError(err?.response?.data?.detail ?? err.message ?? 'Unknown error')
      } finally {
        if (!silent) {
          setLoading(false)
        }
      }
    },
    [],
  )

  useEffect(() => {
    load(fetchFn)
  }, [load, fetchFn])

  const reload = useCallback(
    (nextFn = fetchFn, options = {}) => load(nextFn, options),
    [load, fetchFn],
  )

  return { data, loading, error, reload }
}

function Section({
  title,
  loading,
  error,
  children,
  onRefresh,
  refreshing,
  className = '',
  highlighted = false,
}) {
  const sectionTone = highlighted
    ? 'ring-2 ring-indigo-500/70 shadow-[0_0_0_1px_rgba(99,102,241,0.35),0_12px_30px_rgba(15,23,42,0.6)]'
    : ''

  return (
    <div className={`rounded-xl border border-slate-700 bg-slate-800/60 p-5 transition-all duration-500 ${sectionTone} ${className}`}>
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
  const isTvMode = useMemo(() => window.location.pathname.startsWith('/tv'), [])
  const [tvFocusIndex, setTvFocusIndex] = useState(0)
  const org = useRemoteData(getOrg)
  const repos = useRemoteData(getRepos)
  const contributors = useRemoteData(getContributors)
  const activity = useRemoteData(getActivity)
  const commitActivity = useRemoteData(getCommitActivity)

  const [globalRefreshing, setGlobalRefreshing] = useState(false)

  useEffect(() => {
    const pollables = [
      { state: org, fetch: getOrg },
      { state: repos, fetch: getRepos },
      { state: contributors, fetch: getContributors },
      { state: activity, fetch: getActivity },
      { state: commitActivity, fetch: getCommitActivity },
    ]

    const shouldPoll = pollables.some(
      ({ state }) => state.data?.is_placeholder && !state.loading,
    )

    if (!shouldPoll) {
      return
    }

    const intervalId = setInterval(() => {
      pollables.forEach(({ state, fetch }) => {
        if (state.data?.is_placeholder && !state.loading) {
          state.reload(fetch, { silent: true })
        }
      })
    }, 15000)

    return () => clearInterval(intervalId)
  }, [
    org.data?.is_placeholder,
    org.loading,
    org.reload,
    repos.data?.is_placeholder,
    repos.loading,
    repos.reload,
    contributors.data?.is_placeholder,
    contributors.loading,
    contributors.reload,
    activity.data?.is_placeholder,
    activity.loading,
    activity.reload,
    commitActivity.data?.is_placeholder,
    commitActivity.loading,
    commitActivity.reload,
  ])

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

  useEffect(() => {
    if (!isTvMode) {
      return
    }

    const intervalId = setInterval(() => {
      setTvFocusIndex((index) => (index + 1) % TV_SECTION_ORDER.length)
    }, TV_ROTATION_MS)

    return () => clearInterval(intervalId)
  }, [isTvMode])

  const pageTitle = org.data ? `Org Dashboard / ${org.data.login}` : 'Org Dashboard'
  const focusedTvSection = TV_SECTION_ORDER[tvFocusIndex]

  if (isTvMode) {
    return (
      <div className="tv-page">
        <div className="tv-frame">
          <div className="tv-canvas">
            <header className="mb-4 flex items-center justify-between rounded-xl border border-slate-700 bg-slate-800/70 px-4 py-3">
              <div className="flex items-center gap-2 text-slate-300">
                <FiGithub className="text-xl" />
                <span className="text-lg font-semibold">{pageTitle}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="rounded-md border border-indigo-700/70 bg-indigo-950/40 px-2 py-1 text-xs font-medium uppercase tracking-wider text-indigo-300">
                  Auto focus: {focusedTvSection}
                </span>
                <button
                  onClick={refreshAll}
                  disabled={globalRefreshing}
                  className="flex items-center gap-2 rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-300 transition-colors hover:border-indigo-500 hover:text-indigo-300 disabled:opacity-40"
                >
                  <FiRefreshCw className={globalRefreshing ? 'animate-spin' : ''} />
                  Refresh
                </button>
              </div>
            </header>

            <div className={`mb-4 rounded-xl transition-all duration-500 ${focusedTvSection === 'stats' ? 'ring-2 ring-indigo-500/70 shadow-[0_0_0_1px_rgba(99,102,241,0.35),0_12px_30px_rgba(15,23,42,0.6)]' : ''}`}>
              <StatsGrid org={org.data} repos={repos.data} />
            </div>

            <div className="grid h-[calc(100%-190px)] grid-cols-12 gap-4 overflow-hidden">
              <div className="col-span-8 flex flex-col gap-4 overflow-hidden">
                {(commitActivity.data || commitActivity.loading || commitActivity.error) && (
                  <Section
                    title="Commit Activity"
                    loading={commitActivity.loading}
                    error={commitActivity.error}
                    onRefresh={() => commitActivity.reload(refreshCommitActivity)}
                    refreshing={commitActivity.loading}
                    className="shrink-0"
                    highlighted={focusedTvSection === 'commit'}
                  >
                    <CommitActivity data={commitActivity.data} />
                  </Section>
                )}

                <Section
                  title="Repositories"
                  loading={repos.loading}
                  error={repos.error}
                  onRefresh={() => repos.reload(refreshRepos)}
                  refreshing={repos.loading}
                  className="min-h-0 flex-1 overflow-auto"
                  highlighted={focusedTvSection === 'repos'}
                >
                  <RepoTable repos={repos.data?.repos} />
                </Section>
              </div>

              <div className="col-span-4 flex flex-col gap-4 overflow-hidden">
                <Section
                  title="Top Contributors"
                  loading={contributors.loading}
                  error={contributors.error}
                  onRefresh={() => contributors.reload(refreshContributors)}
                  refreshing={contributors.loading}
                  className="shrink-0"
                  highlighted={focusedTvSection === 'contributors'}
                >
                  <ContributorsChart data={contributors.data} />
                </Section>

                <Section
                  title="Recent Activity"
                  loading={activity.loading}
                  error={activity.error}
                  onRefresh={() => activity.reload(refreshActivity)}
                  refreshing={activity.loading}
                  className="min-h-0 flex-1 overflow-auto"
                  highlighted={focusedTvSection === 'activity'}
                >
                  <ActivityFeed data={activity.data} />
                </Section>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
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
