#!/usr/bin/env python3
"""Build an independent workbench and maintain its two persistent libraries."""
import argparse
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from library import VERSION, atomic_json, initialize
from store import Store

MODULES = ("library.py", "providers.py", "store.py", "jobs.py", "engines.py", "server.py", "workbench.py")


def runtime_files():
    scripts = Path(__file__).resolve().parent
    assets = scripts / "static"
    if not assets.is_dir():
        assets = scripts.parent / "assets"
    return {**{name: scripts/name for name in MODULES}, **{"static/"+name: assets/name for name in ("index.html", "app.js", "styles.css")}}


def data_root(path):
    root = Path(path).expanduser().resolve()
    marker = root / ".workbench.json"
    if marker.exists():
        target = Path(json.loads(marker.read_text(encoding="utf-8"))["data_root"])
        return (root/target).resolve() if not target.is_absolute() else target.resolve()
    if (root/"账号方向.json").exists():
        return root
    raise ValueError("没有找到内容库；首次请先运行 workbench.py init")


def build(root, builder, existing_data=None, upgrade=False):
    project = Path(root).expanduser().resolve()
    if not builder:
        raise ValueError("请明确本次搭建平台 codex 或 workbuddy，不根据安装情况猜测")
    manifest_path = project/".workbench.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    if prior and existing_data and data_root(project) != Path(existing_data).expanduser().resolve():
        raise ValueError("已有工作台的数据路径不能在重开时被替换")
    root_data = data_root(project) if prior else Path(existing_data).expanduser().resolve() if existing_data else project/"data"
    app = project/"app"
    if app.exists() and not prior:
        raise ValueError("已有 app 文件夹，未覆盖；请选择独立工作台目录")
    if prior and not upgrade:
        store = Store(root_data)
        result = {"created": False, "project": str(project), "data": str(root_data), "version": prior["version"], "builder": store.settings()["builder"], "message": "沿用已有工作台和设置，未覆盖程序或数据"}
        store.close()
        return result
    files = runtime_files()
    if any(not f.is_file() for f in files.values()):
        raise ValueError("Skill 程序文件不完整，请重新校验安装包")
    if prior:
        changed = [name for name, digest in prior["files"].items() if not (app/name).is_file() or hashlib.sha256((app/name).read_bytes()).hexdigest() != digest]
        if changed:
            raise ValueError("工作台已有本地改动，未覆盖："+"、".join(changed)+"；请让 AI 定向合并")
        if app.is_dir():
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            shutil.copytree(app, project/"程序备份"/stamp)
    initialize(root_data)
    project.mkdir(parents=True, exist_ok=True)
    for name, source in files.items():
        target = app/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    store = Store(root_data)
    platform_marker = root_data/"搭建平台.json"
    if not platform_marker.exists():
        store.update_settings({"builder": builder})
        platform_marker.write_text(json.dumps({"builder": builder}, ensure_ascii=False), encoding="utf-8")
    store.export()
    actual_builder = store.settings()["builder"]
    store.close()
    try:
        relative_data = root_data.relative_to(project).as_posix()
    except ValueError:
        relative_data = str(root_data)
    atomic_json(manifest_path, {"version": VERSION, "data_root": relative_data, "builder": actual_builder, "files": {name: hashlib.sha256(source.read_bytes()).hexdigest() for name, source in files.items()}})
    guide = project/"启动说明.md"
    if not guide.exists():
        guide.write_text("# 我的内容工作台\n\n用 Codex 或 WorkBuddy 打开这个文件夹，对 AI 说：\n\n> 打开这个工作台，沿用已有两个库和搭建平台，不要重新建库。\n\nAI 可运行 `python3 app/workbench.py run --root . --port 0`，打开返回的本机 URL。停止服务后数据仍在。\n\n左侧是爆款库、选题库、采集批次和设置。采集需先授权 Get笔记，TikHub 凭证在自己的电脑上配置；设置可改关键词和完整选题提示词。\n\nAI 生成沿用搭建平台的本机登录与默认模型，需先测试连接。每条选题只有一句话，分待选和已确认，确认不等于发布。\n\n增加功能时让 AI 在 app/ 内修改，保留数据。备份前停止服务，复制本工作台和外置数据目录（如有）；凭证单独保管，不随库分享。\n", encoding="utf-8")
    ignore = project/".gitignore"
    if not ignore.exists():
        ignore.write_text("data/\n.ai/\n__pycache__/\n*.pyc\n.env*\ncredentials.json\n程序备份/\n", encoding="utf-8")
    return {"created": prior is None, "project": str(project), "data": str(root_data), "builder": actual_builder, "version": VERSION, "next": "python3 app/workbench.py run --root . --port 0"}


def main():
    parser = argparse.ArgumentParser(description="独立内容工作台：搭建、重开和维护两个库")
    parser.add_argument("command", choices=("init", "run", "status", "context", "export", "settings", "configure", "material-add", "topics-import", "topic-update"))
    parser.add_argument("--root", required=True, help="工作台项目文件夹，或已有内容库目录")
    parser.add_argument("--builder", choices=("codex", "workbuddy"))
    parser.add_argument("--data-root", help="沿用已有内容库；不移动或清空它")
    parser.add_argument("--upgrade", action="store_true", help="仅更新未被本地修改的程序；更新前保存程序副本")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--id")
    args = parser.parse_args()
    store = None
    try:
        if args.command == "init":
            result = build(args.root, args.builder, args.data_root, args.upgrade)
        elif args.command == "run":
            from server import serve
            serve(data_root(args.root), args.port, args.builder)
            return
        else:
            store = Store(data_root(args.root))
            if args.command == "status":
                result = {"data": str(store.root), "materials": len(store.all("materials")), "pending": sum(t["decision"] == "pending" for t in store.all("topics")), "confirmed": sum(t["decision"] == "confirmed" for t in store.all("topics")), "batches": len(store.rows("batches")), "builder": store.settings()["builder"], "version": VERSION}
            elif args.command == "context":
                result = store.state()
            elif args.command == "export":
                result = {"output": store.export()}
            else:
                payload = json.load(sys.stdin)
                if args.command == "settings":
                    result = store.update_settings(payload)
                elif args.command == "configure":
                    result = store.configure(payload)
                elif args.command == "material-add":
                    result = store.material(payload, manual=True)
                elif args.command == "topic-update":
                    result = store.decide(args.id, payload)
                else:
                    if not isinstance(payload, list):
                        raise ValueError("请输入一句话选题数组，每条包含 title、references")
                    # Check every row before inserting; references must exist.
                    for t in payload:
                        if not isinstance(t, dict) or not isinstance(t.get("title"), str) or not t["title"].strip() or len(" ".join(t["title"].split())) > 160 or not isinstance(t.get("references"), list) or not t["references"] or any(not store.get("materials", key) for key in t["references"]):
                            raise ValueError("选题需为160字以内的一句话，并引用库中的真实素材ID")
                    added = reused = 0
                    for t in payload:
                        _, created = store.simple_topic(t["title"], t["references"], "conversation")
                        added += int(created)
                        reused += int(not created)
                    result = {"added": added, "reused": reused, "decision": "pending"}
                store.export()
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    main()
