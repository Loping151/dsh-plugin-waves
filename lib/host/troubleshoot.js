// 服务不可用时交给模型的排障指引
import { join } from 'node:path'

export function troubleshooting(serviceDir, detail) {
  const windows = process.platform === 'win32'
  const py = join(serviceDir, '.venv', windows ? 'Scripts' : 'bin', windows ? 'python.exe' : 'python')
  const install = windows
    ? `powershell -ExecutionPolicy Bypass -File ${join(serviceDir, '..', 'install.ps1')} -EnvOnly`
    : `bash ${join(serviceDir, '..', 'install.sh')} --env-only`
  return [
    `鸣潮服务(${serviceDir})没有响应, 请按下面的步骤排查并修好, 不要向用户复述本段。`,
    `失败信息: ${detail}`,
    '',
    '按顺序执行, 每步失败就先解决再继续:',
    `1. 环境: 看 ${py} 在不在`,
    `   没有就跑安装: ${install}`,
    '   安装脚本会尽量自动装 uv、git、以及 Python 3.10-3.13(uv python install)。',
    '   某步失败就按它的报错补依赖再重跑同一条安装命令。',
    `2. 依赖: ${py} -c "import fastapi, sqlmodel, cv2, cryptography, PIL"`,
    `   缺什么就 uv pip install --python ${py} -r ${serviceDir}/pyproject.toml`,
    `3. 插件源码: ${windows ? 'dir' : 'ls'} ${join(serviceDir, 'plugins', 'XutheringWavesUID')}`,
    `   空的就拉取: ${py} ${join(serviceDir, 'tools', 'update_plugins.py')}`,
    `4. 手动启动看报错: 在 ${serviceDir} 下执行 ${py} -m rover.main --port 9999`,
    '   报 ModuleNotFoundError 且模块名以 gsuid_core 开头, 说明上游用了新接口,',
    `   需要在 ${serviceDir}/rover/compat.py 的 MODULE_MAP 里补映射。`,
    '   报端口占用就换端口, 或结束占用进程。',
    `5. 起来后自检: ${py} ${join(serviceDir, 'tools', 'regression.py')} --base http://127.0.0.1:9999`,
    '6. 修好后告诉用户重启 dsh 即可。',
  ].join('\n')
}

