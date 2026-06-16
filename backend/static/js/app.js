// =============================================================================
// GitHub Org Dashboard — vanilla JS, no build tools, no npm
// =============================================================================

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  org: null,
  allRepos: [],
  contributors: null,
  activity: null,
  commitActivity: null,
  // UI
  repoSearch: '',
  repoFilter: 'all',
  repoSort: { field: 'pushed_at', dir: 'desc' },
  // Chart.js instances (destroyed on refresh)
  charts: { contributors: null, commits: null },
}

// ── Utils ─────────────────────────────────────────────────────────────────────

function timeAgo(isoString) {
  if (!isoString) return '—'
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const intervals = [
    { label: 'year',   s: 31536000 },
    { label: 'month',  s: 2592000  },
    { label: 'day',    s: 86400    },
    { label: 'hour',   s: 3600     },
    { label: 'minute', s: 60       },
  ]
  for (const { label, s } of intervals) {
    const n = Math.floor(seconds / s)
    if (n >= 1) return `${n} ${label}${n > 1 ? 's' : ''} ago`
  }
  return 'just now'
}

function fmtDate(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function num(n) {
  if (n == null) return '—'
  return n.toLocaleString()
}

function esc(str) {
  if (!str) return ''
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function el(id) { return document.getElementById(id) }

// ── API ───────────────────────────────────────────────────────────────────────

async function apiFetch(path) {
  const res = await fetch(`/api${path}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

async function apiPost(path) {
  const res = await fetch(`/api${path}`, { method: 'POST' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Loading / Error helpers ───────────────────────────────────────────────────

function spinnerHTML(label = 'Loading…') {
  return `<div class="flex flex-col items-center justify-center gap-3 py-12 text-slate-400">
    <div class="spin h-8 w-8 rounded-full border-4 border-slate-600 border-t-indigo-500"></div>
    <span class="text-sm">${esc(label)}</span>
  </div>`
}

function warningHTML(msg) {
  return `<div class="flex items-start gap-3 rounded-lg border border-yellow-700 bg-yellow-950/40 px-4 py-3 text-yellow-300 text-sm">
    <svg class="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
    </svg>
    <span>${esc(msg)}</span>
  </div>`
}

function errorHTML(msg) {
  return `<div class="flex items-center gap-3 rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-red-300 text-sm">
    <svg class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
    </svg>
    ${esc(msg)}
  </div>`
}

function setLoading(id, label) {
  const node = el(id)
  if (node) node.innerHTML = spinnerHTML(label)
}

function setError(id, msg) {
  const node = el(id)
  if (node) node.innerHTML = errorHTML(msg)
}

// ── Org Header ────────────────────────────────────────────────────────────────

function renderOrgHeader(org) {
  const section = el('org-header-section')
  if (!section) return

  const blogUrl = org.blog
    ? (org.blog.startsWith('http') ? org.blog : `https://${org.blog}`)
    : null

  section.innerHTML = `
    <div class="flex flex-col gap-4 rounded-xl border border-slate-700 bg-slate-800 p-6 sm:flex-row sm:items-center">
      ${org.avatar_url ? `<img src="${esc(org.avatar_url)}" alt="${esc(org.login)}" class="h-20 w-20 rounded-full border-2 border-slate-600 shrink-0">` : ''}
      <div class="flex-1 min-w-0">
        <div class="flex flex-wrap items-center gap-3">
          <h1 class="text-2xl font-bold text-white">${esc(org.name || org.login)}</h1>
          ${org.html_url ? `<a href="${esc(org.html_url)}" target="_blank" rel="noopener noreferrer"
            class="text-sm text-indigo-400 hover:text-indigo-300">@${esc(org.login)} ↗</a>` : ''}
        </div>
        ${org.description ? `<p class="mt-1 text-slate-300">${esc(org.description)}</p>` : ''}
        <div class="mt-2 flex flex-wrap gap-4 text-sm text-slate-400">
          ${org.location ? `<span>📍 ${esc(org.location)}</span>` : ''}
          ${org.email ? `<span>✉ ${esc(org.email)}</span>` : ''}
          ${blogUrl ? `<a href="${esc(blogUrl)}" target="_blank" rel="noopener noreferrer" class="hover:text-slate-200">🔗 ${esc(org.blog)}</a>` : ''}
          ${org.created_at ? `<span>Est. ${new Date(org.created_at).getFullYear()}</span>` : ''}
        </div>
      </div>
    </div>`

  const navName = el('nav-org-name')
  if (navName) navName.textContent = `/ ${org.login}`
}

// ── Stats Grid ────────────────────────────────────────────────────────────────

function renderStats(org, repos) {
  const grid = el('stats-grid')
  if (!grid) return

  const privateCount = repos ? (repos.private || 0) + (repos.internal || 0) : null

  const cards = [
    { label: 'Followers',        value: org?.followers,         icon: '👥', border: 'border-indigo-700/40' },
    { label: 'Members',          value: org?.member_count,      icon: '🧑‍💻', border: 'border-violet-700/40' },
    { label: 'Repositories',     value: repos?.total,           icon: '📁',
      sub: repos ? `${repos.public} public · ${privateCount} private/internal` : '',
      border: 'border-blue-700/40' },
    { label: 'Total Stars',      value: repos?.total_stars,     icon: '⭐', border: 'border-yellow-700/40' },
    { label: 'Open Issues',      value: repos?.total_open_issues, icon: '🐛', border: 'border-red-700/40' },
    { label: 'Private/Internal', value: privateCount,           icon: '🔒',
      sub: repos ? `${repos.archived || 0} archived` : '',
      border: 'border-emerald-700/40' },
  ]

  grid.innerHTML = cards.map(c => `
    <div class="rounded-xl border ${c.border} bg-slate-800 p-5">
      <div class="flex items-center justify-between">
        <span class="text-sm font-medium text-slate-400">${c.label}</span>
        <span class="text-xl opacity-70">${c.icon}</span>
      </div>
      <p class="mt-2 text-3xl font-bold text-white">${c.value != null ? num(c.value) : '—'}</p>
      ${c.sub ? `<p class="mt-1 text-xs text-slate-400">${esc(c.sub)}</p>` : ''}
    </div>`).join('')
}

// ── Repo Filter Buttons ───────────────────────────────────────────────────────

function renderRepoFilterBtns() {
  const container = el('repo-filter-btns')
  if (!container) return

  const filters = [
    { key: 'all',              label: 'All' },
    { key: 'public',           label: 'Public' },
    { key: 'private_internal', label: 'Private + Internal' },
    { key: 'archived',         label: 'Archived' },
  ]

  container.innerHTML = filters.map(f => `
    <button data-filter="${f.key}"
      class="filter-btn rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors
        ${state.repoFilter === f.key
          ? 'border-indigo-500 bg-indigo-600 text-white'
          : 'border-slate-600 text-slate-400 hover:border-slate-500 hover:text-slate-200'}">
      ${f.label}
    </button>`).join('')
}

// ── Repo Table ────────────────────────────────────────────────────────────────

const VISIBILITY_BADGE = {
  public:   'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  private:  'bg-red-900/50 text-red-300 border border-red-700',
  internal: 'bg-yellow-900/50 text-yellow-300 border border-yellow-700',
}

function getFilteredRepos() {
  let list = state.allRepos

  if (state.repoFilter === 'public') {
    list = list.filter(r => r.visibility === 'public')
  } else if (state.repoFilter === 'private_internal') {
    list = list.filter(r => r.visibility === 'private' || r.visibility === 'internal')
  } else if (state.repoFilter === 'archived') {
    list = list.filter(r => r.archived)
  }

  if (state.repoSearch) {
    const q = state.repoSearch.toLowerCase()
    list = list.filter(r =>
      r.name.toLowerCase().includes(q) ||
      (r.description || '').toLowerCase().includes(q)
    )
  }

  const { field, dir } = state.repoSort
  return [...list].sort((a, b) => {
    let av = a[field] ?? '', bv = b[field] ?? ''
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av < bv) return dir === 'asc' ? -1 : 1
    if (av > bv) return dir === 'asc' ? 1 : -1
    return 0
  })
}

function sortClass(field) {
  if (state.repoSort.field !== field) return 'sort-arrow'
  return state.repoSort.dir === 'asc' ? 'sort-asc' : 'sort-desc'
}

function thBtn(field, label) {
  return `<th class="px-4 py-3">
    <button data-sort="${field}"
      class="${sortClass(field)} text-left text-xs font-semibold uppercase tracking-wider
        ${state.repoSort.field === field ? 'text-indigo-400' : 'text-slate-400 hover:text-slate-200'}
        whitespace-nowrap transition-colors">
      ${label}
    </button>
  </th>`
}

function renderRepoTable() {
  const wrapper = el('repos-table-wrapper')
  if (!wrapper) return

  const rows = getFilteredRepos()

  wrapper.innerHTML = `
    <div class="overflow-x-auto rounded-xl border border-slate-700">
      <table class="w-full text-sm">
        <thead class="border-b border-slate-700 bg-slate-800/80">
          <tr>
            ${thBtn('name',       'Repository')}
            ${thBtn('language',   'Language')}
            <th class="px-4 py-3 text-right">${thBtn('stars',       'Stars').replace('<th','<span').replace('</th>','</span>')}</th>
            <th class="px-4 py-3 text-right">${thBtn('forks',       'Forks').replace('<th','<span').replace('</th>','</span>')}</th>
            <th class="px-4 py-3 text-right">${thBtn('open_issues', 'Issues').replace('<th','<span').replace('</th>','</span>')}</th>
            ${thBtn('pushed_at',  'Last Push')}
          </tr>
        </thead>
        <tbody>
          ${rows.length === 0
            ? `<tr><td colspan="6" class="py-10 text-center text-slate-500">No repositories match your filter.</td></tr>`
            : rows.map(r => `
              <tr class="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                <td class="px-4 py-3">
                  <div class="flex flex-col gap-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <a href="${esc(r.html_url)}" target="_blank" rel="noopener noreferrer"
                        class="font-medium text-indigo-400 hover:text-indigo-300 hover:underline">
                        ${esc(r.name)} ↗
                      </a>
                      <span class="rounded px-1.5 py-0.5 text-xs font-medium ${VISIBILITY_BADGE[r.visibility] || 'bg-slate-700 text-slate-300 border border-slate-600'}">
                        ${r.visibility}
                      </span>
                      ${r.archived ? `<span class="rounded border border-slate-600 bg-slate-700 px-1.5 py-0.5 text-xs text-slate-400">archived</span>` : ''}
                      ${r.fork     ? `<span class="rounded border border-slate-600 bg-slate-700 px-1.5 py-0.5 text-xs text-slate-400">fork</span>` : ''}
                    </div>
                    ${r.description ? `<span class="text-xs text-slate-400 truncate max-w-xs">${esc(r.description)}</span>` : ''}
                  </div>
                </td>
                <td class="px-4 py-3 text-slate-300">${r.language ? esc(r.language) : '<span class="text-slate-600">—</span>'}</td>
                <td class="px-4 py-3 text-right text-slate-300">⭐ ${num(r.stars)}</td>
                <td class="px-4 py-3 text-right text-slate-300">🍴 ${num(r.forks)}</td>
                <td class="px-4 py-3 text-right text-slate-300">🐛 ${num(r.open_issues)}</td>
                <td class="px-4 py-3 text-right text-xs text-slate-400">${timeAgo(r.pushed_at)}</td>
              </tr>`).join('')
          }
        </tbody>
      </table>
    </div>`

  const label = el('repo-count-label')
  if (label) label.textContent = `Showing ${rows.length} of ${state.allRepos.length} repositories`
}

// ── Contributors Chart ────────────────────────────────────────────────────────

function renderContributorsChart(data) {
  const container = el('contributors-content')
  if (!container) return

  const top = (data?.contributors || []).slice(0, 15)
  if (!top.length) {
    container.innerHTML = '<p class="text-sm text-slate-500">No contributor data available.</p>'
    return
  }

  container.innerHTML = `
    <div class="mb-2 text-xs text-slate-500">
      ${num(data.total_unique_contributors)} contributors · ${num(data.total_contributions)} total contributions
    </div>
    <canvas id="contributors-chart" height="320"></canvas>`

  if (state.charts.contributors) {
    state.charts.contributors.destroy()
    state.charts.contributors = null
  }

  const COLORS = ['#6366f1','#8b5cf6','#a78bfa','#c4b5fd','#818cf8','#7c3aed','#4f46e5','#4338ca','#7e22ce','#6d28d9','#5b21b6','#7c3aed','#9333ea','#a21caf','#86198f']

  const ctx = el('contributors-chart').getContext('2d')
  state.charts.contributors = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top.map(c => c.login),
      datasets: [{
        data: top.map(c => c.contributions),
        backgroundColor: COLORS.slice(0, top.length),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1e293b',
          borderColor: '#334155',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#f1f5f9',
          callbacks: {
            label: ctx => ` ${num(ctx.parsed.x)} contributions`,
          },
        },
      },
      scales: {
        x: { grid: { color: '#1e293b' }, ticks: { color: '#94a3b8', font: { size: 11 } } },
        y: { grid: { display: false }, ticks: { color: '#e2e8f0', font: { size: 12 } } },
      },
    },
  })
}

// ── Commit Activity Chart ─────────────────────────────────────────────────────

function renderCommitActivity(data) {
  const container = el('commit-activity-content')
  if (!container) return

  const aggregated = data?.aggregated || []
  if (!aggregated.length) {
    container.innerHTML = '<p class="text-sm text-slate-500">No commit data available.</p>'
    return
  }

  const total = aggregated.reduce((s, d) => s + d.commits, 0)
  container.innerHTML = `
    <div class="mb-2 flex justify-end text-xs text-slate-500">${num(total)} commits in period</div>
    <canvas id="commit-chart" height="80"></canvas>`

  if (state.charts.commits) {
    state.charts.commits.destroy()
    state.charts.commits = null
  }

  const ctx = el('commit-chart').getContext('2d')
  state.charts.commits = new Chart(ctx, {
    type: 'line',
    data: {
      labels: aggregated.map(d => fmtDate(d.week)),
      datasets: [{
        label: 'Commits',
        data: aggregated.map(d => d.commits),
        fill: true,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99,102,241,0.15)',
        tension: 0.3,
        pointRadius: 2,
        pointHoverRadius: 5,
        pointBackgroundColor: '#818cf8',
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1e293b',
          borderColor: '#334155',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#f1f5f9',
          callbacks: { label: ctx => ` ${num(ctx.parsed.y)} commits` },
        },
      },
      scales: {
        x: {
          grid: { color: '#1e293b' },
          ticks: { color: '#94a3b8', maxTicksLimit: 10, font: { size: 11 } },
        },
        y: {
          grid: { color: '#1e293b' },
          ticks: { color: '#94a3b8', font: { size: 11 } },
          beginAtZero: true,
        },
      },
    },
  })
}

// ── Activity Feed ─────────────────────────────────────────────────────────────

const EVENT_ICON = {
  PushEvent:              { icon: '⬆', color: 'text-indigo-400',  bg: 'bg-indigo-900/30' },
  PullRequestEvent:       { icon: '↔', color: 'text-violet-400',  bg: 'bg-violet-900/30' },
  IssuesEvent:            { icon: '●', color: 'text-red-400',     bg: 'bg-red-900/30' },
  ReleaseEvent:           { icon: '🏷', color: 'text-emerald-400', bg: 'bg-emerald-900/30' },
  CreateEvent:            { icon: '+', color: 'text-blue-400',    bg: 'bg-blue-900/30' },
  WatchEvent:             { icon: '⭐', color: 'text-yellow-400', bg: 'bg-yellow-900/30' },
  ForkEvent:              { icon: '⑂', color: 'text-pink-400',   bg: 'bg-pink-900/30' },
  PullRequestReviewEvent: { icon: '✓', color: 'text-teal-400',   bg: 'bg-teal-900/30' },
  DeleteEvent:            { icon: '✕', color: 'text-slate-400',  bg: 'bg-slate-700/30' },
}

function eventSummary(event) {
  const p = event.payload || {}
  switch (event.type) {
    case 'PushEvent':
      return `pushed ${p.commit_count || 1} commit${p.commit_count !== 1 ? 's' : ''} to ${(p.ref || '').replace('refs/heads/', '')}${p.message ? ` — "${p.message}"` : ''}`
    case 'PullRequestEvent':
      return `${p.action} PR #${p.number}: ${p.title}`
    case 'IssuesEvent':
      return `${p.action} issue #${p.number}: ${p.title}`
    case 'ReleaseEvent':
      return `${p.action} release ${p.tag_name || ''} — ${p.name || ''}`
    case 'CreateEvent':
      return `created ${p.ref_type} ${p.ref || ''}`
    case 'WatchEvent':
      return 'starred the repository'
    case 'ForkEvent':
      return `forked to ${p.forkee || ''}`
    case 'DeleteEvent':
      return `deleted ${p.ref_type} ${p.ref || ''}`
    default:
      return event.type.replace('Event', '')
  }
}

function renderActivityFeed(data) {
  const container = el('activity-content')
  if (!container) return

  const events = data?.events || []
  if (!events.length) {
    container.innerHTML = '<p class="text-sm text-slate-500">No recent activity found.</p>'
    return
  }

  container.innerHTML = `<ul class="flex flex-col gap-0.5">
    ${events.map(event => {
      const cfg = EVENT_ICON[event.type] || { icon: '·', color: 'text-slate-400', bg: 'bg-slate-700/30' }
      const repoName = (event.repo || '').split('/').pop()
      return `
        <li class="flex items-start gap-3 rounded-lg px-3 py-2.5 hover:bg-slate-700/30 transition-colors">
          <div class="mt-0.5 shrink-0 rounded-full p-2 ${cfg.bg}">
            <span class="${cfg.color} text-sm font-mono leading-none">${cfg.icon}</span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex flex-wrap items-baseline gap-1 text-sm">
              <a href="${esc(event.actor?.url)}" target="_blank" rel="noopener noreferrer"
                class="font-semibold text-slate-200 hover:text-indigo-300">
                ${esc(event.actor?.login)}
              </a>
              <span class="text-slate-400 truncate">${esc(eventSummary(event))}</span>
            </div>
            <div class="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
              <span class="font-medium text-slate-400">${esc(repoName)}</span>
              <span>·</span>
              <span>${timeAgo(event.created_at)}</span>
            </div>
          </div>
          ${event.actor?.avatar_url
            ? `<img src="${esc(event.actor.avatar_url)}" alt="${esc(event.actor.login)}"
                 class="h-7 w-7 shrink-0 rounded-full border border-slate-600">`
            : ''}
        </li>`
    }).join('')}
  </ul>`
}

// ── Load sections (independent, non-blocking) ─────────────────────────────────

async function loadOrg() {
  try {
    const org = await apiFetch('/org')
    state.org = org
    renderOrgHeader(org)
    renderStats(state.org, state.allRepos.length ? { total: state.allRepos.length } : null)
  } catch (e) {
    const s = el('org-header-section')
    if (s) s.innerHTML = errorHTML(`Organization: ${e.message}`)
  }
}

async function loadRepos() {
  try {
    const data = await apiFetch('/repos')
    state.allRepos = data.repos || []
    renderRepoFilterBtns()

    if (data.warning) {
      const wrapper = el('repos-table-wrapper')
      if (wrapper) wrapper.innerHTML = warningHTML(data.warning)
      const label = el('repo-count-label')
      if (label) label.textContent = ''
    } else {
      renderRepoTable()
      if (data.truncated) {
        const label = el('repo-count-label')
        if (label) label.textContent += `  ·  Showing most recently pushed ${data.max_repos} of ${data.total}+ repos. Set MAX_REPOS in .env to increase.`
      }
    }

    renderStats(state.org, data)
  } catch (e) {
    setError('repos-table-wrapper', `Repositories: ${e.message}`)
  }
}

async function loadContributors() {
  try {
    const data = await apiFetch('/contributors')
    state.contributors = data
    renderContributorsChart(data)
  } catch (e) {
    setError('contributors-content', `Contributors: ${e.message}`)
  }
}

async function loadActivity() {
  try {
    const data = await apiFetch('/activity')
    state.activity = data
    renderActivityFeed(data)
  } catch (e) {
    setError('activity-content', `Activity: ${e.message}`)
  }
}

async function loadCommitActivity() {
  try {
    const data = await apiFetch('/commit-activity')
    state.commitActivity = data
    renderCommitActivity(data)
  } catch (e) {
    setError('commit-activity-content', `Commit activity: ${e.message}`)
  }
}

// ── Refresh handlers ──────────────────────────────────────────────────────────

async function refreshSection(postPath, loadFn, contentId, label) {
  setLoading(contentId, `Refreshing ${label}…`)
  try {
    await apiPost(postPath)
    await loadFn()
  } catch (e) {
    setError(contentId, e.message)
  }
}

async function refreshAll() {
  const icon = el('refresh-all-icon')
  const btn  = el('refresh-all-btn')
  if (icon) icon.classList.add('spin')
  if (btn)  btn.disabled = true

  await Promise.allSettled([
    refreshSection('/org/refresh',              loadOrg,           'org-header-section',    'org'),
    refreshSection('/repos/refresh',            loadRepos,         'repos-table-wrapper',   'repos'),
    refreshSection('/contributors/refresh',     loadContributors,  'contributors-content',  'contributors'),
    refreshSection('/activity/refresh',         loadActivity,      'activity-content',      'activity'),
    refreshSection('/commit-activity/refresh',  loadCommitActivity,'commit-activity-content','commits'),
  ])

  if (icon) icon.classList.remove('spin')
  if (btn)  btn.disabled = false
}

// ── Event delegation ──────────────────────────────────────────────────────────

document.addEventListener('click', e => {
  // Refresh buttons
  const refreshBtn = e.target.closest('[data-refresh]')
  if (refreshBtn) {
    const key = refreshBtn.dataset.refresh
    const map = {
      repos:        ['/repos/refresh',            loadRepos,         'repos-table-wrapper',    'repos'],
      contributors: ['/contributors/refresh',      loadContributors,  'contributors-content',   'contributors'],
      activity:     ['/activity/refresh',          loadActivity,      'activity-content',       'activity'],
      commits:      ['/commit-activity/refresh',   loadCommitActivity,'commit-activity-content','commits'],
    }
    if (map[key]) refreshSection(...map[key])
    return
  }

  // Repo filter buttons
  const filterBtn = e.target.closest('[data-filter]')
  if (filterBtn) {
    state.repoFilter = filterBtn.dataset.filter
    renderRepoFilterBtns()
    renderRepoTable()
    return
  }

  // Repo sort columns
  const sortBtn = e.target.closest('[data-sort]')
  if (sortBtn) {
    const field = sortBtn.dataset.sort
    if (state.repoSort.field === field) {
      state.repoSort.dir = state.repoSort.dir === 'asc' ? 'desc' : 'asc'
    } else {
      state.repoSort.field = field
      state.repoSort.dir = 'desc'
    }
    renderRepoTable()
    return
  }

  // Global refresh button
  if (e.target.closest('#refresh-all-btn')) {
    refreshAll()
  }
})

// Repo search
document.addEventListener('input', e => {
  if (e.target.id === 'repo-search') {
    state.repoSearch = e.target.value
    renderRepoTable()
  }
})

// ── Chart.js global defaults (dark theme) ────────────────────────────────────

function configureChartDefaults() {
  Chart.defaults.color = '#94a3b8'
  Chart.defaults.borderColor = '#1e293b'
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  configureChartDefaults()
  // All sections load independently so one slow endpoint doesn't block others
  await Promise.allSettled([
    loadOrg(),
    loadRepos(),
    loadContributors(),
    loadActivity(),
    loadCommitActivity(),
  ])
}

document.addEventListener('DOMContentLoaded', init)
