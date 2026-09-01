// pre-step 剥离用户消息里的 image block(文本路由带图会让后续每轮请求报错)并暂存引用;
// waves 工具 with_image=true 时取回转发给服务。
import { homedir } from 'node:os'
import { join } from 'node:path'

import { freezeMessage } from '@deepseek-ai/dsh-llm'

// 与 dsh-attachment-local 的 objectPath 一致: objects/<hex前2>/<hex>, 无扩展名
function storedPath(ref) {
  const hex = String(ref?.attachmentId || '').replace(/^sha256:/, '')
  if (!/^[a-f0-9]{64}$/.test(hex)) return null
  const home = process.env.DSH_HOME || join(homedir(), '.dsh')
  return join(home, 'attachments', 'v1', 'objects', hex.slice(0, 2), hex)
}

// agentId -> ImageAttachmentRef[]; 新图整组替换, 只保留最近一批
const pending = new Map()

export function takeImages(agentId) {
  return pending.get(agentId) ?? []
}

export function registerImageBridge(ctx) {
  // 放行文本模型的带图消息(否则 host 直接拒收"当前模型不支持图片"), 图随后在 pre-step 被剥离旁路。
  // 模态抹成 undefined 而非加 "image": prompt 门(显式不含才拒)放行,
  // read_image/MCP 图片门(要求显式包含)维持拦截, image block 进不了会话历史。
  ctx.inject(['llm'], (lctx) => {
    lctx.effect(() => {
      const llm = lctx.llm
      const original = llm.resolveModelInfo
      llm.resolveModelInfo = async function (provider, model, signal) {
        const info = await original.call(this, provider, model, signal)
        if (info && Array.isArray(info.inputModalities) && !info.inputModalities.includes('image')) {
          const { inputModalities, ...rest } = info
          return rest
        }
        return info
      }
      return () => {
        llm.resolveModelInfo = original
      }
    })
  })

  ctx.inject(['agents'], (actx) => {
    actx.on(
      'agent/pre-step',
      async (payload, next) => {
        const decision = await next()
        if (decision.kind === 'reject' || payload.signal?.aborted) return decision

        const refs = []
        for (const message of decision.messages) {
          for (const block of message?.content || []) {
            if (block?.type === 'image' && block.attachment) refs.push(block.attachment)
          }
        }
        if (!refs.length) return decision
        pending.set(payload.agent.id, refs)

        const listed = refs
          .map((r) => {
            const p = storedPath(r)
            return `${r.mediaType} ${r.width}x${r.height}${p ? ` → ${p}` : ''}`
          })
          .join('\n')
        const note =
          `[用户随消息附了 ${refs.length} 张图片，已暂存:\n${listed}]\n` +
          '你看不到图片内容。若该图是给鸣潮功能用的(如声骸评分/分析截图)，' +
          '调用 waves 工具时把 with_image 设为 true，图片会随命令一起交给鸣潮服务。' +
          '上面的路径是图片原文件(按内容寻址, 无扩展名)，有读图能力的工具可直接读它。'
        const messages = decision.messages.map((message) => {
          if (!(message?.content || []).some((block) => block?.type === 'image')) return message
          const content = message.content.filter((block) => block?.type !== 'image')
          content.push({ type: 'text', text: note })
          return freezeMessage({ ...message, content })
        })
        return { kind: 'enter', messages }
      },
      { prepend: true },
    )

    actx.on('agent/disposed', (payload) => {
      pending.delete(payload?.agent?.id)
    })
  })
}
