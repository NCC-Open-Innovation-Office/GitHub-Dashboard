import { useState, useMemo } from 'react'
import { formatDistanceToNow, parseISO } from 'date-fns'
import {
  FiExternalLink,
  FiStar,
  FiGitBranch,
  FiAlertCircle,
  FiLock,
  FiEye,
  FiArchive,
} from 'react-icons/fi'

const VISIBILITY_COLORS = {
  public: 'bg-emerald-900/50 text-emerald-300 border-emerald-700',
  private: 'bg-red-900/50 text-red-300 border-red-700',
  internal: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
}

function Badge({ label, color }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {label}
    </span>
  )
}

function SortButton({ field, current, dir, onClick, children }) {
  const active = current === field
  return (
    <button
      className={`flex items-center gap-1 whitespace-nowrap text-xs font-semibold uppercase tracking-wider ${active ? 'text-indigo-400' : 'text-slate-400 hover:text-slate-200'}`}
      onClick={() => onClick(field)}
    >
      {children}
      {active && <span>{dir === 'asc' ? '↑' : '↓'}</span>}
    </button>
  )
}

export default function RepoTable({ repos }) {
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState('pushed_at')
  const [sortDir, setSortDir] = useState('desc')

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const displayed = useMemo(() => {
    let list = repos ?? []

    if (filter !== 'all') {
      if (filter === 'private_internal') {
        list = list.filter((r) => r.visibility === 'private' || r.visibility === 'internal')
      } else {
        list = list.filter((r) => r.visibility === filter)
      }
    }

    if (search) {
      const q = search.toLowerCase()
      list = list.filter(
        (r) =>
          r.name.toLowerCase().includes(q) ||
          r.description?.toLowerCase().includes(q),
      )
    }

    return [...list].sort((a, b) => {
      let av = a[sortField] ?? ''
      let bv = b[sortField] ?? ''
      if (typeof av === 'string') av = av.toLowerCase()
      if (typeof bv === 'string') bv = bv.toLowerCase()
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [repos, filter, search, sortField, sortDir])

  return (
    <div className="flex flex-col gap-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search repositories…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-48 rounded-lg border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        {['all', 'public', 'private_internal', 'internal'].map((v) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium capitalize ${
              filter === v
                ? 'border-indigo-500 bg-indigo-600 text-white'
                : 'border-slate-600 text-slate-400 hover:border-slate-500 hover:text-slate-200'
            }`}
          >
            {v === 'private_internal' ? 'Private + Internal' : v}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-700">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-700 bg-slate-800/80">
            <tr>
              <th className="px-4 py-3 text-left">
                <SortButton field="name" current={sortField} dir={sortDir} onClick={handleSort}>
                  Repository
                </SortButton>
              </th>
              <th className="px-4 py-3 text-left">
                <SortButton field="language" current={sortField} dir={sortDir} onClick={handleSort}>
                  Language
                </SortButton>
              </th>
              <th className="px-4 py-3 text-right">
                <SortButton field="stars" current={sortField} dir={sortDir} onClick={handleSort}>
                  Stars
                </SortButton>
              </th>
              <th className="px-4 py-3 text-right">
                <SortButton field="forks" current={sortField} dir={sortDir} onClick={handleSort}>
                  Forks
                </SortButton>
              </th>
              <th className="px-4 py-3 text-right">
                <SortButton field="open_issues" current={sortField} dir={sortDir} onClick={handleSort}>
                  Issues
                </SortButton>
              </th>
              <th className="px-4 py-3 text-right">
                <SortButton field="pushed_at" current={sortField} dir={sortDir} onClick={handleSort}>
                  Last Push
                </SortButton>
              </th>
            </tr>
          </thead>
          <tbody>
            {displayed.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-10 text-center text-slate-500">
                  No repositories match your filter.
                </td>
              </tr>
            ) : (
              displayed.map((repo) => (
                <tr
                  key={repo.id}
                  className="border-b border-slate-700/50 transition-colors hover:bg-slate-700/30"
                >
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <a
                          href={repo.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-indigo-400 hover:text-indigo-300 hover:underline flex items-center gap-1"
                        >
                          {repo.name}
                          <FiExternalLink className="text-xs opacity-60" />
                        </a>
                        <Badge
                          label={repo.visibility}
                          color={VISIBILITY_COLORS[repo.visibility] ?? 'bg-slate-700 text-slate-300 border-slate-600'}
                        />
                        {repo.archived && (
                          <Badge label="archived" color="bg-slate-700 text-slate-400 border-slate-600" />
                        )}
                        {repo.fork && (
                          <Badge label="fork" color="bg-slate-700 text-slate-400 border-slate-600" />
                        )}
                      </div>
                      {repo.description && (
                        <span className="text-xs text-slate-400 line-clamp-1">
                          {repo.description}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {repo.language ?? <span className="text-slate-600">—</span>}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300">
                    <span className="flex items-center justify-end gap-1">
                      <FiStar className="text-yellow-400 text-xs" />
                      {repo.stars}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300">
                    <span className="flex items-center justify-end gap-1">
                      <FiGitBranch className="text-emerald-400 text-xs" />
                      {repo.forks}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300">
                    <span className="flex items-center justify-end gap-1">
                      <FiAlertCircle className="text-red-400 text-xs" />
                      {repo.open_issues}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-xs text-slate-400">
                    {repo.pushed_at
                      ? formatDistanceToNow(parseISO(repo.pushed_at), { addSuffix: true })
                      : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Showing {displayed.length} of {repos?.length ?? 0} repositories
      </p>
    </div>
  )
}
