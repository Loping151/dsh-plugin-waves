// 服务进程托管: 目录解析、首启安装、拉起与健康检查
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { PKG_NAME } from './consts.js'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '../..')

export function serviceDirCandidates() {
  const home = process.env.DSH_HOME || join(process.env.HOME || process.env.USERPROFILE || '', '.dsh')
  const profiles = join(home, 'profiles')
  const out = []
  let names = []
  try {
    names = readdirSync(profiles)
  } catch {
    return out
  }
  for (const name of names) {
    // 用 file: 装的按源码目录跑(环境和数据都在克隆里, README 的用法), 找不到才用 profile 里的副本
    try {
      const manifest = JSON.parse(readFileSync(join(profiles, name, 'package.json'), 'utf8'))
      const spec = manifest?.dependencies?.[PKG_NAME]
      if (typeof spec === 'string' && spec.startsWith('file:')) {
        out.push(join(spec.slice('file:'.length), 'service'))
      }
    } catch {}
    out.push(join(profiles, name, 'node_modules', PKG_NAME, 'service'))
  }
  return out
}

export function resolveServiceDir(config) {
  const candidates = [
    config?.servicePath,
    process.env.WAVES_SERVICE_DIR,
    ...serviceDirCandidates(),
    join(ROOT, 'service'),
  ].filter((dir) => dir && existsSync(join(dir, 'rover/main.py')))
  // 已经装好的(有虚拟环境或数据)优先: 免得把跑着的实例切到一个空目录去重装
  const ready = candidates.find(
    (dir) => existsSync(venvPython(dir)) || existsSync(join(dir, 'data/config.json')),
  )
  return ready || candidates[0] || join(ROOT, 'service')
}

// 服务配置里的模型可见开关; 读文件即可, 改动本来就要重启生效
export function exposeToModelFlag(serviceDir) {
  try {
    const cfg = JSON.parse(readFileSync(join(serviceDir, 'data/config.json'), 'utf8'))
    return cfg.expose_to_model !== false
  } catch {
    return true
  }
}

// 命令前缀(逗号分隔多个); 每个前缀都注册成命令, 菜单里才都列得出来
export function readPrefixes(serviceDir) {
  try {
    const cfg = JSON.parse(readFileSync(join(serviceDir, 'data/config.json'), 'utf8'))
    const raw = String(cfg.command_prefix ?? 'ww')
    const list = raw.split(/[,，]/).map((x) => x.trim()).filter(Boolean)
    return list.length ? list : ['ww']
  } catch {
    return ['ww']
  }
}

// 虚拟环境的解释器位置随平台不同: Windows 在 Scripts\\python.exe
export function venvPython(serviceDir) {
  return join(
    serviceDir,
    '.venv',
    process.platform === 'win32' ? 'Scripts' : 'bin',
    process.platform === 'win32' ? 'python.exe' : 'python',
  )
}

export function servicePython(serviceDir) {
  const venv = venvPython(serviceDir)
  if (existsSync(venv)) return venv
  return process.platform === 'win32' ? 'python' : 'python3'
}

export function makeClient(port) {
  const base = `http://127.0.0.1:${port}`
  async function call(path, { method = 'GET', body, signal, timeoutMs = 300000 } = {}) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    const onAbort = () => controller.abort()
    if (signal) signal.addEventListener('abort', onAbort, { once: true })
    try {
      const res = await fetch(base + path, {
        method,
        headers: body ? { 'content-type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })
      const text = await res.text()
      let data
      try {
        data = text ? JSON.parse(text) : null
      } catch {
        throw new Error(`服务返回非 JSON (${res.status}): ${text.slice(0, 200)}`)
      }
      if (!res.ok) throw new Error(data?.detail || data?.error || `服务错误 ${res.status}`)
      return data
    } finally {
      clearTimeout(timer)
      if (signal) signal.removeEventListener('abort', onAbort)
    }
  }
  return { base, call }
}

// 首次启动时环境还没装好, 自动跑一次安装
export function bootstrap(serviceDir) {
  if (existsSync(venvPython(serviceDir))) return { ok: true }
  const root = join(serviceDir, '..')
  const windows = process.platform === 'win32'
  const script = join(root, windows ? 'install.ps1' : 'install.sh')
  if (!existsSync(script)) {
    return { ok: false, reason: `缺少 ${windows ? 'install.ps1' : 'install.sh'}` }
  }
  console.log('[waves] 首次启动, 正在安装运行环境(几分钟)...')
  const result = windows
    ? spawnSync(
        'powershell',
        ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, '-EnvOnly'],
        { cwd: root, stdio: 'inherit' },
      )
    : spawnSync('bash', [script, '--env-only'], { cwd: root, stdio: 'inherit' })
  if (result.status === 0) return { ok: true }
  return { ok: false, reason: `安装脚本退出码 ${result.status}` }
}

// 与 rover.restart.RESTART_EXIT 一致: 资源有 diff 后主动退出, 马上再拉起
const RESTART_EXIT = 75

export function startService(ctx, config) {
  const python = servicePython(config.serviceDir)
  let child
  let stopping = false
  let timer
  let backoff = 500

  const log = (buf, level) => {
    const line = buf.toString().trimEnd()
    if (line) ctx.logger?.[level]?.(line) ?? console.log(`[waves] ${line}`)
  }

  const launch = () => {
    if (stopping) return
    child = spawn(python, ['-m', 'rover.main', '--port', String(config.port)], {
      cwd: config.serviceDir,
      env: { ...process.env, PYTHONUNBUFFERED: '1', ROVER_PORT: String(config.port) },
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    child.stdout.on('data', (b) => log(b, 'info'))
    child.stderr.on('data', (b) => log(b, 'warn'))
    child.on('exit', (code) => {
      child = undefined
      if (stopping) return
      const asked = code === RESTART_EXIT
      const wait = asked ? 400 : backoff
      if (asked) backoff = 500
      else backoff = Math.min(backoff * 2, 10000)
      console.log(`[waves] 服务退出 code=${code}${asked ? ' (主动重启)' : ''}, ${wait}ms 后拉起`)
      timer = setTimeout(launch, wait)
    })
  }

  launch()
  const stop = () => {
    stopping = true
    if (timer) clearTimeout(timer)
    try {
      child?.kill('SIGTERM')
    } catch {}
  }
  // dsh 进程退出时连带结束服务, 避免残留
  process.on('exit', stop)
  return () => {
    process.removeListener('exit', stop)
    stop()
  }
}

export async function waitReady(client, tries = 60) {
  for (let i = 0; i < tries; i++) {
    try {
      await client.call('/api/health', { timeoutMs: 2000 })
      return true
    } catch {
      await new Promise((r) => setTimeout(r, 1000))
    }
  }
  return false
}

