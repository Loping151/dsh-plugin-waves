import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import vm from 'node:vm'
import { readAttachments } from '../lib/host/attachments.js'
import { runSlashCommand } from '../lib/host/command.js'
import { makeResultStore } from '../lib/host/results.js'

const signal = new AbortController().signal
const image = { type: 'image', attachment: { attachmentId: 'image-id' } }
const file = { type: 'file', attachment: { attachmentId: 'file-id', name: 'records.json' } }
const ctx = { get: () => ({
  async readImage(ref, receivedSignal) {
    assert.equal(ref, image.attachment)
    assert.equal(receivedSignal, signal)
    return { data: Buffer.from('image') }
  },
  async *readFileStream(ref, receivedSignal) {
    assert.equal(ref, file.attachment)
    assert.equal(receivedSignal, signal)
    yield Buffer.from('{')
    yield Buffer.from('}')
  },
}) }

test('DSH 0.2 attachments reach the service as images and one named file', async () => {
  const results = makeResultStore()
  let body
  const result = await runSlashCommand({ async call(path, options) {
    assert.equal(path, '/api/chat')
    assert.equal(options.signal, signal)
    body = options.body
    return { ok: true, summary: '评分完成', segments: [{ type: 'html', url: '/api/media/panel.html' }] }
  } }, results, { rawInput: '-p 评分', agent: { id: 'session-id' }, commandId: 'command-id', signal,
    attachments: [image, file] }, (blocks, signal) => readAttachments(ctx, blocks, signal))
  assert.equal(result.kind, 'success')
  assert.deepEqual(body, { command: '评分', scene: 'direct', session_id: 'session-id',
    images: ['base64://aW1hZ2U='], file_name: 'records.json', file_data: 'e30=' })
  assert.equal(results.get('command-id').segments[0].type, 'html')
})

test('attachment read failures refuse dispatch and preserve the command failure', async () => {
  const failure = new Error('图片读取失败')
  let called = false
  const result = await runSlashCommand({ call() { called = true } }, makeResultStore(), {
    rawInput: '评分', signal, attachments: [image],
  }, () => { throw failure })
  assert.equal(called, false)
  assert.equal(result.kind, 'error')
  assert.match(result.text, /图片读取失败/)
  await assert.rejects(readAttachments({ get: () => null }, [image], signal), /附件服务不可用/)
  await assert.rejects(readAttachments(ctx, [file, file], signal), /一次只接受一个文件/)
})

test('no attachments and canceled commands keep their original semantics', async () => {
  assert.deepEqual(await readAttachments({ get: () => null }, [], signal), { images: [] })
  const controller = new AbortController()
  controller.abort()
  const result = await runSlashCommand({ call() { throw new Error('aborted') } }, makeResultStore(), {
    rawInput: '查询', signal: controller.signal,
  })
  assert.equal(result.kind, 'error')
  assert.match(result.text, /已取消/)
})

async function clientFixture(execution, { deferred = [] } = {}) {
  let plugin, source
  const slots = new Map()
  const pending = new Map()
  const requests = []
  const react = {
    createElement: (type, props, ...children) => ({ type, props, children }),
    useState: (initial) => [typeof initial === 'function' ? initial() : initial, () => {}],
    useEffect: () => {}, useRef: (value) => ({ current: value }), useCallback: (fn) => fn,
  }
  const sandbox = {
    window: { __ModuleLoader__: { load: ({ factory }) => { plugin = factory(() => react) } } },
    document: { body: {}, head: { appendChild() {} }, getElementById: () => ({}), querySelectorAll: () => [] },
    MutationObserver: class { observe() {} },
    localStorage: { getItem: (key) => key === 'ww-slash-prefixes' ? '["/ww","/xw"]' : null, setItem() {} },
    fetch: async (path, options) => {
      requests.push({ path, options })
      return { ok: true, json: async () => ({ ok: true, prefixes: ['ww', 'xw'], segments: [] }) }
    },
    setTimeout, clearTimeout,
  }
  vm.runInNewContext(await readFile(new URL('../lib/client.js', import.meta.url), 'utf8'), sandbox)
  const ctx = {
    effect: (setup) => setup(),
    on: () => () => {},
    inject: (dependencies, setup) => setup(ctx),
    remote: { commands: { execute: execution } },
    inputTriggers: { registerSource: (registered) => { source = registered } },
    slots: {
      inject: (name, setup) => deferred.includes(name) ? pending.set(name, setup) : setup(),
      register: (spec, view) => {
        const key = spec.name + ":" + (spec.key || spec.id)
        slots.set(key, view)
        return () => slots.delete(key)
      },
    },
  }
  plugin.apply(ctx)
  return { source, slots, requests, declare: (name) => pending.get(name)() }
}

test('compact slash claims follow the DSH 0.2 contract and forward attachments once', async () => {
  const calls = []
  const { source } = await clientFixture(async (...args) => {
    calls.push(args)
    return { ok: true, value: { result: { kind: 'success' } } }
  })
  assert.equal(await source.matchEnter({ sessionId: 'session' }, '/ww 查询'), undefined)
  const { claim } = await source.matchEnter({ sessionId: 'session' }, '/xw评分')
  assert.equal(claim.name, 'xw')
  assert.equal(claim.token, '/xw ')
  assert.equal(claim.attachments, true)
  const images = [{ type: 'image', data: 'image-base64', mediaType: 'image/png' }]
  assert.equal((await claim.submit('', {}, images)).kind, 'success')
  assert.deepEqual(calls, [['session', '/ww 评分', images]])
})

test('compact slash failures return error so the composer retains attachments', async () => {
  const { source } = await clientFixture(async () => ({ ok: true, value: { result: { kind: 'error', text: '评分失败' } } }))
  const { claim } = await source.matchEnter({ sessionId: 'session' }, '/ww评分')
  assert.equal((await claim.submit('', {}, [])).text, '评分失败')
})

test('rc.7 arity fallback only retries argument validation without attachments', async () => {
  const calls = []
  const { source } = await clientFixture(async (...args) => {
    calls.push(args)
    if (args.length === 3) throw new Error('expected 2 business arguments')
    return { ok: true, value: { result: { kind: 'success' } } }
  })
  const { claim } = await source.matchEnter({ sessionId: 'session' }, '/ww查询')
  assert.equal((await claim.submit('', {}, [])).kind, 'success')
  assert.deepEqual(calls.map(args => args.length), [3, 2])
  calls.length = 0
  await assert.rejects(claim.submit('', {}, [image]), /expected 2 business arguments/)
  assert.equal(calls.length, 1)
})

test('settled tool cards use current metadata and the real session for follow-up commands', async () => {
  const { slots, requests } = await clientFixture()
  const view = slots.get('tool.call.toolview:waves')
  const tree = view({ sessionId: 'session', callId: 'tool-id', phase: 'result', block: {
    kind: 'tool-result', call: { name: 'waves', argsRaw: '{"command":"ww查询"}' },
    meta: { segments: [{ type: 'text', text: '查询结果' }] },
  } })
  const find = (node) => node && typeof node === 'object' && (
    node.props?.seg ? node : node.children?.flat().map(find).find(value => value && typeof value === 'object')
  )
  const segment = find(tree)
  assert.equal(segment.props.seg.text, '查询结果')
  await segment.props.onCommand('ww椿面板')
  const request = requests.find(({ path }) => path === '/waves-api/api/chat')
  assert.equal(JSON.parse(request.options.body).session_id, 'session')
})

test('service env drops bracketed no_proxy entries that httpx rejects', async () => {
  const { serviceEnv } = await import('../lib/host/service.js')
  const env = serviceEnv(9777, { no_proxy: 'localhost,127.0.0.1,::1,[::1]', NO_PROXY: '[::1]', HTTP_PROXY: 'http://127.0.0.1:1' })
  assert.equal(env.no_proxy, 'localhost,127.0.0.1,::1')
  assert.equal(env.NO_PROXY, '')
  assert.equal(env.HTTP_PROXY, 'http://127.0.0.1:1')
  assert.equal(env.ROVER_PORT, '9777')
  assert.equal(serviceEnv(1, {}).no_proxy, undefined)
})

test('config page lives on the plugins page and falls back to settings only without it', async () => {
  const { slots } = await clientFixture()
  assert.ok(slots.has('plugins.bundle.config:dsh-plugin-waves'))
  assert.ok(!slots.has('settings.section:waves'))

  const legacy = await clientFixture(undefined, { deferred: ['plugins.bundle.config'] })
  assert.ok(legacy.slots.has('settings.section:waves'))
  legacy.declare('plugins.bundle.config')
  assert.ok(legacy.slots.has('plugins.bundle.config:dsh-plugin-waves'))
  assert.ok(!legacy.slots.has('settings.section:waves'))
})
