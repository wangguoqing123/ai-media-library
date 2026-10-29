import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import engines
from jobs import Jobs
from library import original_title, share_url, VERSION
from store import Store, DEFAULT_PROMPT


def serve(root, port=0, builder=None):
    root = Path(root).resolve()
    marker = root/"搭建平台.json"
    if not marker.exists() and builder is None:
        raise ValueError("首次搭建需要明确 --builder codex 或 workbuddy，不按安装情况猜测平台")
    store = Store(root, recover=True)
    if not marker.exists():
        store.update_settings({"builder": builder})
        marker.write_text(json.dumps({"builder": builder}, ensure_ascii=False), encoding="utf-8")
    store.close()
    manager = Jobs(root)
    token = secrets.token_urlsafe(24)
    assets = Path(__file__).parent/"static"
    if not assets.is_dir():
        assets = Path(__file__).resolve().parents[1]/"assets"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):pass

        def reply(self, data, code=200, kind="application/json; charset=utf-8"):
            b = data if isinstance(data, bytes) else data.encode("utf-8") if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers();self.wfile.write(b)

        def host_ok(self):
            return self.headers.get("Host") == "127.0.0.1:"+str(self.server.server_port)

        def do_GET(self):
            if not self.host_ok():return self.reply({"error":"仅供本机使用"},403)
            routes={"/":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","application/javascript; charset=utf-8"),"/styles.css":("styles.css","text/css; charset=utf-8")}
            if self.path in routes:
                file,kind=routes[self.path];s=(assets/file).read_text(encoding="utf-8").replace("__TOKEN__",token);return self.reply(s,kind=kind)
            if self.path=="/api/health":return self.reply({"ok":True,"version":VERSION})
            store=Store(root)
            try:
                if self.path=="/api/state":
                    state=store.state();settings=state["settings"];ai=engines.availability(settings["builder"]);last=store.get("jobs","ai:connection")
                    ai["last_test"]=last if last and last.get("provider")==settings["builder"] else None
                    state.update(ai=ai,default_prompt=DEFAULT_PROMPT)
                    return self.reply(state)
                if self.path.startswith("/api/task/"):
                    task=store.row("tasks",self.path[len('/api/task/'):]);return self.reply(task or {"error":"任务不存在"},200 if task else 404)
                return self.reply({"error":"未找到"},404)
            finally:store.close()

        def do_POST(self):
            origin=self.headers.get("Origin");expected="http://127.0.0.1:"+str(self.server.server_port)
            if not self.host_ok() or origin not in (None,expected) or self.headers.get("X-Workbench-Token")!=token:return self.reply({"error":"请在工作台页面操作"},403)
            if not self.headers.get("Content-Type","").startswith("application/json"):return self.reply({"error":"需要JSON"},415)
            store=None
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=2*1024*1024:raise ValueError("输入为空或过长")
                payload=json.loads(self.rfile.read(length));store=Store(root);settings=store.settings()
                if self.path=="/api/collect/link":
                    text=payload.get("url","");share_url(text)
                    return self.reply({"task_id":manager.submit("link",{"text":text,"settings":settings})},202)
                if self.path=="/api/collect/keywords":
                    queries=payload.get("keywords",settings["keywords"])
                    if not isinstance(queries,list) or not queries or len(queries)>10 or any(not isinstance(x,str) or not x.strip() or len(x)>60 for x in queries):raise ValueError("请填写1—10个关键词")
                    return self.reply({"task_id":manager.submit("keywords",{"keywords":queries,"settings":settings})},202)
                if self.path=="/api/topics/from-material":
                    ids=payload.get("material_ids",[])
                    if not ids or len(ids)>50:raise ValueError("请选择素材")
                    added=reused=0;results=[]
                    if not isinstance(ids,list) or any(not isinstance(key,str) for key in ids):raise ValueError("请选择真实素材")
                    # Validate all inputs before making any changes.
                    if any(not store.get("materials",key) or not original_title(store.get("materials",key)) for key in ids):raise ValueError("所选素材缺少已核实原题，请先补齐资料")
                    for key in ids:
                        m=store.get("materials",key)
                        if not m or not original_title(m):raise ValueError("所选素材缺少已核实原题，请先补齐资料")
                        topic,created=store.simple_topic(original_title(m),[key],"material");results.append(topic["id"]);added+=int(created);reused+=int(not created)
                    store.export_simple_topics();return self.reply({"added":added,"reused":reused,"topic_ids":results})
                if self.path=="/api/topics/update":
                    result=store.decide(payload["id"],payload["patch"]);store.export_simple_topics();return self.reply(result)
                if self.path=="/api/ai/generate":
                    ids=payload.get("material_ids",[])
                    if not isinstance(ids,list) or not 1<=len(ids)<=10:raise ValueError("每次请选择1—10条素材")
                    count=payload.get("count",settings["topic_count"])
                    if type(count)is not int or not 1<=count<=10:raise ValueError("每次生成1—10题")
                    engines.resolve(settings["builder"])
                    for key in ids:
                        m=store.get("materials",key)
                        if not m or not(m.get("source_content") or m.get("description")):raise ValueError("所选素材原文尚未提取，请先完成采集")
                    snapshot={"builder":settings["builder"],"prompt":settings["prompt"],"material_ids":list(dict.fromkeys(ids)),"count":count}
                    return self.reply({"task_id":manager.submit("generate",snapshot)},202)
                if self.path=="/api/ai/test":
                    engines.resolve(settings["builder"])
                    return self.reply({"task_id":manager.submit("connection",{"builder":settings["builder"]})},202)
                if self.path=="/api/settings":return self.reply(store.update_settings(payload))
                if self.path=="/api/account":return self.reply(store.configure({k:v for k,v in payload.items() if k in ('direction','audience','formats')}))
                return self.reply({"error":"未找到"},404)
            except (ValueError,TypeError,KeyError) as e:return self.reply({"error":str(e)},400)
            finally:
                if store:store.close()

    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    print(json.dumps({"url":"http://127.0.0.1:"+str(server.server_port),"version":VERSION,"data":str(root)},ensure_ascii=False),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();manager.pool.shutdown(wait=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--port',type=int,default=0);p.add_argument('--builder',choices=['codex','workbuddy']);a=p.parse_args();serve(a.root,a.port,a.builder)
