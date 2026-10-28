#!/usr/bin/env python3
"""Get笔记 first; TikHub metadata fallback/discovery. Never invent ASR."""
import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from library import Library, now, share_url, source_id

CREDS = Path.home() / ".config" / "ai-media-library" / "credentials.json"


class ProviderError(Exception):
    pass


def token():
    value = os.environ.get("TIKHUB_API_TOKEN") or os.environ.get("TIKHUB_API_KEY")
    if value:
        return value
    if CREDS.exists():
        try:
            return json.loads(CREDS.read_text(encoding="utf-8")).get("tikhub", "")
        except (OSError, ValueError):
            return ""
    return ""


def cli_json(args, timeout=45):
    if not shutil.which("getnote"):
        raise ProviderError("getnote_missing：尚未安装 Get笔记 CLI")
    try:
        p = subprocess.run(["getnote"] + args + ["-o", "json"], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ProviderError("getnote_timeout：处理超时；原任务可能仍在运行，不会自动重复创建")
    except OSError:
        raise ProviderError("getnote_unavailable：Get笔记 CLI 无法启动")
    # Error bodies can contain account data or credentials. Do not propagate them.
    if p.returncode:
        raise ProviderError("getnote_failed：请检查登录、会员权限、额度和网络")
    try:
        data = json.loads(p.stdout)
    except ValueError:
        raise ProviderError("getnote_schema：没有收到 JSON 结果，请核对 CLI 版本")
    if isinstance(data, dict) and (data.get("success") is False or data.get("ok") is False):
        raise ProviderError("getnote_failed：服务未返回成功结果")
    return data


def get_note(payload):
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    note = data.get("note", data) if isinstance(data, dict) else {}
    return note if isinstance(note, dict) else {}


def normalize_get(payload, original_url):
    note = get_note(payload)
    web = note.get("web_page") or {}
    if not isinstance(web, dict):
        web = {}
    url = web.get("url") or original_url
    try:
        actual_id = source_id(url)
    except ValueError:
        url, actual_id = original_url, source_id(original_url)
    expected_id = source_id(original_url)
    if expected_id.startswith("xhs:") and actual_id.startswith("xhs:") and expected_id != actual_id:
        raise ProviderError("source_mismatch：返回内容与提交的小红书作品不一致")
    # note.content is the AI summary; it must never replace web_page.content.
    original = web.get("content") or note.get("web_content") or ""
    if not isinstance(original, str):
        original = ""
    image_urls = re.findall(r"!\[[^\]]*\]\((https?://[^\s)]+)\)", original)
    doc = {"url": url, "title": note.get("title", ""), "provider": "getnote", "getnote_id": str(note.get("note_id") or note.get("id") or ""),
           "source_content": original, "image_urls": image_urls, "source_content_kind": "Get笔记提取原文（正文/口播边界待核验）",
           "getnote_summary": note.get("content", ""), "extraction_status": "待核验" if original.strip() else "部分取得",
           "transcript_status": "待核验" if original.strip() else "待补充", "captured_at": now()}
    if actual_id.startswith("xhs:"):
        doc["note_id"] = actual_id[4:]
    return doc


def walk(value):
    queue = [value]
    count = 0
    while queue and count < 10000:
        item = queue.pop(0)
        count += 1
        if isinstance(item, dict):
            yield item
            queue.extend(v for v in item.values() if isinstance(v, (dict, list)))
        elif isinstance(item, list):
            queue.extend(v for v in item if isinstance(v, (dict, list)))


def note_cards(payload):
    found = {}
    for item in walk(payload.get("data", payload)):
        card = item.get("note_card") or item.get("noteCard") or item.get("note") or item
        if not isinstance(card, dict):
            continue
        key = str(card.get("note_id") or card.get("noteId") or card.get("id") or item.get("note_id") or item.get("id") or "")
        if re.fullmatch(r"[0-9a-fA-F]{24}", key) and any(k in card for k in ("title", "display_title", "desc", "description")):
            found[key.lower()] = dict(card, note_id=key.lower())
    return list(found.values())


def count_value(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    m = re.fullmatch(r"([\d.]+)\s*([万千kKwW]?)", str(value).replace(",", "").strip())
    if not m:
        return None
    return round(float(m[1]) * ({"万": 10000, "千": 1000, "k": 1000, "w": 10000}.get(m[2].lower(), 1)))


def first_url(value, fields):
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    for d in walk(value):
        for name in fields:
            v = d.get(name)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                return v
    return ""


def normalize_tik(card, url=None):
    note_id = str(card["note_id"])
    user = card.get("user") or card.get("author") or {}
    info = card.get("interact_info") or card.get("interactInfo") or card
    metrics = {}
    for target, names in {"likes": ("liked_count", "nice_count", "likes"), "saves": ("collected_count", "collect_count", "collects"), "comments": ("comment_count", "comments_count")}.items():
        metrics[target] = next((count_value(info[k]) for k in names if info.get(k) is not None), None)
    images = []
    for image in card.get("image_list", card.get("images_list", [])) or []:
        u = first_url(image, ("url_default", "url", "url_pre", "original"))
        if u:
            images.append(u)
    cover = first_url(card.get("cover", {}), ("url_default", "url", "url_pre")) or (images[0] if images else "")
    video = first_url(card.get("video", {}), ("master_url", "url", "play_url"))
    link = url or card.get("share_url") or ("https://www.xiaohongshu.com/explore/" + note_id)
    if not url and card.get("xsec_token"):
        link = "https://www.xiaohongshu.com/explore/" + note_id + "?" + urlencode({"xsec_token": card["xsec_token"], "xsec_source": "pc_search"})
    return {"url": link, "note_id": note_id, "title": card.get("display_title") or card.get("title") or "",
            "author": user.get("nickname") or user.get("nick_name") or user.get("name") or "",
            "description": card.get("desc") or card.get("description") or "", "cover_url": cover, "image_urls": images,
            "video_url": video, "note_type": card.get("type", ""), "metrics": metrics, "captured_at": now(),
            "provider": "tikhub", "transcript_status": "待补充", "extraction_status": "部分取得"}


class TikHub:
    def __init__(self, config, max_calls=None):
        self.calls = 0
        requested = config.get("max_calls", 5) if max_calls is None else max_calls
        if type(requested) is not int or requested < 0:
            raise ValueError("调用上限应为非负整数")
        self.max_calls = min(config.get("max_calls", 5), requested)
        self.key = token()
        self.enabled = config.get("tikhub_enabled") is True

    def request(self, endpoint, params):
        if not self.enabled:
            raise ProviderError("tikhub_disabled：尚未启用付费调用，请先完成配置")
        if not self.key:
            raise ProviderError("tikhub_missing：尚未配置 TikHub 使用凭证")
        if self.calls >= self.max_calls:
            raise ProviderError("call_limit：已达到本次 TikHub 调用上限")
        self.calls += 1
        request = Request("https://api.tikhub.io/api/v1/xiaohongshu/app_v2/" + endpoint + "?" + urlencode(params), headers={"Authorization": "Bearer " + self.key, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=40) as response:
                payload = json.load(response)
        except HTTPError as e:
            raise ProviderError("tikhub_http_" + str(e.code) + "：请求失败；请检查权限、余额或限流，不自动重试扣费")
        except (URLError, TimeoutError, OSError, ValueError):
            raise ProviderError("tikhub_request_failed：网络或返回格式异常；没有自动重试")
        if not isinstance(payload, dict) or str(payload.get("code", "200")) not in ("0", "200"):
            raise ProviderError("tikhub_business_error：服务返回失败，请在服务商后台核对请求")
        return payload

    def detail(self, url):
        expected = source_id(url)
        payload = self.request("get_image_note_detail", {"share_text": url})
        cards = note_cards(payload)
        matches = [c for c in cards if "xhs:" + c["note_id"] == expected] if expected.startswith("xhs:") else cards
        if len(matches) != 1:
            raise ProviderError("source_ambiguous：未找到唯一匹配的原作品，不会把推荐笔记混入素材")
        doc = normalize_tik(matches[0], url)
        if doc["note_type"] == "video" and self.calls < self.max_calls:
            # Video detail can contain recommendations: match the actual target ID.
            try:
                payload = self.request("get_video_note_detail", {"note_id": doc["note_id"]})
                matches = [c for c in note_cards(payload) if c["note_id"] == doc["note_id"]]
                if len(matches) != 1:
                    raise ProviderError("source_ambiguous：视频结果没有唯一匹配作品")
                newer = normalize_tik(matches[0], url)
                doc.update({k: v for k, v in newer.items() if v not in (None, "", [], {})})
            except ProviderError as e:
                doc["issues"] = [str(e)]
        return doc


def doctor():
    executable = shutil.which("getnote")
    state = {"installed": bool(executable), "authorized_local": False, "remote_status": "未测试"}
    if executable:
        try:
            p = subprocess.run([executable, "auth", "status"], capture_output=True, text=True, timeout=10)
            text = p.stdout + p.stderr
            negative = re.search(r"not authenticated|未登录|未认证", text, re.I)
            state["authorized_local"] = bool(p.returncode == 0 and not negative and re.search(r"Authenticated|已登录|已认证", text, re.I))
        except (OSError, subprocess.TimeoutExpired):
            state["local_status"] = "检查失败"
    return {"getnote": state, "tikhub": {"credential_present": bool(token()), "remote_status": "未测试"}, "note": "本地凭证存在不代表服务可用；请用一条真实链接完成连接测试"}


def collect(lib, url, provider="auto", existing_getnote_id=None, retry=False, max_calls=None):
    url = share_url(url)
    key = source_id(url)
    prior = lib.get("materials", key)
    if prior and prior.get("source_content") and provider == "auto" and not retry and not existing_getnote_id:
        return {"id": prior["id"], "status": "已存在，保留原文", "tikhub_calls": 0}
    job = lib.get("jobs", key) or {}
    issues = []
    record = None
    get_failed = False
    if provider != "tikhub":
        try:
            if existing_getnote_id or job.get("getnote_id"):
                payload = cli_json(["note", str(existing_getnote_id or job["getnote_id"])])
            elif job.get("state") in ("inflight", "uncertain") and not retry:
                raise ProviderError("getnote_uncertain：先前任务尚未确认；请检查 Get笔记，不会重复创建")
            else:
                args = ["save", url]
                try:
                    help_text = subprocess.run(["getnote", "save", "--help"], capture_output=True, text=True, timeout=8).stdout
                    if "--idempotency-key" in help_text:
                        args += ["--idempotency-key", "ai-media-" + hashlib.sha256(key.encode()).hexdigest()]
                except (OSError, subprocess.TimeoutExpired):
                    pass
                lib.put("jobs", key, {"url": url, "state": "inflight", "at": now()})
                payload = cli_json(args, timeout=240)
            note = get_note(payload)
            note_id = note.get("note_id") or note.get("id")
            if note_id:
                lib.put("jobs", key, {"url": url, "state": "saved", "getnote_id": str(note_id), "at": now()})
                if not note.get("web_page"):
                    payload = cli_json(["note", str(note_id)])
            record = normalize_get(payload, url)
            if not record.get("source_content", "").strip():
                issues.append("Get笔记没有返回可读原文；AI 摘要已单独保留")
        except ProviderError as e:
            get_failed = True
            issues.append(str(e))
            if "timeout" in str(e):
                lib.put("jobs", key, {"url": url, "state": "uncertain", "at": now()})
    tik = TikHub(lib.config(), max_calls)
    if provider == "tikhub" or get_failed or not record or not record.get("source_content", "").strip():
        try:
            supplement = tik.detail(url)
            if record:
                record.update({k: v for k, v in supplement.items() if k not in ("provider", "transcript_status", "source_content") and v not in (None, "", [], {})})
                record["provider"] = "getnote+tikhub"
            else:
                record = supplement
        except ProviderError as e:
            issues.append(str(e))
    if not record:
        record = {"url": url, "extraction_status": "提取失败", "provider": provider}
    if issues:
        record["issues"] = record.get("issues", []) + issues
    doc = lib.material(record)
    lib.export()
    return {"id": doc["id"], "status": doc["extraction_status"], "has_original_content": bool(doc.get("source_content")), "tikhub_calls": tik.calls, "issues": issues}


def main():
    p = argparse.ArgumentParser(description="Get笔记优先，TikHub 备用；配置和提取")
    p.add_argument("command", choices=["doctor", "configure-tikhub", "collect", "discover"])
    p.add_argument("--root")
    p.add_argument("--url")
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--provider", choices=["auto", "tikhub"], default="auto")
    p.add_argument("--getnote-id")
    p.add_argument("--retry", action="store_true")
    p.add_argument("--query")
    p.add_argument("--account")
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--max-calls", type=int)
    args = p.parse_args()
    lib = None
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "configure-tikhub":
            if not sys.stdin.isatty():
                raise ValueError("请在自己的终端运行此命令，隐藏输入 TikHub 凭证；不要粘贴到聊天里")
            value = getpass.getpass("请粘贴 TikHub 使用凭证（输入不显示）：").strip()
            if not value or len(value) < 12:
                raise ValueError("没有取得有效的使用凭证")
            CREDS.parent.mkdir(parents=True, exist_ok=True)
            CREDS.parent.chmod(0o700)
            # Open with restrictive permissions from the first byte, not after writing.
            fd = os.open(CREDS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"tikhub": value}, f)
            result = {"saved": True, "remote_status": "未测试", "next": "设置调用上限、启用 TikHub，再用一条真实笔记测试"}
        else:
            if not args.root:
                raise ValueError("需要 --root 指定自己的内容库")
            lib = Library(args.root)
            if args.command == "collect":
                text = sys.stdin.read() if args.stdin else args.url
                if not text:
                    raise ValueError("需要一条小红书分享链接")
                result = collect(lib, text, args.provider, args.getnote_id, args.retry, args.max_calls)
            else:
                if bool(args.query) == bool(args.account):
                    raise ValueError("请提供一个关键词或一个对标主页链接")
                if not 1 <= args.limit <= 20:
                    raise ValueError("首次只处理 1—20 条候选")
                tik = TikHub(lib.config(), args.max_calls)
                if args.query:
                    payload = tik.request("search_notes", {"keyword": args.query, "page": 1, "sort_type": "最多点赞", "note_type": "不限", "time_filter": "不限", "search_id": "", "search_session_id": "", "source": "explore_feed", "ai_mode": 0})
                else:
                    payload = tik.request("get_user_posted_notes", {"share_text": share_url(args.account), "cursor": ""})
                candidates = []
                minimum = lib.config().get("min_likes", 0)
                for card in note_cards(payload):
                    doc = normalize_tik(card)
                    likes = doc["metrics"]["likes"]
                    if minimum and (likes is None or likes < minimum):
                        continue
                    candidates.append(doc)
                    if len(candidates) >= args.limit:
                        break
                result = {"tikhub_calls": tik.calls, "candidates": candidates, "scope": "只查第一页；候选未冒充完整采集，也没有自动入库", "next": "AI 按账号方向筛选，再逐条使用 collect 提取"}
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, ProviderError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        if lib:
            lib.close()


if __name__ == "__main__":
    main()
