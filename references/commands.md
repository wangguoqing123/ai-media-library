# 使用命令与验收

替换 SKILL、ROOT 为实际绝对路径。JSON 通过标准输入或工具参数传递，路径含空格保持引号，不把分享文案/密钥拼进 Shell。

## 打开内容库

```bash
python3 "SKILL/scripts/library.py" init --root "ROOT"
python3 "SKILL/scripts/server.py" --root "ROOT" --port 0
```

第二条持续运行，返回本机 URL，打开即可。自动选空闲端口，不干扰其他工作台。停止时在对应终端 Ctrl+C；重开运行第二条。本机地址不是公开分享地址。

## 方向与工具配置

`library.py configure --root "ROOT"` 从标准输入读 JSON。字段：`direction`、`audience`、`account_name`、`formats`、`known_tools`、`keywords`、`accounts`。只填用户确认事实。

`tikhub_enabled`、`max_calls` 同一命令设置，先说明收费并让用户确定范围；密钥不能写这里。工具未配置不阻止手动录入或对已有素材生成选题。

## 添加和修改素材

```bash
python3 "SKILL/scripts/library.py" material-add --root "ROOT"
```

标准输入包含真实 `url`、`title`、`author`、`category`、`source_content`、`learning_point`、`ai_summary`、`read_status`。同一作品合并，不重复添加。`title` 只保存已核实原题；`getnote_title` 是 Get笔记生成标题，不能混用。`source_content` 是提取原文，`description` 是平台正文，`getnote_summary` 是服务摘要，`ai_summary` 是当前 AI 归纳；不因缺项清空已有原文。需要补齐元资料用 collect --metadata，计入预算。

页面“录入参考”支持手动添加，相同链接更新记录；只有链接标待提取，再让 AI 采集。

## 生成选题

```bash
python3 "SKILL/scripts/library.py" context --root "ROOT"
python3 "SKILL/scripts/library.py" topics-import --root "ROOT"
```

context 返回账号方向、完整素材及已有选题。长输出存文件分段读，不用截断片段冒充全文。选题由当前 AI 生成，页面不额外调用其他大模型。topics-import 标准输入为已选选题数组。

## 更新状态

```bash
python3 "SKILL/scripts/library.py" topic-update --root "ROOT" --id "实际选题ID"
```

输入 `{"status":"制作中"}`；实际发布后输入 `{"status":"已发布","published_url":"实际小红书作品链接"}`。页面也能更新；没有链接不能标已发布。

## 导出与作业

```bash
python3 "SKILL/scripts/library.py" export --root "ROOT"
python3 "SKILL/scripts/library.py" status --root "ROOT"
```

数据库为 `内容库.sqlite3`，导出目录有两个库的 Markdown 和 JSON。导出是可重建副本，直接编辑不会回写数据库；修改用页面或 AI 命令。备份时先停止服务再复制整个用户库，不混入凭证。

本关统一提交两个库截图或可查看的资料，及一次“真实素材→自己的选题”示例。验收来源可回看、内容可读、选题有依据、状态能更新、关掉重开仍保存。未配置/未采集/缺少转写/未做测试都明确标注，不新增卡片式作业名称。

工作台分别显示 Get笔记、TikHub 最近实测结果，每条素材也保留分工具结果。接口失败不再借用旧原文显示通过；缺少原题、封面或口播时保留待补状态。
