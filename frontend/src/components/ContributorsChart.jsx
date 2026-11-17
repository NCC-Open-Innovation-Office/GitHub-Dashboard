const COLORS = [
  '#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd',
  '#818cf8', '#7c3aed', '#4f46e5', '#4338ca',
  '#7e22ce', '#6d28d9',
]

export default function ContributorsChart({ data }) {
  const top = data?.contributors?.slice(0, 10) ?? []

  if (!top.length && !data?.warning) return null

  const maxContributions = Math.max(...top.map((contributor) => contributor.contributions), 1)

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {data?.warning && (
        <p role="status" className="text-sm text-yellow-300">{data.warning}</p>
      )}
      {top.length > 0 && (
        <div className="text-xs text-slate-500">
          {data.scope === 'member_github_wide' ? (
            <>{data.total_members} organization members · {data.total_contributions?.toLocaleString()} commits in the last {data.period_years ?? 1} {(data.period_years ?? 1) === 1 ? 'year' : 'years'}</>
          ) : (
            <>{data.total_unique_contributors} unique contributors · {data.total_contributions?.toLocaleString()} total contributions (across all repos)</>
          )}
        </div>
      )}
      <ol className="space-y-2">
        {top.map((contributor, i) => (
          <li key={contributor.login} className="flex items-center gap-2 text-xs">
            {contributor.avatar_url ? (
              <img src={contributor.avatar_url} alt="" className="h-6 w-6 shrink-0 rounded-full" />
            ) : (
              <span aria-hidden="true" className="h-6 w-6 shrink-0 rounded-full bg-slate-700" />
            )}
            {contributor.html_url ? (
              <a href={contributor.html_url} target="_blank" rel="noopener noreferrer"
                className="w-24 shrink-0 truncate text-slate-200 hover:text-indigo-300 hover:underline"
                title={contributor.login}>
                {contributor.login}
              </a>
            ) : (
              <span className="w-24 shrink-0 truncate text-slate-200" title={contributor.login}>
                {contributor.login}
              </span>
            )}
            <span aria-hidden="true" className="h-3 min-w-0 flex-1 rounded bg-slate-700">
              <span
                className="block h-full rounded"
                style={{ width: `${contributor.contributions / maxContributions * 100}%`, backgroundColor: COLORS[i] }}
              />
            </span>
            <span className="shrink-0 text-slate-300">
              {contributor.contributions.toLocaleString()}<span className="sr-only"> contributions</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
