import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

const COLORS = [
  '#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd',
  '#818cf8', '#7c3aed', '#4f46e5', '#4338ca',
  '#7e22ce', '#6d28d9',
]

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm shadow-xl">
      <div className="flex items-center gap-2">
        {d.avatar_url && (
          <img src={d.avatar_url} alt={d.login} className="h-6 w-6 rounded-full" />
        )}
        <a
          href={d.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-indigo-300 hover:underline"
        >
          {d.login}
        </a>
      </div>
      <p className="mt-1 text-slate-300">
        {d.contributions.toLocaleString()} contributions
      </p>
    </div>
  )
}

export default function ContributorsChart({ data }) {
  const top = data?.contributors?.slice(0, 25) ?? []

  if (!top.length) return null

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
        Top Contributors
      </h2>
      <div className="text-xs text-slate-500">
        {data.total_unique_contributors} unique contributors ·{' '}
        {data.total_contributions?.toLocaleString()} total contributions (across all repos)
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart
          data={top}
          layout="vertical"
          margin={{ top: 0, right: 20, left: 80, bottom: 0 }}
        >
          <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis
            type="category"
            dataKey="login"
            tick={{ fill: '#cbd5e1', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={76}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: '#ffffff10' }} />
          <Bar dataKey="contributions" radius={[0, 4, 4, 0]}>
            {top.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
