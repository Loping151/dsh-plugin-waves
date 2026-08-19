// /ww 斜杠命令: 直接打服务, 不经过模型
import { SLASH_USAGE } from './consts.js'
import { resultText } from './results.js'

export function parseSlashInput(rawInput) {
  let command = String(rawInput || '').trim()
  let scene = 'group'
  const flag = /^(-p|--private)(\s+|$)/.exec(command)
  if (flag) {
    scene = 'direct'
    command = command.slice(flag[0].length).trim()
  }
  return { command, scene }
}

// 斜杠命令直接打服务, 不经过模型
export async function runSlashCommand(client, results, invocation) {
  const { command, scene } = parseSlashInput(invocation.rawInput)
  if (!command) return { kind: 'error', text: SLASH_USAGE }
  try {
    const data = await client.call('/api/chat', {
      method: 'POST',
      body: { command, scene, session_id: invocation.agent?.id || 'dsh' },
      signal: invocation.signal,
    })
    if (!data?.ok) return { kind: 'error', text: data?.summary || `执行失败: ${command}` }
    results.put(invocation.commandId, { command, scene, ...data })
    return { kind: 'success', text: resultText(command, data) }
  } catch (e) {
    if (invocation.signal?.aborted) return { kind: 'error', text: `已取消: ${command}` }
    return { kind: 'error', text: `${command} 执行失败: ${String(e?.message || e)}` }
  }
}

