import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const contributors = Array.from({ length: 12 }, (_, i) => ({
  login: `user-${i + 1}`,
  avatar_url: i === 1 ? null : `https://avatars.example/${i + 1}`,
  html_url: `https://github.com/user-${i + 1}`,
  contributions: 12 - i,
}))
const data = { contributors, total_unique_contributors: 12, total_contributions: 78 }

function assertLeaderboard(markup) {
  assert.equal((markup.match(/<li\b/g) ?? []).length, 10)
  assert.match(markup, /user-1\b/)
  assert.match(markup, /user-10\b/)
  assert.doesNotMatch(markup, /user-11\b/)
  assert.match(markup, /src="https:\/\/avatars\.example\/1"/)
  assert.equal((markup.match(/<img\b/g) ?? []).length, 9)
  assert.match(markup, /href="https:\/\/github\.com\/user-1"/)
}

test('production dashboard renders at most ten contributors on home and TV', async () => {
  const source = await readFile(new URL('../../backend/static/js/app.js', import.meta.url), 'utf8')
  for (const pathname of ['/', '/tv']) {
    const container = { innerHTML: '' }
    const context = vm.createContext({
      window: { location: { pathname } },
      document: {
        addEventListener() {},
        getElementById: () => container,
      },
    })
    vm.runInContext(source, context)
    context.renderContributorsChart(data)
    assertLeaderboard(container.innerHTML)
    context.renderContributorsChart({
      ...data, scope: 'member_github_wide', total_members: 12, warning: 'Refresh failed',
    })
    assert.match(container.innerHTML, /12 organization members/)
    assert.match(container.innerHTML, /GitHub-wide contributions in the last 12 months/)
    assert.match(container.innerHTML, /Refresh failed/)
    context.renderContributorsChart({
      ...data,
      contributors: [{ login: '<user>', contributions: 0 }],
    })
    assert.match(container.innerHTML, /&lt;user&gt;/)
    assert.match(container.innerHTML, /width: 0%/)
    assert.equal((container.innerHTML.match(/<li\b/g) ?? []).length, 1)
    context.renderContributorsChart({ contributors: [] })
    assert.match(container.innerHTML, /No contributor data available/)
  }
})

test('React dashboard renders at most ten contributors and handles empty data', async () => {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true },
  })
  try {
    const { default: ContributorsChart } = await server.ssrLoadModule('/src/components/ContributorsChart.jsx')
    assertLeaderboard(renderToStaticMarkup(React.createElement(ContributorsChart, { data })))
    const members = renderToStaticMarkup(React.createElement(ContributorsChart, {
      data: { ...data, scope: 'member_github_wide', total_members: 12, warning: 'Refresh failed' },
    }))
    assert.match(members, /12 organization members/)
    assert.match(members, /GitHub-wide contributions in the last 12 months/)
    assert.match(members, /Refresh failed/)
    const single = renderToStaticMarkup(React.createElement(ContributorsChart, {
      data: { ...data, contributors: [{ login: '<user>', contributions: 0 }] },
    }))
    assert.match(single, /&lt;user&gt;/)
    assert.match(single, /width:0%/)
    assert.equal((single.match(/<li\b/g) ?? []).length, 1)
    assert.equal(renderToStaticMarkup(React.createElement(ContributorsChart, { data: { contributors: [] } })), '')
  } finally {
    await server.close()
  }
})
