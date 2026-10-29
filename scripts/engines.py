"""Native, locally authenticated model adapters. No copied account tokens."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def resolve(provider):
    if provider == "codex":
        candidates = [os.environ.get("WORKBENCH_CODEX_BIN", "")]
        for app in ("ChatGPT.app", "Codex.app"):
            candidates += ["/Applications/"+app+"/Contents/Resources/codex-cli/bin/codex", "/Applications/"+app+"/Contents/Resources/codex"]
        candidates += [shutil.which("codex") or ""]
        for f in candidates:
            if f and Path(f).is_file() and os.access(f, os.X_OK):
                return [f], {}, "Codex"
        raise ValueError("未找到本机 Codex，请先用 Codex 完成安装和登录")
    if provider == "workbuddy":
        base = Path("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli")
        entry = base / "bin/codebuddy"
        lite = base / "dist/codebuddy-lite-wb.mjs"
        node = shutil.which("node")
        if entry.exists() and lite.exists() and node:
            return [node, str(entry)], {"CODEBUDDY_FORCE_LITE_WB_BUNDLE": "1"}, "WorkBuddy"
        command = shutil.which("workbuddy") or shutil.which("codebuddy")
        if command:
            return [command], {}, "WorkBuddy / CodeBuddy CLI"
        raise ValueError("未找到 WorkBuddy 本机引擎，请在 WorkBuddy 中完成登录并连接；不会自动改用 Codex")
    raise ValueError("请使用搭建时对应的 Codex 或 WorkBuddy")


def availability(provider):
    try:
        command, _, label = resolve(provider)
        return {"installed": True, "provider": provider, "label": label, "message": "已找到本机引擎，点击测试连接后才能确认授权可用"}
    except ValueError as e:
        return {"installed": False, "provider": provider, "message": str(e)}


def safe_error(s):
    s = re.sub(r"\x1b\[[0-9;]*m", "", s)
    s = re.sub(r"(?i)bearer\s+[^\s\"']+|gk_live_[\w-]+|sk-[\w-]{12,}", "[凭证已隐藏]", s)
    s = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization)[\"\s]*[:=][\"\s]*)[^\s\"&,}]+', r'\1[凭证已隐藏]', s)
    lines = [x for x in s.splitlines() if x.strip() and not re.search(r"^\s*(WARN|warning:)", x, re.I)]
    return " ".join(lines[-5:])[:700]


def run(provider, prompt, schema, directory, timeout=180):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    (directory/"prompt.txt").write_text(prompt, encoding="utf-8")
    (directory/"schema.json").write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
    command, extra_env, label = resolve(provider)
    env = dict(os.environ, **extra_env)
    if provider == "codex":
        output = directory/"response.json"
        args = command + ["exec", "--ephemeral", "--json", "--color", "never", "--sandbox", "read-only", "--skip-git-repo-check", "--cd", str(directory), "--output-schema", str(directory/"schema.json"), "--output-last-message", str(output), "-"]
    else:
        args = command + ["--print", "--output-format", "json", "--tools", "", "--json-schema", json.dumps(schema, ensure_ascii=False)]
    try:
        p = subprocess.run(args, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=directory, env=env)
    except subprocess.TimeoutExpired:
        raise ValueError(label+" 生成超时，未自动重试；可查看本次提示词后再决定是否重试")
    (directory/"engine.log").write_text(safe_error(p.stderr), encoding="utf-8")
    if p.returncode:
        message = safe_error(p.stderr or p.stdout)
        raise ValueError(label+" 调用未完成："+(message or "请检查本机登录与可用额度"))
    try:
        if provider == "codex":
            result = json.loads(output.read_text(encoding="utf-8"))
        else:
            try:
                result = json.loads(p.stdout)
            except json.JSONDecodeError:
                # Some packaged CLIs print a diagnostic line before the JSON result.
                messages = []
                for line in p.stdout.splitlines():
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict) and any(k in item for k in ("result", "structured_output", "is_error")):
                            messages.append(item)
                    except json.JSONDecodeError:
                        pass
                if not messages:
                    if re.search(r"login|log in|sign in|auth|登录|授权", p.stdout, re.I):
                        raise ValueError(label+" 尚未完成本机引擎授权，请在自己的 WorkBuddy/官方CLI内登录后重新测试")
                    raise ValueError(label+" 没有返回JSON响应，请检查本机引擎入口与当前版本；本次未写入选题")
                result = messages[-1]
            if result.get("is_error"):
                raise ValueError(label+" 返回错误："+safe_error(str(result.get("result", "请检查登录"))))
            result = result.get("structured_output") or result.get("result") or result
            if isinstance(result, str):
                result = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", result.strip()))
    except (OSError, json.JSONDecodeError):
        raise ValueError(label+" 没有返回可验证的结构化结果，本次未写入选题")
    return result


TOPIC_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"topics": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"title": {"type": "string"}, "references": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "references"]}}}, "required": ["topics"]}
