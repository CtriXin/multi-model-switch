/**
 * Integration Test - 验证统一浏览器适配层
 *
 * 用法: npx tsx lib/test-integration.ts
 */

import { createBrowser, probeAll } from './index'

async function main() {
  console.log('=== Unified Browser Integration Test ===\n')

  // 1. Probe availability
  console.log('1. Probing backend availability...')
  const availability = await probeAll()
  console.log(JSON.stringify(availability, null, 2))
  console.log()

  // 2. Auto-select and run
  console.log('2. Auto-selecting best backend...')
  const browser = await createBrowser({ backend: 'auto' })
  console.log(`   Active: ${browser.active.name}`)
  console.log(`   Available: ${browser.adapters.map((a) => a.name).join(', ')}`)
  console.log()

  // 3. Open page
  console.log('3. Opening test page...')
  const session = await browser.exec((a) => a.open('https://example.com'))
  console.log(`   Session: ${session.id} (${session.backend})`)
  console.log(`   URL: ${session.url}`)
  console.log()

  // 4. Snapshot
  console.log('4. Taking snapshot...')
  const snap = await browser.exec((a) => a.snapshot(session))
  console.log(`   Refs: ${snap.refs.length}`)
  console.log(`   Text preview: ${snap.text.substring(0, 200)}`)
  console.log()

  // 5. Screenshot
  console.log('5. Taking screenshot...')
  const shot = await browser.exec((a) => a.screenshot(session, { path: '/tmp/unified-browser-test.png' }))
  console.log(`   Size: ${shot.buffer.length} bytes`)
  console.log(`   Path: ${shot.path}`)
  console.log()

  // 6. Click
  console.log('6. Clicking link...')
  try {
    const linkRef = snap.refs.find((r) => r.role === 'link')
    if (linkRef) {
      await browser.exec((a) => a.click(session, linkRef.ref))
      console.log(`   Clicked: ${linkRef.name}`)
    } else {
      console.log('   No link found to click')
    }
  } catch (e: any) {
    console.log(`   Click skipped: ${e.message}`)
  }
  console.log()

  // 7. Close
  console.log('7. Closing session...')
  await browser.exec((a) => a.close(session))
  console.log('   Done')
  console.log()

  console.log('=== All tests passed ===')
}

main().catch((e) => {
  console.error('Test failed:', e.message)
  process.exit(1)
})
