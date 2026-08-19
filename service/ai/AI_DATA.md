# 鸣潮数据与脚本指南

本地存了什么、怎么读、怎么用插件自带的评分内核自己算。
出图和常规查询走 waves 工具下命令；要精确数值或跨角色统筹，按这份写脚本。

## 铁律

- **不改用户数据**。`service/data/` 只读，包括 `players/`、`*.db`、`config.json`、`show/`。
  不要写、不要删、不要"顺手修一下"。改配置只能由用户在设置页点，改账号数据只能由用户发命令。
- 要写东西就用 `wwdata.scratch()`（系统临时目录下的 `dsh-waves-scratch/`，会建好并返回路径）：
  模拟数据、中间结果、脚本产物都落这里。沙箱只放行临时目录和工作区，别往 data 里写。
- sqlite 只能只读打开：`sqlite3.connect("file:...?mode=ro&immutable=1", uri=True)`。
  服务正在写这个库，用读写连接会把它写坏。
- **数据旧了就先刷新再读**。每份数据都带时间戳，见下节。刷新靠跑命令，不是自己去动文件。

## 数据新鲜度

| 想要的东西 | 文件 | 刷新命令 |
|---|---|---|
| 角色面板 | `players/<uid>/rawData.json.gz` | `ww刷新面板`（全量，慢）/ `ww刷新<角色>面板` |
| 账号概览 | `players/<uid>/baseInfo.json` | `ww查询` |
| 矩阵 | `players/<uid>/matrixData.json.gz` | `ww矩阵` |
| 深塔 | `players/<uid>/rover.json.gz` | `ww深塔` |
| 冥海 | `players/<uid>/slashData.json.gz` | `ww海墟` |
| 抽卡 | `players/<uid>/gacha_logs.json.gz` | `ww抽卡记录` |

挑战数据里有 `record_time`（秒级时间戳），面板数据看文件 mtime。
距离用户提及超过一两天、或者用户刚说"我又打了一轮"，先用 waves 工具跑一次对应命令读取拉取数据。

## 起手式

跑脚本用服务自己的解释器（Linux/macOS：`<service>/.venv/bin/python`，Windows：`<service>/.venv/Scripts/python.exe`），
系统 python 缺依赖，评分相关的接口会直接报错。

```python
import sys; sys.path.insert(0, "<service>/tools")   # <service> 见工具说明里的绝对路径
import wwdata as w

uid = w.default_uid()          # 当前默认账号（wavesbind 里的第一个）
w.bound_uids()                 # 绑过的全部账号
w.base_info(uid)               # 名字/等级/世界等级/激活天数
```

`wwdata` 只读，且已经把 gzip、别名、评分模板这些琐事包好了。直接读 json 也行，但别绕过只读约束。

## 角色与练度

```python
w.roster(uid)     # 紧凑一行式: "卡提希娅 Lv90 6链 不屈命定之冠5阶 声骸176.7"
w.roster(uid, 10) # 只要练度最高的 10 个

w.roles(uid)      # 完整结构, 需要逐项判断时才用
# {'id','name','level','attribute','chain'(命座数),'weapon':{'name','level','reson'},
#  'skills':{'常态攻击':10,...},'echo_score','sonatas':{'沉日劫明':5}}
```

只想知道"有谁、练到什么程度"就用 `roster`；四五十个角色的 `roles` 全量结构没必要整份摊开。

**练度不一是常态**，给建议前先看清：`level`、`chain`、`weapon.reson`（谐振阶数）、`skills`、`echo_score`。
一个 0 链 90 级配专武的角色和一个 6 链 70 级配三星武器的，不能当同一个东西排。

名字/别名（别自己猜简称）：

```python
w.resolve("洛可可")      # 别名 → 正式名，认不出返回 None
w.resolve_sonata("暗套")  # 套装别名 → 正式名
w.name(1507)             # 角色 id → 名字
w.char_id("椿")          # 名字 → id
w.id2name()              # 全表，够用就别再去读 alias 文件
```

别名原始表在 `data/XutheringWavesUID/alias/`（`char_alias.json`、`sonata_alias.json`、`echo_alias.json`、
`weapon_alias.json`），只有 `w.resolve` 认不出来时才需要翻。

用户话里出现别名时，插件会在上下文尾部补一条对照（"暗套→沉日劫明"这种）。那是按子串匹配来的，
可能误命中，别当成用户已经确认的指代；拿不准就按用户原话问一句。

## 声骸与评分

```python
w.echoes(uid)                          # 全部已装备声骸拉平成一张表
w.echoes(uid, sonata="沉日劫明")        # 按套装筛
w.echoes(uid, char="椿")               # 按角色筛
# 每项: owner/owner_id/slot/cost/level/sonata/echo/main/subs/raw

w.score(uid, "洛可可", echo)   # 把这件放到洛可可的评分模板下打分 → {score,grade,template,char}
w.total_score(uid, "椿", echo_list)
w.calc_temp(uid, "椿")        # 该角色当前的评分模板（词条权重）
```

分数来自插件自带的评分内核（各角色模板不同），**不是伤害模拟**。要伤害对比就跑 `ww<角色>伤害`。

只有已装备的声骸会出现在数据里；仓库里没戴的读不到。

## 场景一：优化矩阵配队

```python
ms = w.matrix_summary(uid)
# {'record_time', 'reward', 'total_reward',
#  'modes':[{'mode_id','rank','score','pass_boss','boss_count','round',
#            'teams':[{'roles':['赞妮','菲比','白芷'],'pass_boss','boss_count','buffs':[...]}]}],
#  'stage_roles': {'1_0': ['赞妮','菲比','白芷'], ...}}   # 各层实到阵容
```

做法：

1. `matrix_summary` 看哪层卡住（`pass_boss < boss_count`）、当前用了谁、这层的 buff 是什么。
2. `roles(uid)` 拿全部持有角色和练度，注意别推荐没有的角色，也别把低练度角色当核心。
3. buff 描述里往往点名了机制（异常效应、虚湮、共鸣解放等），据此决定配队方向。
4. 需要版本环境/流行配队时可以联网查，但**必须回到第 2 步过滤成用户真有的角色**，
   并按练度给出"现在能上的"和"值得练的"两档。
5. 想验证输出强度，对候选主 C 跑 `ww<角色>伤害` 看期望伤害。

## 场景二：一套声骸在多角色间怎么分

沉日劫明这类套装会被丹瑾、弗洛洛、椿、洛可可、坎特蕾拉、千咲等多人共用，但吃的词条不一样，
所以同一件在不同人身上分数差很多，互换有可能双赢。但注意不是随便换，需要受到装配cost<=12且同套装（不论2、3还是5件套）内声骸不能重复，
且注意部分角色使用3+2搭配等，比如千咲/弗洛洛可能只有2件是沉日劫明，另外3件由于跨套装一般不考虑更换

```python
w.sonata_pool(uid, "沉日劫明")     # {角色: [该套装的声骸...]}
w.cross_scores(uid, "沉日劫明")    # 每件 × 每个候选角色的交叉分，按"换人能涨多少"排序
w.swap_gains(uid, "沉日劫明")      # 直接给出总分净增益为正的两两互换（只在 cost 相同的件之间）
```

`cross_scores` 是证据，`swap_gains` 是结论。`swap_gains` 空不代表没优化空间——
它只换 cost 相同的件；`cross_scores` 里 `gain_vs_owner` 高但换不动的，通常是槽位 cost 对不上，
这种要在建议里说清楚（"这件在弗洛洛身上更值，但他没有 4c 槽"）。

想把候选角色扩到还没戴这套的人：`w.cross_scores(uid, "沉日劫明", chars=["千咲", "坎特蕾拉"])`。

### 把截图里的声骸也放进池子

`ww评分 <角色><cost>c(主词条)` 带图会走远端识图评分，回的是一张卡片。
要让新声骸参与本地推演，把截图上的词条转录出来自己造一件：

```python
new = w.make_echo(
    cost=4, sonata="沉日劫明", echo_name="无冠者",
    main=[("攻击", "18.0%"), ("暴击伤害", "44.0%")],
    subs=[("暴击", "8.1%"), ("攻击", "11.6%"), ("共鸣效率", "8.4%"),
          ("重击伤害加成", "9.9%"), ("攻击", "40")],
)
for c in ["椿", "洛可可", "弗洛洛"]:
    print(c, w.score(uid, c, new))
```

词条名和值照抄面板原文（带 `%` 就带上）。

## 直接读文件

`wwdata` 没覆盖到的，自己读也行，路径都在 `data/XutheringWavesUID/`：

- `resource/map/detail_json/char/<角色id>.json` 角色详情：技能树、共鸣链、成长曲线、属性
- `resource/map/detail_json/` 下还有 `weapon`、`echo`、`sonata`、`forte`、`material`、`challenge`
- `resource/map/CharId2Data.json`、`id2name.json`
- `players/<uid>/state.json` 每个角色的查看/刷新次数（用户最近在关注谁）
- `players/<uid>/gachaStats.json` 各卡池 `total/avg/remain/up_count`

## 跑命令

要刷新数据、要出图、要用插件已有的分析（伤害、优化建议、练度、排行），
直接调 waves 工具下命令，别自己重写一遍。命令清单看 `ww帮助`，或工具说明里的常用列表。
