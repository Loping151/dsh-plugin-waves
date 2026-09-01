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

跑脚本不需要沙箱升级：读 data、写 scratch 都在默认权限内，shell 工具别带
`sandbox_permissions`/`justification` 参数（同级升级会被拒，空 justification 会报错）。
Windows 下控制台输出中文会乱码：结果写成 UTF-8 文件到 `wwdata.scratch()` 再读回来，别依赖 stdout。

## 角色与练度

```python
w.roster(uid)     # 紧凑一行式: "卡提希娅 Lv90 6链 不屈命定之冠5阶 声骸176.7"
w.roster(uid, 10) # 只要练度最高的 10 个

w.roles(uid)      # 完整结构, 需要逐项判断时才用
# {'id','name','level','attribute','chain'(链数),'weapon':{'name','level','reson'},
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

角色图鉴（detail_json 的精简视图，富文本标记已剥掉，只传有效信息）：

```python
w.char_info("菲比")                  # 属性/武器型/星级/技能/共鸣链, 纯文本
w.char_info("菲比", parts=["stats"]) # 附成长数值(还可加 "ascensions")
w.detail_file("weapon", "苍鳞千嶂")   # char/weapon/echo/sonata 源文件路径
w.clean_text(s)                      # 自己读源文件时剥 <span style=...> 等标记
```

要抠 `char_info` 没带出来的原始字段（成长曲线细节、技能树 param 等）才去读 `detail_file` 指向的源文件。

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

0. **先核对周期**：`w.challenge_periods()` 拿当期开始时间，与 `matrix_summary` 的 `record_time`
   比对。record_time 早于当期 start = 上一期数据，只能当历史参考；`ww矩阵` 提示"暂无数据" =
   已换期且新一期没打（不是 bug，见 kb"挑战周期"）。当期 boss/可多次上场角色**没有接口可查**
   （矩阵接口只回个人战绩，wiki 活动说明只有时间条件）：用户没打新一期就把所缺信息一次列全
   请用户从游戏里带出来，别拆成多轮。目标不用问，默认冲总分最高。配队硬约束见 kb"矩阵配队规则"。
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

`ww评分 <角色><cost>c(主词条)` 带图（调 waves 工具时设 with_image=true）走远端识图评分，回的是一张卡片；
卡片会被本地 OCR，词条名与数值就在返回的 summary"图片文字(OCR)"里。
要让新声骸参与本地推演，把词条转录出来自己造一件——优先从评分卡的 OCR 文字里抄；
OCR 缺漏或没走评分时，能读图的路由用读图工具读上下文提示给的暂存路径，都不行就让用户打字发来，
别凭空编数值：

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

### 重组出一张完整面板卡

打分归打分，想让用户直观看到"换完之后面板长什么样"，用 `waves_panel` 工具（不是命令）：

```json
{ "char": "椿",
  "echoes": [
    { "slot": 1, "from": { "char": "洛可可", "slot": 2 } },
    { "slot": 2, "name": "无冠者", "cost": 4, "sonata": "沉日劫明",
      "main": [["暴击", "22.0%"], ["攻击", "150"]],
      "subs": [["暴击伤害", "21.0%"], ["攻击", "11.6%"]] }
  ],
  "change": "换6链" }
```

- 没列到的槽位保持该角色当前装备；`from` 引用别人正在装备的那件，自定义件词条照抄原文。
- cost 只能 1/3/4，总和 ≤12；`change` 走换装文本管线（换链/武器/等级/技能/主词条）。
- 只在本地渲染出卡：不写 `players/`、不进总排行上传队列。别把假设数据说成用户真实面板。

## 游戏常识知识库

库洛 wiki 文本（图鉴/攻略/百科/活动/任务/剧情）已在本地，按"条目/小节"粒度存放，
纯文本、图片以 `![名](url)` 内嵌——要展示图片直接把 url 给用户。

```python
w.kb("虚湮效应")                 # 词法检索小节 → [{id,entry,title,tags,score,snippet}]
w.kb("配队", tags=["玩法攻略"])   # 按 tags/source 收窄
w.kb_get("wiki-xxx#2")           # 小节 id → 该小节
w.kb_get("wiki-xxx")             # entry id → 整条(全部小节)
```

先 `kb` 看 snippet 定位到小节，通常小节就够了；要上下文再用 entry id 取整条，别整库摊开。
用户话里首次提到角色名/机制词时，插件会自动附带该条目的首个小节（每会话每条只附一次，
标注"仅供参考"）；那只是字面命中，后续要引用细节自己再 `kb`/`kb_get`。

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
