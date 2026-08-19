// 模型工具: 自然语言场景由模型转成命令调用
import { defineTool } from '@deepseek-ai/dsh-tools'

import { dataGuide } from './dataguide.js'
import { troubleshooting } from './troubleshoot.js'

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
        const data = await client.call('/api/chat', {
          method: 'POST',
          body: {
            command: String(args.command || ''),
            scene: args.private ? 'direct' : 'group',
            session_id: exec?.agent?.id || 'dsh',
          },
          signal: exec?.signal,
        })
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
}
