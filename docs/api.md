# 内置 HTTP 接口

鸣潮服务默认听 `127.0.0.1:9777`。dsh 网页里经插件反代，前缀是 `/waves-api`（例如 `/waves-api/api/health`）。
命令结果图文里的 `/api/media/...` 也会被改写成 `/waves-api/api/media/...`。

本机直连示例：

```sh
curl -s http://127.0.0.1:9777/api/health
```

dsh 里：

```sh
curl -s http://127.0.0.1:3080/waves-api/api/health
```

## 命令

### `POST /api/chat`

执行一条鸣潮命令，返回摘要和图文段（前端按 `segments` 渲染）。

```json
{
  "command": "ww椿面板",
  "scene": "group",
  "session_id": "dsh",
  "user_id": null,
  "images": [],
  "file_name": null,
  "file_data": null
}
```

| 字段 | 说明 |
|---|---|
| `command` | 必填。可带或不带 `ww` 前缀 |
| `scene` | `group`（默认）或 `direct`。仅少数命令（如获取 ck）需要 `direct` |
| `session_id` | 预留。当前**不会**用来区分 dsh 会话 |
| `user_id` | 省略则用本机使用者（默认 `local`） |
| `images` | 可选。http(s) 链接或 `base64://...`，声骸评分截图用 |
| `file_name` / `file_data` | 可选。随命令附带的文件（base64） |

成功：

```json
{
  "ok": true,
  "summary": "卡片上的文字摘要",
  "matched": ["触发词"],
  "segments": [{"type": "html", "url": "/api/media/xxx.html"}],
  "elapsed": 1.23
}
```

`segments[].type`：`text` / `image` / `html` / `file` / `buttons` / `node`。`url` 以 `/api/` 开头的要按上面的反代规则补前缀。

### `GET /api/commands`

当前已注册触发器列表，以及标了给模型用的命令说明（`ai`）。

### `GET /api/health`

服务是否起来、载了哪些插件、命令条数、前缀。

## 配置

### `GET /api/config`

设置页用的全部分组。敏感项已掩码。

### `POST /api/config`

```json
{ "group": "服务配置", "key": "log_level", "value": "INFO" }
```

`group` 为 `服务配置` 时改服务自身；否则是上游插件配置名（如 `XutheringWavesUID`）。

### `POST /api/config/upload`

页面模板、头像等文件类配置。`data` 是 base64（可带 `data:` 前缀）。目标路径由服务决定，前端改不了。

### `GET /api/config/media`

卡片缩放默认值：`image_portrait_max_percent`、`image_landscape_max_percent`。

## 数据与媒体

### `GET /api/alias/lookup?text=`

在一段话里扫本地别名表，只返回命中，不做指代判断。纯英文缩写不收。

```json
{ "hits": [{ "alias": "长离", "kind": "角色", "name": "长离" }] }
```

### `GET /api/media/{name}`

渲染产物。HTML 带 sandbox CSP。

### `GET /api/status`

各插件状态数字（绑定数等）。不含图标。

### `POST /api/cleanup`

按配置淘汰过期渲染产物。

## 模型读数据

HTTP 只管下命令和出图。跨角色统筹、自己算分，用 `service/tools/wwdata.py`，字段和场景见 `service/ai/AI_DATA.md`。

## 不做的事

公告订阅、定时推送没有接到 dsh 会话：订阅记在假群 `dsh` 上，通知进全局收件箱。本插件已关掉推送总开关、不注册订阅命令、卡片上也不挂通知条。查公告仍可用 `ww公告`。
