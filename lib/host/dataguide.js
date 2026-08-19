// 开了"AI 可使用鸣潮插件"时一并给出的数据地图。
// 只放常驻部分: 够模型判断"要不要深挖", 细节让它按需去读 service/ai/AI_DATA.md, 省上下文也吃得到缓存
import path from 'node:path'

import { venvPython } from './service.js'

export function dataGuide(serviceDir) {
  const service = serviceDir || '.'
  const data = path.join(service, 'data')
  const ww = path.join(data, 'XutheringWavesUID')
  return [
    '',
    '除了下命令出图，你还可以直接读本地数据、写脚本自己算（用户问"最优/怎么分配/帮我规划"这类',
    '需要跨角色统筹的问题时就该这么做）：',
    `- 只读库 ${path.join(service, 'tools', 'wwdata.py')}（跑脚本一律用服务自己的解释器`,
    `  ${venvPython(service)}，系统 python 缺依赖）：`,
    '  default_uid() / roles(uid) 角色与练度 /',
    '  echoes(uid, sonata=) 声骸 / score(uid, 角色, 声骸) 按该角色评分模板打分 /',
    '  cross_scores()、swap_gains() 同套装跨角色换装推演 / matrix_summary() 矩阵战绩 /',
    '  resolve() 别名转正式名 / id2name()',
    `- 玩家原始数据 ${path.join(ww, 'players')}/<特征码>/：rawData.json.gz 面板、matrixData/slashData/`,
    '  rover.json.gz 挑战、gacha_logs.json.gz 抽卡、baseInfo.json 概览（.gz 要先解压）',
    `- 静态资料 ${path.join(ww, 'resource', 'map')}/：CharId2Data.json 角色 id↔名、detail_json/ 角色武器声骸详情`,
    `- 字段清单、两类统筹场景的完整做法，看 ${path.join(service, 'ai', 'AI_DATA.md')}（按需读，别整份贴）`,
    '规矩：',
    `- ${data} 只读，不写不删不"顺手修"。要落中间结果就用 wwdata.scratch()（系统临时目录下），`,
    '  沙箱只放行临时目录和工作区。改用户数据只能由用户自己发命令或在设置页操作。',
    '- sqlite 一律 file:...?mode=ro&immutable=1 只读打开，服务正在写，读写连接会损坏库。',
    '- 数据可能过期：挑战数据看 record_time，面板看文件 mtime。旧了先用本工具跑对应命令刷新',
    '  （面板 ww刷新面板 / 矩阵 ww矩阵 / 深塔 ww深塔 / 海墟 ww海墟 / 抽卡 ww抽卡记录 / 概览 ww查询），再读。',
    '- 插件已有的分析别重写：伤害 ww<角色>伤害、词条优化 ww<角色>优化、练度 ww练度、排行 ww<角色>总排行。',
  ].join('\n')
}
