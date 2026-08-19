import { registerAliasHint } from './host/aliashint.js'
import { runSlashCommand } from './host/command.js'
import { registerProxy } from './host/proxy.js'
import { makeResultStore } from './host/results.js'
import {
  bootstrap,
  exposeToModelFlag,
  makeClient,
  readPrefixes,
  resolveServiceDir,
  startService,
  waitReady,
} from './host/service.js'
import { registerTool } from './host/tool.js'

export const name = 'waves-plugin'
export const inject = ['tools']

export function apply(ctx, config = {}) {
  const port = config.port ?? 9777
  const serviceDir = resolveServiceDir(config)
  const client = makeClient(port)
  const results = makeResultStore(serviceDir)

  const boot = config.autoStart === false ? { ok: true } : bootstrap(serviceDir)
  if (!boot.ok) console.log(`[waves] 自动安装未完成: ${boot.reason}`)

  if (config.autoStart !== false) {
    ctx.effect(() => startService(ctx, { port, serviceDir }))
    waitReady(client).then((ok) => {
      if (!ok) console.log('[waves] 服务未能在 60s 内就绪')
    })
  }

  registerProxy(ctx, client, results)

  // commands 只在带交互界面的 profile 里存在, 软依赖
  ctx.inject(['commands'], (cctx) => {
    for (const prefix of readPrefixes(serviceDir)) {
      cctx.commands.register({
        name: prefix,
        description: '直接执行鸣潮命令，不经过模型',
        input: { hint: '<命令> 如 查询 / 深塔 / 椿面板' },
        handler: (invocation) => runSlashCommand(client, results, invocation),
      })
    }
  })

  // 零上下文: 不把工具暴露给模型, 只保留 / 命令触发, 省下这段描述占用的上下文
  if (config.exposeToModel === false || !exposeToModelFlag(serviceDir)) {
    console.log('[waves] 零上下文模式: 模型不可见, 请用 /ww 命令')
    return
  }

  registerTool(ctx, client, serviceDir)
  registerAliasHint(ctx, client)
}
