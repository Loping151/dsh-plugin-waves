// /waves-api 反代与命令结果回取
import { PROXY_PREFIX, RESULT_PATH, SESSION_PATH } from './consts.js'

export function registerProxy(ctx, client, results) {
  // 会话查在这个作用域里拿, 拿不到就当查不了, 由前端按"能下命令"处理
  let sessions = null
  ctx.inject(['sessions'], (sctx) => {
    sessions = sctx.sessions
    sctx.effect(() => () => {
      sessions = null
    })
  })

  ctx.inject(['webServer'], (wctx) => {
    wctx.effect(() =>
      wctx.webServer.register({
        kind: 'prefix',
        path: PROXY_PREFIX,
        handler: async (req, res) => {
          const rest = req.url.slice(PROXY_PREFIX.length)
          if (rest.startsWith(SESSION_PATH)) {
            const id = decodeURIComponent(rest.slice(SESSION_PATH.length).split('?')[0])
            const alive = sessions ? sessions.get(id) !== undefined : null
            res.writeHead(200, { 'content-type': 'application/json' })
            res.end(JSON.stringify({ alive }))
            return
          }
          if (rest.startsWith(RESULT_PATH)) {
            const id = decodeURIComponent(rest.slice(RESULT_PATH.length).split('?')[0])
            const found = results.get(id)
            res.writeHead(found ? 200 : 404, { 'content-type': 'application/json' })
            res.end(JSON.stringify(found || { error: '结果已过期' }))
            return
          }
          const target = client.base + rest
          try {
            const chunks = []
            for await (const chunk of req) chunks.push(chunk)
            const upstream = await fetch(target, {
              method: req.method,
              headers: req.headers['content-type']
                ? { 'content-type': req.headers['content-type'] }
                : undefined,
              body: chunks.length ? Buffer.concat(chunks) : undefined,
            })
            const buf = Buffer.from(await upstream.arrayBuffer())
            res.writeHead(upstream.status, {
              'content-type': upstream.headers.get('content-type') || 'application/octet-stream',
            })
            res.end(buf)
          } catch (e) {
            res.writeHead(502, { 'content-type': 'application/json' })
            res.end(JSON.stringify({ error: String(e?.message || e) }))
          }
        },
      }),
    )
  })
}
