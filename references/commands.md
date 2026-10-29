# 搭建、重开与维护

SKILL、PROJECT、DATA 均由 AI 换成实际绝对路径，不把占位命令丢给新手。脚本数据通过标准输入传 JSON，不将分享正文或密钥拼进 Shell。

## 从空文件夹搭建

先检查 Python 3.9+；Windows 常用 `py -3`，macOS常用 `python3`。缺少时按官方安装方式帮助配置，再继续。

```bash
python3 "SKILL/scripts/workbench.py" init --root "PROJECT" --builder codex
python3 "PROJECT/app/workbench.py" run --root "PROJECT" --port 0
```

WorkBuddy构建改为 `--builder workbuddy`。第一条会复制完整程序到 app/、建 data/ 两个库、记录搭建平台、生成启动说明，返回实际 DATA；第二条持续运行并返回空闲本机端口，打开这个 URL。不能固定使用作者的50210端口。

只在明确已有库时用 init 的 `--data-root "已有DATA"` 原地接入。已有 app/ 但没有本工作台标记时拒绝覆盖。普通再次 init 沿用程序、数据和平台，忽略本次不同平台参数，不悄悄换模型。

停止在对应终端 Ctrl+C；以后用 AI 打开 PROJECT，说“打开这个工作台，沿用两个库”，运行第二条。既有服务先检查是否可用，避免启动多个进程争用同库。

## AI 维护命令

以下 `--root` 可传 PROJECT 或实际 DATA，所有写入自动导出：

```bash
python3 "SKILL/scripts/workbench.py" status --root "PROJECT"
python3 "SKILL/scripts/workbench.py" context --root "PROJECT"
python3 "SKILL/scripts/workbench.py" configure --root "PROJECT"
python3 "SKILL/scripts/workbench.py" settings --root "PROJECT"
python3 "SKILL/scripts/workbench.py" material-add --root "PROJECT"
python3 "SKILL/scripts/workbench.py" topics-import --root "PROJECT"
python3 "SKILL/scripts/workbench.py" topic-update --root "PROJECT" --id "实际选题ID"
python3 "SKILL/scripts/workbench.py" export --root "PROJECT"
```

- configure 标准输入：已确认的 direction、audience、formats、account_name、known_tools、keywords、accounts；TikHub enabled/max_calls 说明费用后按用户确定的值设置。凭证不用此命令。
- settings 标准输入：keywords、sort_type、time_filter、note_type、min_likes、max_items、max_calls、topic_count、prompt、builder 中需改的字段。设置与采集器的关键词/请求上限保持一致。builder 的更改必须是用户明确换平台。
- material-add 标准输入：真实 url、已核实title、author、category、source_content、ai_summary、learning_point 等。同ID合并，不能用新摘要覆盖原文。
- topics-import 标准输入数组：每条只需 `title` 和 `references`（真实素材ID数组），进入待选。对话生成也遵循完整阅读、去重和真实来源。
- topic-update 标准输入：`{"decision":"confirmed"}` 或 `{"decision":"pending"}`；编辑句子用 `{"title":"实际一句话选题"}`。确认不要求发布链接。

不要再用旧版 library.py 的富字段选题导入流程。context 包含完整素材，长内容保存文件分段读，不截断后声称读全。

## 四个页面怎么用

1. 爆款库：添加链接→等待；关键词采集→按设置执行。页内搜索用于已有素材，关键词采集用于找新作品。看详情可读原始内容、来源和缺失项；可以按批次筛选。
2. 选题库：原题一键加入后可编辑为自己的题目；AI生成先勾选1—10条素材或选批次。每条一句话，分待选/已确认，保留来源。
3. 采集批次：每次采集的关键词/链接、新增、复用、部分、失败和 TikHub请求数；最近任务可看本次完整生成提示词。中断任务不会伪称已完成。
4. 设置：账号方向、观众、搭建平台连接、关键词筛选和完整主提示词；改完点保存。恢复默认先填入草稿，仍需保存生效。

## 保存、升级和扩展

数据库在 DATA/内容库.sqlite3；方向、工作台设置和平台也保存在 DATA。导出/ 下有两个库 Markdown及内容库 JSON，是可重建副本，编辑不会回写数据库。备份先停止服务，再复制项目和可能外置的 DATA；别分享 .ai/任务提示词/日志 或凭证。

升级已生成的工作台用 init --upgrade；先停止服务。仅在已有 app 文件与上次复制时哈希相符时自动升级，并保存程序副本；有本地修改就拒绝覆盖，由 AI 定向合并。两个库不清空。程序升级与更新 Skill 是两件事，不能把已生成实例悄悄换掉。

新增功能从 app/static/app.js 的 PAGES 加导航、实现页面、在 app/server.py 加对应接口；数据模型放 app/store.py。让AI在自己的项目里执行并验证，保留 app/ 与 data/ 分离。

## 交付验收

两个库能打开；一条真实素材能回原帖，原文/摘要边界清楚；一条自己的选题能进待选并确认；批次、设置保存后重开仍在。提交两个库截图或可查看导出，附一次素材到选题示例。没有配置/未测试的工具如实标注；本机URL不能当作远程访问入口。
