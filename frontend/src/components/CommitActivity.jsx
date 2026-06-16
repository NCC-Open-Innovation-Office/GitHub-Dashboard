import { useMemo } from 'react'
import { format, fromUnixTime } from 'date-fns'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm shadow-xl">
      <p className="text-slate-400">{label}</p>
      <p className="text-indigo-300 font-semibold">
        {payload[0].value.toLocaleString()} commits
      </p>
    </div>
  )
}

export default function CommitActivity({ data }) {
  const chartData = useMemo(() => {
    return (data?.aggregated ?? []).map((d) => ({
      week: format(fromUnixTime(d.week), 'MMM d'),
      commits: d.commits,
    }))
  }, [data])

  const totalCommits = useMemo(
    () => chartData.reduce((s, d) => s + d.commits, 0),
    [chartData],
  )

  if (!chartData.length) return null

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Commit Activity — Last 26 Weeks
        </h2>
        <span className="text-xs text-slate-500">
          {totalCommits.toLocaleString()} commits total
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="commitGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
          <XAxis
            dataKey="week"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="commits"
            stroke="#6366f1"
            strokeWidth={2}
            fill="url(#commitGrad)"
            dot={false}
            activeDot={{ r: 4, fill: '#818cf8' }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
