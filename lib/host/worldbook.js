// 世界书: 用户话里首次命中知识触发词时, 把对应条目附进上下文; 同一会话同一条目只注入一次。
import { createUserMessage } from '@deepseek-ai/dsh-llm'

const PLUGIN = 'waves-kb'
const SESSION_MAX = 10

// agentId -> Set<entryId>
const injected = new Map()

function userText(messages) {
  const out = []
  for (const message of messages || []) {
    const kind = message?.source?.kind
    if (kind && kind !== 'user') continue
    for (const block of message?.content || []) {
      if (block?.type === 'text' && block.text) out.push(block.text)
    }
  }
  return out.join('\n').slice(0, 2000)
}

function render(hits) {
  const parts = hits.map(
    (h) => `【${h.title}】(id ${h.id}, 命中"${h.trigger}")\n${h.content}`,
  )
  return [
    '鸣潮资料（关键词命中自动附带，同一条目本会话只出现一次）：',
    ...parts,
    '仅按字面命中，可能与用户所指无关；用得上再用。全文与更多条目用 wwdata 的 kb()/kb_get()。',
  ].join('\n')
}

export function registerWorldbook(ctx, client) {
  ctx.inject(['agents'], (actx) => {
    actx.on(
      'agent/pre-step',
      async (payload, next) => {
        const decision = await next()
        if (decision.kind === 'reject' || payload.signal?.aborted) return decision
        const text = userText(decision.messages)
        if (!text) return decision
        const seen = injected.get(payload.agent.id) || new Set()
        if (seen.size >= SESSION_MAX) return decision
        let hits = []
        try {
          const data = await client.call(
            `/api/knowledge/lookup?text=${encodeURIComponent(text)}&exclude=${[...seen].join(',')}`,
            { timeoutMs: 1500, signal: payload.signal },
          )
          hits = (data && data.hits) || []
        } catch {
          return decision
        }
        if (!hits.length) return decision
        for (const hit of hits) seen.add(hit.entry || hit.id)
        injected.set(payload.agent.id, seen)
        const note = render(hits)
        return {
          kind: 'enter',
          messages: [
            ...decision.messages,
            createUserMessage({
              content: [{ type: 'text', text: note }],
              source: {
                kind: 'plugin',
                plugin: PLUGIN,
                form: 'snapshot',
                sections: [{ name: PLUGIN, text: note }],
              },
            }),
          ],
        }
      },
      { prepend: true },
    )

    actx.on('agent/disposed', (payload) => {
      injected.delete(payload?.agent?.id)
    })
  })
}
