import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const data = {
  warning: 'Activity refresh failed',
  events: [{
    id: 'commit:private:abc',
    type: 'CommitEvent',
    actor: { login: 'Unlinked author', url: null },
    repo: 'org/private',
    created_at: '2026-01-01T00:00:00Z',
    payload: { message: 'A commit' },
  }],
}

function assertActivity(markup) {
  assert.match(markup, /Activity refresh failed/)
  assert.match(markup, /Unlinked author/)
  assert.match(markup, /committed/)
  assert.match(markup, /A commit/)
  assert.doesNotMatch(markup, /href="(?:undefined|)"/)
}

test('production activity feed renders searched commits and warnings', async () => {
  const source = await readFile(new URL('../../backend/static/js/app.js', import.meta.url), 'utf8')
  const container = { innerHTML: '' }
  const context = vm.createContext({
    window: { location: { pathname: '/' } },
    document: { addEventListener() {}, getElementById: () => container },
  })
  vm.runInContext(source, context)
  context.renderActivityFeed(data)
  assertActivity(container.innerHTML)
})

test('React activity feed renders searched commits and warnings', async () => {
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true },
  })
  try {
    const { default: ActivityFeed } = await server.ssrLoadModule('/src/components/ActivityFeed.jsx')
    assertActivity(renderToStaticMarkup(React.createElement(ActivityFeed, { data })))
  } finally {
    await server.close()
  }
})
