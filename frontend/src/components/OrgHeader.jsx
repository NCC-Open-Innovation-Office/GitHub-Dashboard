import { FiExternalLink, FiMapPin, FiMail, FiLink } from 'react-icons/fi'
import { formatDistanceToNow, parseISO } from 'date-fns'

export default function OrgHeader({ org }) {
  const since = org.created_at
    ? formatDistanceToNow(parseISO(org.created_at), { addSuffix: true })
    : null

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-slate-700 bg-slate-800 p-6 sm:flex-row sm:items-center">
      {org.avatar_url && (
        <img
          src={org.avatar_url}
          alt={org.login}
          className="h-20 w-20 rounded-full border-2 border-slate-600 shrink-0"
        />
      )}

      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-white">
            {org.name || org.login}
          </h1>
          {org.html_url && (
            <a
              href={org.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300"
            >
              @{org.login}
              <FiExternalLink className="text-xs" />
            </a>
          )}
        </div>

        {org.description && (
          <p className="mt-1 text-slate-300">{org.description}</p>
        )}

        <div className="mt-2 flex flex-wrap gap-4 text-sm text-slate-400">
          {org.location && (
            <span className="flex items-center gap-1">
              <FiMapPin /> {org.location}
            </span>
          )}
          {org.email && (
            <span className="flex items-center gap-1">
              <FiMail /> {org.email}
            </span>
          )}
          {org.blog && (
            <a
              href={org.blog.startsWith('http') ? org.blog : `https://${org.blog}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 hover:text-slate-200"
            >
              <FiLink /> {org.blog}
            </a>
          )}
          {since && <span>Created {since}</span>}
        </div>
      </div>
    </div>
  )
}
