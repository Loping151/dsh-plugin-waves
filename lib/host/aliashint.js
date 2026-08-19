// 用户话里出现鸣潮别名时, 在这一步的上下文尾部补一条对照。
// 只给线索不下断言: 别名匹配是子串命中, 完全可能是误判, 由模型自己权衡。
import { createUserMessage } from '@deepseek-ai/dsh-llm'

const PLUGIN = 'waves-alias'
const MAX_CHARS = 500

function textOf(messages) {
  const out = []
  for (const message of messages || []) {
    for (const block of message?.content || []) {
      if (block?.type === 'text' && block.text) out.push(block.text)
    }
  }
  return out.join('\n').slice(0, 2000)
}

function render(hits) {
  const items = hits.map((h) => `${h.alias}→${h.name}(${h.kind})`).join('、')
  return [
    `鸣潮（Wuthering Waves）的本地别名表里有这些相近词条：${items}。`,
    '这些是鸣潮的角色/武器/声骸/套装名，别按其他游戏的同名内容理解。',
    '仅按字面子串匹配得到，可能与用户实际所指无关；用得上再用，别当成用户已经确认的指代。',
  ]
    .join('\n')
    .slice(0, MAX_CHARS)
}

export function registerAliasHint(ctx, client) {
  ctx.inject(['agents'], (actx) => {
    actx.on(
      'agent/pre-step',
      async (payload, next) => {
        const decision = await next()
        if (decision.kind === 'reject' || payload.signal?.aborted) return decision
        // 只在用户刚说完话的那一步补, 工具往返的后续步骤不重复注入
        if (payload.step !== 1) return decision
        const text = textOf(decision.messages)
        if (!text) return decision
        let hits = []
        try {
          const data = await client.call(
            `/api/alias/lookup?text=${encodeURIComponent(text)}`,
            { timeoutMs: 1500, signal: payload.signal },
          )
          hits = (data && data.hits) || []
        } catch {
          return decision
        }
        if (!hits.length) return decision
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
  })
}
