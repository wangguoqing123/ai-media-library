#!/usr/bin/env python3
"""Local, persistent material/topic libraries. Python standard library only."""
import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

VERSION = "0.2.0"
KINDS = ("互动贴", "起号视频", "商单类视频")
STATUSES = ("待制作", "制作中", "已发布", "暂缓")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def share_url(text):
    match = re.search(r"https?://[^\s<>\[\]\"，。]+", text)
    if not match:
        raise ValueError("请提供完整的小红书分享链接")
    url = match.group().rstrip(")）")
    host = (urlparse(url).hostname or "").lower()
    allowed = ("xiaohongshu.com", "xhslink.com", "xhslink.cn")
    if not any(host == h or host.endswith("." + h) for h in allowed):
        raise ValueError("只接受小红书或 xhslink 分享链接")
    return url


def source_id(url):
    url = share_url(url)
    match = re.search(r"/(?:explore|discovery/item)/([0-9a-fA-F]{24})(?:[/?#]|$)", url)
    if match:
        return "xhs:" + match.group(1).lower()
    return "url:" + hashlib.sha256(url.split("?")[0].encode()).hexdigest()[:24]


def clean(value):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", str(value)).lower())


def original_title(record):
    """Do not label a generated or legacy title as a source-platform title."""
    verified = record.get("original_title_verified") is True or record.get("title_source") in ("manual", "share_text", "tikhub")
    return record.get("title", "") if verified else ""


class Library:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        marker = self.root / "账号方向.json"
        if not marker.exists() or read_json(marker).get("schema") != "ai-media-library/v1":
            raise ValueError("这里还没有内容库，请先运行 init")
        self.db = sqlite3.connect(self.root / "内容库.sqlite3", timeout=15)
        self.db.execute("PRAGMA journal_mode=WAL")
        for name in ("materials", "topics", "jobs"):
            self.db.execute("CREATE TABLE IF NOT EXISTS " + name + " (id TEXT PRIMARY KEY, doc TEXT NOT NULL)")
        self.db.commit()

    def close(self):
        self.db.close()

    def all(self, table):
        if table not in ("materials", "topics", "jobs"):
            raise ValueError("未知数据区")
        return [json.loads(r[0]) for r in self.db.execute("SELECT doc FROM " + table + " ORDER BY rowid")]

    def get(self, table, key):
        if table not in ("materials", "topics", "jobs"):
            raise ValueError("未知数据区")
        row = self.db.execute("SELECT doc FROM " + table + " WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, table, key, doc):
        if table not in ("materials", "topics", "jobs"):
            raise ValueError("未知数据区")
        self.db.execute("INSERT INTO " + table + " VALUES (?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc",
                        (key, json.dumps(doc, ensure_ascii=False)))
        self.db.commit()

    def config(self):
        return read_json(self.root / "账号方向.json")

    def configure(self, patch):
        allowed = {"account_name", "audience", "direction", "formats", "known_tools", "keywords", "accounts", "min_likes", "max_calls", "tikhub_enabled"}
        if set(patch) - allowed:
            raise ValueError("配置包含不支持的字段；凭证请用专用配置命令保存")
        if "max_calls" in patch and (type(patch["max_calls"]) is not int or not 1 <= patch["max_calls"] <= 50):
            raise ValueError("每次 TikHub 调用上限应为 1—50")
        if "min_likes" in patch and (type(patch["min_likes"]) is not int or patch["min_likes"] < 0):
            raise ValueError("点赞下限应为非负整数")
        if "tikhub_enabled" in patch and type(patch["tikhub_enabled"]) is not bool:
            raise ValueError("TikHub 开关应为布尔值")
        data = self.config()
        data.update(patch)
        atomic_json(self.root / "账号方向.json", data)
        return data

    def services(self):
        return {name: self.get("jobs", "service:" + name) or {"status": "未测试"} for name in ("getnote", "tikhub")}

    def material(self, record, manual=False):
        key = source_id(record.get("url", ""))
        if record.get("note_id"):
            if not re.fullmatch(r"[0-9a-fA-F]{24}", str(record["note_id"])):
                raise ValueError("小红书笔记 ID 无效")
            key = "xhs:" + record["note_id"].lower()
        old = self.get("materials", key) or {}
        doc = dict(old)
        # Preserve human analysis and already captured original content on provider merges.
        protected = {"category", "learning_point", "ai_summary", "content_type", "read_status"}
        for k, v in record.items():
            if k in ("id", "created_at", "updated_at"):
                continue
            if k == "title" and not manual and original_title(old) and old.get("title_source") in ("manual", "share_text"):
                if v and v != old.get("title"):
                    doc["platform_title"] = v
                continue
            if k in ("title_source", "original_title_verified") and not manual and original_title(old) and (not record.get("title") or old.get("title_source") in ("manual", "share_text")):
                continue
            if not manual and (k in protected and old.get(k) or k == "source_content" and old.get(k)):
                continue
            if k == "issues" and isinstance(v, list):
                doc[k] = v
                continue
            if v is not None and v != "" and v != [] and v != {}:
                doc[k] = v
        doc.update(id=key, created_at=old.get("created_at", now()), updated_at=now())
        if manual and record.get("title") and "title_source" not in record:
            doc.update(title_source="manual", original_title_verified=True)
        elif record.get("title_source") == "getnote":
            # Compatibility for older importers; keep their title as a generated label.
            doc["getnote_title"] = record.get("title", "")
            doc["title"] = old.get("title", "") if original_title(old) else ""
            doc["original_title_verified"] = bool(original_title(old))
        doc.setdefault("category", "待分类")
        doc.setdefault("read_status", "未读")
        doc.setdefault("provider", "手动录入")
        doc.setdefault("extraction_status", "待核验" if doc.get("source_content") or doc.get("description") else "待提取")
        if old.get("source_content") and not record.get("source_content") and not manual and "provider_checks" not in record:
            doc["extraction_status"] = old.get("extraction_status", "待核验")
        self.put("materials", key, doc)
        return doc

    def topic(self, record):
        if not record.get("title", "").strip() or not record.get("core_question", "").strip():
            raise ValueError("选题需要题目和具体问题")
        if record.get("kind") not in KINDS:
            raise ValueError("内容类型应为互动贴、起号视频或商单类视频")
        refs = record.get("references", [])
        if not refs or not isinstance(refs, list):
            raise ValueError("选题必须对应至少一条已入库的参考素材")
        for ref in refs:
            material = self.get("materials", ref)
            if not material or not (material.get("source_content") or material.get("description")):
                raise ValueError("选题引用的素材不存在或还没有可读原文")
        key = record.get("id") or "topic:" + hashlib.sha256((record["kind"] + record["title"]).encode()).hexdigest()[:16]
        if self.get("topics", key):
            raise ValueError("选题已经存在，请用 topic-update 更新状态")
        # This is exact/normalized dedupe. Semantic dedupe belongs to the hosting AI.
        signature = (clean(record["core_question"]), clean(record.get("audience", "")), clean(record.get("scene", "")))
        for existing in self.all("topics"):
            other = (clean(existing["core_question"]), clean(existing.get("audience", "")), clean(existing.get("scene", "")))
            if clean(existing["title"]) == clean(record["title"]) or signature == other:
                raise ValueError("题目或具体问题重复，请保留已有选题")
        doc = dict(record, id=key, status="待制作", created_at=now(), updated_at=now())
        self.put("topics", key, doc)
        return doc

    def topic_update(self, key, patch):
        doc = self.get("topics", key)
        if not doc:
            raise ValueError("没有找到该选题")
        allowed = {"status", "published_url", "notes", "materials_needed", "verification_needed"}
        if set(patch) - allowed:
            raise ValueError("只更新状态、发布链接、备注及待补材料，修改选题正文请另作版本")
        if patch.get("status", doc["status"]) not in STATUSES:
            raise ValueError("不支持的制作状态")
        if patch.get("published_url"):
            share_url(patch["published_url"])
        if patch.get("status", doc["status"]) == "已发布" and not patch.get("published_url", doc.get("published_url")):
            raise ValueError("标记已发布时需要真实的作品链接")
        doc.update(patch, updated_at=now())
        self.put("topics", key, doc)
        return doc

    def export(self):
        output = self.root / "导出"
        output.mkdir(exist_ok=True)
        state = {"config": self.config(), "services": self.services(), "materials": self.all("materials"), "topics": self.all("topics")}
        atomic_json(output / "内容库.json", state)
        lines = ["# 爆款素材库", "", "原始内容与 AI 归纳分开保存。互动数据是采集时快照；缺失不等于零。", ""]
        for m in state["materials"]:
            lines += ["## " + (original_title(m) or "原帖标题待补"), "", "- Get笔记生成标题：" + m.get("getnote_title", "无"), "- ID：" + m["id"], "- 分类：" + m.get("category", "待分类"),
                      "- 作者：" + m.get("author", "待核实"), "- 来源：" + m["url"], "- 提取状态：" + m["extraction_status"],
                      "- 工具检查：" + json.dumps(m.get("provider_checks", {}), ensure_ascii=False), "- 指标快照：" + json.dumps(m.get("metrics", {}), ensure_ascii=False), "", "### 原始内容", "",
                      m.get("source_content", m.get("description", "待提取")), "", "### AI 归纳与借鉴点", "",
                      m.get("ai_summary", "未归纳"), m.get("learning_point", ""), ""]
        (output / "爆款素材库.md").write_text("\n".join(lines), encoding="utf-8")
        lines = ["# 选题库", ""]
        for t in state["topics"]:
            lines += ["## " + t["title"], "", "- ID：" + t["id"], "- 类型：" + t["kind"], "- 状态：" + t["status"],
                      "- 具体问题：" + t["core_question"], "- 自己的切入点：" + t.get("angle", "待补"),
                      "- 制作形式：" + t.get("format", "待选择"), "- 参考素材：" + "、".join(t["references"]),
                      "- 待准备材料：" + json.dumps(t.get("materials_needed", []), ensure_ascii=False),
                      "- 待核实：" + json.dumps(t.get("verification_needed", []), ensure_ascii=False),
                      "- 发布链接：" + t.get("published_url", "未发布"), ""]
        (output / "选题库.md").write_text("\n".join(lines), encoding="utf-8")
        return str(output)


def initialize(root):
    root = Path(root).expanduser().resolve()
    marker = root / "账号方向.json"
    if marker.exists():
        lib = Library(root)
        lib.close()
        return {"root": str(root), "created": False}
    if root.exists() and any(root.iterdir()):
        raise ValueError("请选择空文件夹；不会覆盖已有资料")
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(marker, {"schema": "ai-media-library/v1", "version": VERSION, "account_name": "", "audience": "", "direction": "", "formats": [], "known_tools": [], "keywords": [], "accounts": [], "min_likes": 0, "max_calls": 3, "tikhub_enabled": False})
    (root / ".gitignore").write_text("内容库.sqlite3*\n导出/\n凭证.json\n", encoding="utf-8")
    lib = Library(root)
    lib.export()
    lib.close()
    return {"root": str(root), "created": True}


def main():
    from store import Store
    p = argparse.ArgumentParser(description="建立和维护自己的爆款素材库、选题库")
    p.add_argument("command", choices=["init", "status", "context", "export", "configure", "material-add", "topics-import", "topic-update"])
    p.add_argument("--root", required=True)
    p.add_argument("--id")
    args = p.parse_args()
    lib = None
    try:
        if args.command == "init":
            result = initialize(args.root)
        else:
            lib = Store(args.root)
            if args.command == "status":
                result = {"root": str(lib.root), "materials": len(lib.all("materials")), "topics": len(lib.all("topics"))}
            elif args.command == "context":
                result = {"config": lib.config(), "materials": lib.all("materials"), "topics": lib.all("topics")}
            elif args.command == "export":
                result = {"output": lib.export()}
            else:
                data = json.load(sys.stdin)
                if args.command == "configure":
                    result = lib.configure(data)
                elif args.command == "material-add":
                    result = lib.material(data, manual=True)
                elif args.command == "topics-import":
                    if not isinstance(data, list):
                        raise ValueError("选题输入应为 JSON 数组")
                    result = {"added": [], "skipped": []}
                    for t in data:
                        try:
                            result["added"].append(lib.topic(t)["id"])
                        except ValueError as e:
                            result["skipped"].append({"title": t.get("title", ""), "reason": str(e)})
                else:
                    if not args.id:
                        raise ValueError("需要 --id")
                    result = lib.topic_update(args.id, data)
                lib.export()
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, sqlite3.Error) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        if lib:
            lib.close()


if __name__ == "__main__":
    main()
