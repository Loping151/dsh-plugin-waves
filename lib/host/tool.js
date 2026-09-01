// 模型工具: 自然语言场景由模型转成命令调用
import { defineTool } from '@deepseek-ai/dsh-tools'

import { dataGuide } from './dataguide.js'
import { takeImages } from './imagebridge.js'
import { troubleshooting } from './troubleshoot.js'

// 最近一批用户图片 → base64:// 列表, 交给服务的 images 字段
async function collectImages(ctx, exec) {
  const agentId = exec?.agent?.id
  const attachments = ctx.get?.('attachments')
  if (!agentId || !attachments) return []
  const out = []
  for (const ref of takeImages(agentId)) {
    try {
      const { data } = await attachments.readImage(ref, exec?.signal)
      out.push('base64://' + Buffer.from(data).toString('base64'))
    } catch (e) {
      console.log(`[waves] 附件读取失败 ${ref?.attachmentId}: ${String(e?.message || e)}`)
    }
  }
  return out
}

export function registerTool(ctx, client, serviceDir) {
  ctx.tools.register(
    defineTool({
      name: 'waves',
      description: [
        '鸣潮（Wuthering Waves）全功能查询。把用户的鸣潮相关请求转成一条命令传入 command。',
        '命令带 ww 前缀（不带会自动补）。常用：',
        'ww查询 / ww体力 / ww深塔 / ww海墟 / ww矩阵 / ww全息 / ww探索 / ww练度 / ww声骸 / ww日历 / ww库洛币',
        'ww<角色名>面板（如 ww椿面板）/ ww<角色名>伤害 / ww<角色名>优化 / ww<角色名>权重 / ww<角色名>攻略 / ww<角色名>图鉴',
        'ww<角色名>总排行 / ww练度总排行 / ww抽卡记录 / ww签到 / ww兑换码 / ww帮助 / ww公告',
        '绑定与登录：ww绑定<特征码> / ww登录 / ww添加token<token> / ww切换<特征码>',
        '结果里的图文卡片会直接展示在界面上，其中的角色可点击查看面板，无需你再复述内容；',
        'summary 里带有卡片上的文字与数值（含各队角色名），要引用具体数字时看它就够了。',
        '同一条命令不要重复调用；本机只有一个使用者，群聊/私聊之分已取消，private 一般不用填，',
        '结果看着不够详细也别靠它重试，改用下面的数据接口。',
        dataGuide(serviceDir),
      ].join('\n'),
      parameters: {
        command: {
          type: 'string',
          required: true,
          description: '要执行的鸣潮命令，例如 "ww查询"、"ww椿面板"、"ww绑定100000001"',
        },
        private: {
          type: 'boolean',
          description: '是否按私聊场景执行（获取ck 等仅私聊可用的命令需要设为 true）',
        },
        with_image: {
          type: 'boolean',
          description:
            '用户本条消息附了图片、且该命令要用到它时设为 true（如 ww评分 / ww分析 的声骸截图），图片会随命令转交服务',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            ok: { type: 'boolean', required: true },
            summary: { type: 'string', required: true },
            matched: { type: 'array', items: { type: 'string' } },
            segments: { type: 'array', items: { type: 'object', additionalProperties: true } },
            elapsed: { type: 'number' },
          },
        },
        render: (_args, value) => [
          { type: 'text', text: value?.summary || (value?.ok ? '已执行' : '执行失败') },
        ],
        presentationMeta: (_args, value) => ({
          segments: value?.segments ?? [],
          matched: value?.matched ?? [],
        }),
      },
      timeoutMs: 300000,
      async execute(args, exec) {
        try {
          await client.call('/api/health', { timeoutMs: 4000 })
        } catch (e) {
          return {
            ok: false,
            summary: troubleshooting(serviceDir, String(e?.message || e)),
            matched: [],
            segments: [],
          }
        }
        const images = args.with_image ? await collectImages(ctx, exec) : []
        const data = await client.call('/api/chat', {
          method: 'POST',
          body: {
            command: String(args.command || ''),
            scene: args.private ? 'direct' : 'group',
            session_id: exec?.agent?.id || 'dsh',
            images,
          },
          signal: exec?.signal,
        })
        if (args.with_image && !images.length && data && typeof data.summary === 'string') {
          data.summary += '\n(注: 没有取到用户图片, 命令按无图执行)'
        }
        return data
      },
      presentCall: (args) => ({
        card: 'generic',
        kind: 'other',
        title: `鸣潮 · ${String(args?.command || '').slice(0, 40)}`,
        rawInput: args,
      }),
    }),
  )

  ctx.tools.register(
    defineTool({
      name: 'waves_panel',
      description: [
        '鸣潮自定义面板: 按你组装的数据渲一张完整角色面板卡(声骸可跨角色引用或凭空自定义)。',
        '用于"这套声骸给X用效果如何/把截图转录的声骸装上看看"这类假设推演。',
        'echoes 每项替换一个槽位(slot 1-5, 缺省按下标), 二选一:',
        '- 引用现有: {"slot":1, "from":{"char":"洛可可","slot":2}}',
        '- 全量自定义: {"slot":2, "name":"无冠者", "cost":4, "sonata":"沉日劫明",',
        '  "main":[["暴击","22.0%"],["攻击","150"]], "subs":[["暴击伤害","21.0%"],...]}',
        '词条名和数值照面板原文(带 % 就带上); cost 只能 1/3/4 且总和 ≤12。',
        'change 可选, 走换装文本管线(如 "换6链 换苍鳞千嶂 谐振5")。',
        '结果只在本地渲染, 不写用户数据、不上传总排行; 未给 echoes/change 时就是原样面板。',
      ].join('\n'),
      parameters: {
        char: {
          type: 'string',
          required: true,
          description: '角色名或别名, 如 "椿"',
        },
        uid: { type: 'string', description: '特征码, 缺省用当前绑定' },
        echoes: {
          type: 'array',
          items: { type: 'object', additionalProperties: true },
          description: '要替换的声骸列表, 格式见工具说明',
        },
        change: { type: 'string', description: '附加换装文本, 如 "换6链 换苍鳞千嶂"' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            ok: { type: 'boolean', required: true },
            summary: { type: 'string', required: true },
            segments: { type: 'array', items: { type: 'object', additionalProperties: true } },
          },
        },
        render: (_args, value) => [
          { type: 'text', text: value?.summary || (value?.ok ? '已渲染' : '渲染失败') },
        ],
        presentationMeta: (_args, value) => ({
          segments: value?.segments ?? [],
          matched: value?.matched ?? [],
        }),
      },
      timeoutMs: 300000,
      async execute(args, exec) {
        try {
          await client.call('/api/health', { timeoutMs: 4000 })
        } catch (e) {
          return {
            ok: false,
            summary: troubleshooting(serviceDir, String(e?.message || e)),
            segments: [],
          }
        }
        return await client.call('/api/render/panel', {
          method: 'POST',
          body: {
            char: String(args.char || ''),
            uid: args.uid ? String(args.uid) : null,
            echoes: Array.isArray(args.echoes) ? args.echoes : null,
            change: args.change ? String(args.change) : null,
          },
          signal: exec?.signal,
        })
      },
      presentCall: (args) => ({
        card: 'generic',
        kind: 'other',
        title: `鸣潮 · ${String(args?.char || '')}自定义面板`,
        rawInput: args,
      }),
    }),
  )
}
