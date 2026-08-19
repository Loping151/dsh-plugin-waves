// 共享常量
export const PKG_NAME = 'dsh-plugin-waves'

export const PROXY_PREFIX = '/waves-api'

// 命令卡片按 commandId 回取图文段的路径; 结果带落盘, 重启后仍能还原
export const RESULT_PATH = '/host/results/'
// 会话是否已经真的建起来了; 闪屏上还没有会话, 命令下不去
export const SESSION_PATH = '/host/session/'
export const RESULT_KEEP = 200

export const SLASH_USAGE = [
  '用法: /ww <命令>',
  '例: /ww 查询 · /ww 深塔 · /ww 椿面板 · /ww 签到 · /ww 帮助',
  '命令不带 ww 前缀会自动补; 开头加 -p 按私聊执行（如 /ww -p 获取ck）',
].join('\n')
