import datetime as dt
import hashlib
import json
import uuid
from pathlib import Path

from library import Library, atomic_json, now, clean, original_title

DEFAULT_PROMPT = """你是小红书 AI 自媒体的选题助手。
请完整阅读本次提供的参考素材，结合我的账号方向，扩展我可以制作的选题。

要求：
1. 选题用一句话讲清楚，不写脚本，不输出长分析。
2. 先提炼参考作品的具体问题和吸引点，再换人群、任务、场景、工具领域或结果。
3. 可以借鉴对比、合集、单个技巧、成品展示等模板，不照搬原文，不只换近义词凑数。
4. 起号视频、软件测评／自主样片、互动贴均可；以符合我的账号方向为准。
5. 参考标题里的成绩、效果和省时说法不是我的实测，不编经历、合作或数据。
6. 参考素材缺失的口播、图片文字、功能和价格，不得自行补造为事实。
7. 与已有选题去重。同一具体问题不要拆成几条相似的题目。
8. 每个选题保留对应素材 ID。生成后进入待选区，由我决定是否确认。

账号方向、参考原文、已有选题和生成数量由工作台自动附加。"""

DEFAULT_SETTINGS = {"keywords": [], "sort_type": "最多点赞", "time_filter": "不限", "note_type": "不限", "min_likes": 0, "max_items": 3, "max_calls": 3, "topic_count": 5, "prompt": DEFAULT_PROMPT, "builder": "codex"}


class Store(Library):
    def __init__(self, root, recover=False):
        super().__init__(root)
        for name in ("batches", "tasks"):
            self.db.execute("CREATE TABLE IF NOT EXISTS " + name + " (id TEXT PRIMARY KEY, doc TEXT NOT NULL)")
        self.db.commit()
        self.settings_path = self.root / "工作台设置.json"
        if not self.settings_path.exists():
            config = self.config()
            shared = {k: config[k] for k in ("keywords", "min_likes", "max_calls") if k in config}
            shared["max_calls"] = min(10, shared.get("max_calls", 3))
            atomic_json(self.settings_path, {**DEFAULT_SETTINGS, **shared})
        # Preserve existing content and decisions; assign an explicit imported batch.
        materials = super().all("materials")
        if materials and not self.rows("batches"):
            batch = self.new_batch("历史素材", "import", "从用户已有内容库保留的素材")
            for m in materials:
                self.attach(m["id"], batch["id"])
            batch = self.row("batches", batch["id"])
            batch.update(status="success", finished_at=now(), total=len(materials), added=len(materials), reused=0, failed=0)
            self.save_row("batches", batch)
        for t in super().all("topics"):
            if "decision" not in t:
                t["decision"] = "confirmed"
                self.put("topics", t["id"], t)
        # A previous process cannot continue its background tasks after a restart.
        for t in self.rows("tasks") if recover else []:
            if t.get("status") in ("queued", "running"):
                t.update(status="failed", error="服务已重新启动，请查看已保存结果后再决定是否重试", finished_at=now())
                self.save_row("tasks", t)
                if t.get("batch_id"):
                    batch = self.row("batches", t["batch_id"])
                    if batch and batch.get("status") == "running":
                        batch.update(status="partial", error=t["error"], finished_at=now())
                        self.save_row("batches", batch)

    def row(self, table, key):
        if table not in ("batches", "tasks"):
            raise ValueError("未知数据区")
        r = self.db.execute("SELECT doc FROM " + table + " WHERE id=?", (key,)).fetchone()
        return json.loads(r[0]) if r else None

    def rows(self, table):
        if table not in ("batches", "tasks"):
            raise ValueError("未知数据区")
        return [json.loads(r[0]) for r in self.db.execute("SELECT doc FROM " + table + " ORDER BY rowid DESC")]

    def save_row(self, table, doc):
        if table not in ("batches", "tasks"):
            raise ValueError("未知数据区")
        self.db.execute("INSERT INTO " + table + " VALUES (?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc", (doc["id"], json.dumps(doc, ensure_ascii=False)))
        self.db.commit()
        return doc

    def settings(self):
        return {**DEFAULT_SETTINGS, **json.loads(self.settings_path.read_text(encoding="utf-8"))}

    def update_settings(self, patch):
        if set(patch) - set(DEFAULT_SETTINGS):
            raise ValueError("设置中有未知字段")
        d = self.settings()
        d.update(patch)
        if d["builder"] not in ("codex", "workbuddy"):
            raise ValueError("只能连接搭建所用的 Codex 或 WorkBuddy")
        for key, upper in (("max_items", 10), ("max_calls", 10), ("topic_count", 10)):
            if type(d[key]) is not int or not 1 <= d[key] <= upper:
                raise ValueError("数量需在 1—" + str(upper) + " 之间")
        if type(d["min_likes"]) is not int or d["min_likes"] < 0:
            raise ValueError("点赞下限必须为非负整数")
        if d["sort_type"] not in ("综合", "最新", "最多点赞", "最多评论", "最多收藏") or d["time_filter"] not in ("不限", "一天内", "一周内", "半年内") or d["note_type"] not in ("不限", "视频笔记", "普通笔记"):
            raise ValueError("不支持的筛选条件")
        if not isinstance(d["keywords"], list) or len(d["keywords"]) > 10 or any(not isinstance(x, str) or len(x) > 60 for x in d["keywords"]):
            raise ValueError("最多保存10个关键词，每个60字以内")
        if not isinstance(d["prompt"], str) or not d["prompt"].strip() or len(d["prompt"]) > 16000:
            raise ValueError("提示词不能为空，最多16000字")
        # The UI and collection provider must use the same configured ceiling.
        super().configure({k: d[k] for k in ("keywords", "min_likes", "max_calls")})
        atomic_json(self.settings_path, d)
        return d

    def configure(self, patch):
        if "max_calls" in patch and (type(patch["max_calls"]) is not int or not 1 <= patch["max_calls"] <= 10):
            raise ValueError("工作台每批 TikHub 上限应为 1—10 次")
        result = super().configure(patch)
        shared = {k: patch[k] for k in ("keywords", "min_likes", "max_calls") if k in patch}
        if shared:
            self.update_settings(shared)
        return result

    def new_batch(self, label, mode, query):
        d = {"id": "batch:" + uuid.uuid4().hex[:12], "name": label, "mode": mode, "query": query, "created_at": now(), "status": "running", "total": 0, "added": 0, "reused": 0, "failed": 0, "material_ids": []}
        return self.save_row("batches", d)

    def attach(self, material_id, batch_id):
        m = self.get("materials", material_id)
        if not m:
            return
        m.setdefault("first_batch_id", batch_id)
        m["batch_ids"] = list(dict.fromkeys(m.get("batch_ids", []) + [batch_id]))
        self.put("materials", material_id, m)
        b = self.row("batches", batch_id)
        b["material_ids"] = list(dict.fromkeys(b.get("material_ids", []) + [material_id]))
        self.save_row("batches", b)

    def simple_topic(self, title, references, origin="manual"):
        title = " ".join(str(title).split()).strip()
        if not title or len(title) > 160:
            raise ValueError("选题用一句话，最多160字")
        refs = list(dict.fromkeys(references))
        if not refs or any(not self.get("materials", r) for r in refs):
            raise ValueError("请选择真实参考素材")
        for t in self.all("topics"):
            if clean(t["title"]) == clean(title):
                t["references"] = list(dict.fromkeys(t.get("references", []) + refs))
                self.put("topics", t["id"], t)
                return t, False
        t = {"id": "topic:" + uuid.uuid4().hex[:14], "title": title, "references": refs, "decision": "pending", "origin": origin, "created_at": now(), "updated_at": now()}
        self.put("topics", t["id"], t)
        return t, True

    def decide(self, key, patch):
        t = self.get("topics", key)
        if not t:
            raise ValueError("选题不存在")
        if set(patch) - {"title", "decision"}:
            raise ValueError("只需要一句话选题和确认状态")
        if "decision" in patch and patch["decision"] not in ("pending", "confirmed"):
            raise ValueError("只支持待选或已确认")
        if "title" in patch:
            title = " ".join(str(patch["title"]).split())
            if not title or len(title) > 160:
                raise ValueError("选题需为160字以内的一句话")
            if any(x["id"] != key and clean(x["title"]) == clean(title) for x in self.all("topics")):
                raise ValueError("该选题已存在")
            patch = dict(patch, title=title)
        t.update(patch, updated_at=now())
        self.put("topics", key, t)
        return t

    def state(self):
        return {"materials": self.all("materials"), "topics": self.all("topics"), "batches": self.rows("batches"), "tasks": self.rows("tasks")[:30], "settings": self.settings(), "config": self.config(), "services": self.services()}

    def export_simple_topics(self):
        out = self.root / "导出"
        out.mkdir(exist_ok=True)
        text = "# 选题库\n\n"
        for decision, heading in (("pending", "待选选题"), ("confirmed", "已确认选题")):
            text += "## " + heading + "\n\n"
            text += "\n".join("- " + t["title"] for t in self.all("topics") if t.get("decision", "confirmed") == decision) + "\n\n"
        (out / "选题库.md").write_text(text, encoding="utf-8")

    def export(self):
        out = self.root / "导出"
        out.mkdir(exist_ok=True)
        atomic_json(out / "内容库.json", self.state())
        text = "# 爆款素材库\n\n"
        for m in self.all("materials"):
            text += "## " + (original_title(m) or "原帖标题待补") + "\n\n"
            text += "- 作者：" + m.get("author", "待补") + "\n- 原链接：" + m["url"] + "\n- 采集批次：" + "、".join(m.get("batch_ids", [])) + "\n\n"
            text += "### 原始内容\n\n" + (m.get("source_content") or m.get("description") or "待提取") + "\n\n"
            if m.get("ai_summary"):
                text += "### AI归纳\n\n" + m["ai_summary"] + "\n\n"
        (out/"爆款素材库.md").write_text(text, encoding="utf-8")
        self.export_simple_topics()
        return str(out)
