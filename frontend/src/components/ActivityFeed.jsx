import { formatDistanceToNow, parseISO } from 'date-fns'
import {
  FiGitCommit,
  FiGitPullRequest,
  FiAlertCircle,
  FiTag,
  FiGitBranch,
  FiStar,
  FiCode,
} from 'react-icons/fi'

const EVENT_CONFIG = {
  PushEvent: { icon: FiGitCommit, color: 'text-indigo-400', bg: 'bg-indigo-900/30' },
  PullRequestEvent: { icon: FiGitPullRequest, color: 'text-violet-400', bg: 'bg-violet-900/30' },
  IssuesEvent: { icon: FiAlertCircle, color: 'text-red-400', bg: 'bg-red-900/30' },
  ReleaseEvent: { icon: FiTag, color: 'text-emerald-400', bg: 'bg-emerald-900/30' },
  CreateEvent: { icon: FiGitBranch, color: 'text-blue-400', bg: 'bg-blue-900/30' },
  WatchEvent: { icon: FiStar, color: 'text-yellow-400', bg: 'bg-yellow-900/30' },
  ForkEvent: { icon: FiCode, color: 'text-pink-400', bg: 'bg-pink-900/30' },
}

function eventSummary(event) {
  const p = event.payload ?? {}
  switch (event.type) {
    case 'PushEvent':
      return `pushed ${p.commit_count ?? 1} commit${p.commit_count !== 1 ? 's' : ''} to ${p.ref?.replace('refs/heads/', '') ?? '…'}${p.message ? ` — "${p.message}"` : ''}`
    case 'PullRequestEvent':
      return `${p.action} PR #${p.number}: ${p.title}`
    case 'IssuesEvent':
      return `${p.action} issue #${p.number}: ${p.title}`
    case 'ReleaseEvent':
      return `${p.action} release ${p.tag_name ?? ''} — ${p.name ?? ''}`
    case 'CreateEvent':
      return `created ${p.ref_type} ${p.ref ?? ''}`
    case 'WatchEvent':
      return 'starred the repository'
    case 'ForkEvent':
      return `forked to ${p.forkee ?? ''}`
    default:
      return event.type.replace('Event', '')
  }
}

export default function ActivityFeed({ data }) {
  const events = data?.events ?? []

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
        Recent Activity
      </h2>
      {events.length === 0 ? (
        <p className="text-sm text-slate-500">No recent activity found.</p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {events.map((event) => {
            const cfg = EVENT_CONFIG[event.type] ?? {
              icon: FiCode,
              color: 'text-slate-400',
              bg: 'bg-slate-700/30',
            }
            const Icon = cfg.icon
            const repoName = event.repo?.split('/').pop() ?? event.repo

            return (
              <li
                key={event.id}
                className="flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-slate-700/30"
              >
                <div className={`mt-0.5 shrink-0 rounded-full p-1.5 ${cfg.bg}`}>
                  <Icon className={`text-sm ${cfg.color}`} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-baseline gap-1 text-sm">
                    <a
                      href={event.actor?.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-semibold text-slate-200 hover:text-indigo-300"
                    >
                      {event.actor?.login}
                    </a>
                    <span className="text-slate-400 truncate">{eventSummary(event)}</span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                    <span className="font-medium text-slate-400">{repoName}</span>
                    <span>·</span>
                    <span>
                      {event.created_at
                        ? formatDistanceToNow(parseISO(event.created_at), { addSuffix: true })
                        : ''}
                    </span>
                  </div>
                </div>

                {event.actor?.avatar_url && (
                  <img
                    src={event.actor.avatar_url}
                    alt={event.actor.login}
                    className="h-7 w-7 shrink-0 rounded-full border border-slate-600"
                  />
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
