import {
  FiUsers,
  FiStar,
  FiGitBranch,
  FiAlertCircle,
  FiLock,
  FiUserCheck,
} from 'react-icons/fi'

function StatCard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className={`rounded-xl border bg-slate-800 p-5 ${color}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-400">{label}</span>
        <Icon className="text-xl opacity-70" />
      </div>
      <p className="mt-2 text-3xl font-bold text-white">
        {value?.toLocaleString() ?? '—'}
      </p>
      {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
    </div>
  )
}

export default function StatsGrid({ org, repos }) {
  const privateCount = repos
    ? repos.private + (repos.internal ?? 0)
    : null

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
      <StatCard
        icon={FiUsers}
        label="Followers"
        value={org?.followers}
        color="border-indigo-700/40"
      />
      <StatCard
        icon={FiUserCheck}
        label="Members"
        value={org?.member_count}
        color="border-violet-700/40"
      />
      <StatCard
        icon={FiGitBranch}
        label="Repositories"
        value={repos?.total}
        sub={`${repos?.public ?? 0} public · ${privateCount ?? 0} private/internal`}
        color="border-blue-700/40"
      />
      <StatCard
        icon={FiStar}
        label="Total Stars"
        value={repos?.total_stars}
        color="border-yellow-700/40"
      />
      <StatCard
        icon={FiAlertCircle}
        label="Open Issues"
        value={repos?.total_open_issues}
        color="border-red-700/40"
      />
      <StatCard
        icon={FiLock}
        label="Private / Internal"
        value={privateCount}
        sub={`${repos?.archived ?? 0} archived`}
        color="border-emerald-700/40"
      />
    </div>
  )
}
