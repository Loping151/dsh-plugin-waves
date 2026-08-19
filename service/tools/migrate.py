#!/usr/bin/env python3
"""从既有部署迁入配置、凭据与素材。默认只做缺失项, --force 覆盖。"""

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Optional

DST_DATA = Path(__file__).resolve().parents[1] / "data"

# 配置模型类名去掉了 Gs 前缀, 存量 json 的 type 标签要跟着换
TYPE_MAP = {
    f"Gs{n}Config": f"{n}Config"
    for n in ("Str", "Bool", "Dict", "ListStr", "List", "Int", "Float", "Image",
              "TimeR", "FileUpload", "FilesUpload", "Date", "TimeRange", "Color",
              "RepeatGroup", "Time")
}
TYPE_MAP["GsDivider"] = "Divider"

PLUGINS = ["XutheringWavesUID", "RoverSign", "ScoreEcho"]

SYMLINK_DIRS = ["guide_new", "custom_role_pile", "custom_mr_bg", "custom_orb", "custom_mr_role_pile"]
COPY_DIRS = ["alias", "show", "resource"]
COPY_FILES = ["ann_data.json", "guide_config.json", "gacha_config.json"]

# 订阅表不迁: 那是群聊场景的推送去向, 本地只有一个使用者, 迁过来只会留下外部群号
DB_TABLES = [
    "wavesbind", "wavesuser", "WavesUserSdk", "WavesGachaCloud",
    "WavesLangSettings", "WavesStaminaRecord", "RoverSign", "ScoreEcho",
    "ScoreLangSettings",
]


def _rewrite_paths(item: dict, src_root: Path, dst_root: Path) -> int:
    """配置里存的是绝对路径, 迁过来要落到本地数据目录的同名位置。"""
    changed = 0
    prefix = str(src_root)
    for field in ("data", "upload_to"):
        value = item.get(field)
        if not isinstance(value, str) or not value:
            continue
        if value.startswith(prefix):
            item[field] = str(dst_root) + value[len(prefix) :]
        elif "/XutheringWavesUID/" in value.replace("\\", "/"):
            # 来源部署的目录结构不同时, 按插件目录之后的相对部分归位
            tail = value.replace("\\", "/").split("/XutheringWavesUID/", 1)[1]
            item[field] = str(dst_root / "XutheringWavesUID" / tail)
        else:
            continue
        changed += 1
    return changed


def convert_config(src: Path, dst: Path, force: bool, roots: Optional[tuple] = None) -> None:
    if not src.is_file():
        print(f"跳过 (源缺失): {src}")
        return
    if dst.exists() and not force:
        print(f"跳过 (已存在): {dst}")
        return
    data = json.loads(src.read_text("utf-8"))
    paths = 0
    for item in data.values():
        if not isinstance(item, dict):
            continue
        if item.get("type") in TYPE_MAP:
            item["type"] = TYPE_MAP[item["type"]]
        if roots:
            paths += _rewrite_paths(item, *roots)
    if paths:
        print(f"路径改写: {paths} 处指向本地数据目录")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    secrets = [k for k in ("WavesToken", "LocalProxyUrl", "xwtoken") if k in data]
    print(f"配置: {dst.name} 项数={len(data)} 含凭据={secrets}")


def _prune_users(conn: sqlite3.Connection, masters: list) -> int:
    """只留主人自己的行, 其余用户数据不进本地库。"""
    if not masters:
        return 0
    placeholders = ",".join("?" for _ in masters)
    removed = 0
    for table in ("wavesbind", "wavesuser", "WavesUserSdk", "WavesGachaCloud",
                  "WavesLangSettings", "WavesStaminaRecord", "ScoreEcho",
                  "ScoreLangSettings"):
        try:
            cur = conn.execute(
                f'DELETE FROM "{table}" WHERE user_id IS NOT NULL '
                f"AND user_id NOT IN ({placeholders})",
                masters,
            )
            removed += cur.rowcount or 0
        except sqlite3.OperationalError:
            continue
    conn.commit()
    return removed


def find_source_db(src: Path) -> Optional[Path]:
    """来源库文件名随部署而异, 按是否含绑定表识别。"""
    for path in sorted(src.glob("*.db")):
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        except sqlite3.Error:
            continue
        try:
            names = {
                str(row[0]).lower()
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        except sqlite3.Error:
            names = set()
        finally:
            conn.close()
        if "wavesbind" in names:
            return path
    return None


def snapshot_db(src: Optional[Path], dst: Path, force: bool, masters: list) -> None:
    if src is None or not src.is_file():
        print(f"跳过 (源库缺失): {src}")
        return
    if dst.exists() and not force:
        print(f"跳过 (已存在): {dst}")
        return
    tmp = dst.with_suffix(".snapshot")
    for path in (tmp, Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
        path.unlink(missing_ok=True)
    # 只读 + 快照, 不与在写进程共享连接
    source = sqlite3.connect(f"file:{src}?mode=ro&immutable=1", uri=True)
    target = sqlite3.connect(tmp)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    keep = sqlite3.connect(tmp)
    try:
        existing = {r[0] for r in keep.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        dropped = 0
        for table in existing:
            if table not in DB_TABLES and not table.startswith("sqlite_"):
                keep.execute(f'DROP TABLE IF EXISTS "{table}"')
                dropped += 1
        keep.commit()
        pruned = _prune_users(keep, masters)
        rows = {t: keep.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                for t in DB_TABLES if t in existing}
        keep.execute("VACUUM")
        keep.commit()
        print(f"数据库: 丢弃他人行={pruned}")
    finally:
        keep.close()
    tmp.replace(dst)
    print(f"数据库: {dst.name} 保留表={rows} 丢弃无关表={dropped}")


def rewrite_bot_id(db: Path, bot_id: str = "dsh") -> None:
    """来源库按原平台标识分区, 本地只有一个会话来源, 统一改写。"""
    if not db.is_file():
        return
    conn = sqlite3.connect(db)
    try:
        changed = 0
        for table in DB_TABLES:
            for column in ("bot_id", "bot_self_id", "WS_BOT_ID"):
                try:
                    cur = conn.execute(
                        f'UPDATE "{table}" SET "{column}"=? WHERE "{column}" IS NOT NULL '
                        f'AND "{column}"!=?',
                        (bot_id, bot_id),
                    )
                    changed += cur.rowcount or 0
                except sqlite3.OperationalError:
                    continue
        conn.commit()
        print(f"会话来源: {changed} 处改写为 {bot_id}")
    finally:
        conn.close()


def rewrite_user_id(db: Path, user_id: str) -> None:
    """来源库按聊天平台的用户 id 分区, 本地只有一个使用者, 统一归到它名下。"""
    if not db.is_file() or not user_id:
        return
    conn = sqlite3.connect(db)
    try:
        changed = 0
        for table in DB_TABLES:
            try:
                cur = conn.execute(
                    f'UPDATE "{table}" SET user_id=? WHERE user_id IS NOT NULL AND user_id!=?',
                    (user_id, user_id),
                )
                changed += cur.rowcount or 0
            except sqlite3.OperationalError:
                continue
        conn.commit()
        print(f"归属: {changed} 处改写为 {user_id}")
    finally:
        conn.close()


def bind_group(db: Path, group: str = "dsh") -> None:
    """把绑定记录挂到本地会话所属的组, 群维度的排行才有数据。"""
    if not db.is_file():
        return
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT id, group_id FROM wavesbind").fetchall()
        changed = 0
        for row_id, group_id in rows:
            parts = [g for g in (group_id or "").split("_") if g]
            if group not in parts:
                parts.append(group)
                conn.execute("UPDATE wavesbind SET group_id=? WHERE id=?", ("_".join(parts), row_id))
                changed += 1
        conn.commit()
        print(f"绑定: {changed}/{len(rows)} 行加入 {group}")
    finally:
        conn.close()


def master_uids(db: Path) -> list:
    if not db.is_file():
        return []
    conn = sqlite3.connect(db)
    try:
        uids = set()
        for (cell,) in conn.execute("SELECT uid FROM wavesbind WHERE uid IS NOT NULL"):
            uids.update(u for u in str(cell).split("_") if u)
        for (cell,) in conn.execute("SELECT uid FROM wavesuser WHERE uid IS NOT NULL"):
            if cell:
                uids.add(str(cell))
        return sorted(uids)
    finally:
        conn.close()


def copy_players(src: Path, dst: Path, uids: list, force: bool) -> None:
    if not src.is_dir() or not uids:
        print("跳过 players (无绑定 uid)")
        return
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for uid in uids:
        one_src, one_dst = src / uid, dst / uid
        if not one_src.is_dir():
            continue
        if one_dst.exists():
            if not force:
                continue
            shutil.rmtree(one_dst)
        shutil.copytree(one_src, one_dst, symlinks=True)
        copied += 1
    print(f"玩家数据: {copied}/{len(uids)} 个 uid")


def link_or_copy(src: Path, dst: Path, mode: str, force: bool) -> None:
    if not src.exists():
        print(f"跳过 (源缺失): {src.name}")
        return
    if dst.exists() or dst.is_symlink():
        if not force:
            print(f"跳过 (已存在): {dst.name}")
            return
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "symlink":
        try:
            dst.symlink_to(src)
            print(f"链接: {dst.name} -> {src}")
            return
        except OSError:
            # Windows 未开开发者模式时创建符号链接会失败, 退回复制
            print(f"链接失败, 改为复制: {dst.name}")
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=True)
        print(f"复制: {dst.name}/")
    else:
        shutil.copy2(src, dst)
        print(f"复制: {dst.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, help="来源部署的 data 目录, 不给则跳过迁入")
    parser.add_argument("--src-db", type=Path, help="来源数据库, 默认在 --src 下自动识别")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-players", action="store_true")
    parser.add_argument("--masters", nargs="*", help="要保留的用户 id, 默认取 data/config.json")
    args = parser.parse_args()
    src = args.src
    if src is None:
        print("未指定 --src, 跳过迁入 (全新部署无需迁移)")
        return
    if not src.is_dir():
        sys.exit(f"源数据目录不存在: {src}")

    DST_DATA.mkdir(parents=True, exist_ok=True)

    for plugin in PLUGINS:
        convert_config(
            src / plugin / "config.json",
            DST_DATA / plugin / "config.json",
            args.force,
            (src.resolve(), DST_DATA.resolve()),
        )

    masters = args.masters or json.loads(
        (DST_DATA / "config.json").read_text("utf-8")
    ).get("masters", [])
    snapshot_db(
        args.src_db or find_source_db(src),
        DST_DATA / "WavesData.db",
        args.force,
        masters,
    )
    rewrite_bot_id(DST_DATA / "WavesData.db")
    rewrite_user_id(DST_DATA / "WavesData.db", masters[0] if masters else "local")
    bind_group(DST_DATA / "WavesData.db")

    ww_src, ww_dst = src / "XutheringWavesUID", DST_DATA / "XutheringWavesUID"
    for name in COPY_DIRS:
        link_or_copy(ww_src / name, ww_dst / name, "copy", args.force)
    for name in SYMLINK_DIRS:
        link_or_copy(ww_src / name, ww_dst / name, "symlink", args.force)
    for name in COPY_FILES:
        link_or_copy(ww_src / name, ww_dst / name, "copy", args.force)
    if not args.skip_players:
        copy_players(
            ww_src / "players",
            ww_dst / "players",
            master_uids(DST_DATA / "WavesData.db"),
            args.force,
        )

    print("\n完成。若首次运行, 建议接着执行: .venv/bin/python tools/smoke.py ww查询")


if __name__ == "__main__":
    main()
