# 工具配置与收集

替换 SKILL、ROOT 为实际绝对路径。Python 3.9+，不需要购买数据库或配置新的 AI API；语言分析由当前 AI 助手完成。

## 检查

```bash
python3 "SKILL/scripts/providers.py" doctor
```

只显示是否安装、有无本地授权/凭证，不输出密钥；这不等于远端连接成功。两个服务分开记录，不跨项目搜其他人的私密配置。

## Get笔记：默认提取

先检查 `getnote --version`、`getnote save --help`。缺少 CLI 时安装；没有 Node/npm 时按用户系统指导安装 Node.js LTS，也可使用官方独立二进制。不要将旧版不支持的命令当作必有能力。

```bash
npm install -g @getnote/cli
getnote auth login
```

优先官方浏览器授权，用户登录自己的账号，不把密钥贴到聊天。已有授权直接沿用，不退出或清空配置；不自动升级已安装 CLI，能力不足时解释再按用户选择处理。

官方说明 OpenAPI 需要会员权限。登录不等于有接口权限；会员、额度、授权错误要解释和指导处理，不代付款。新版可用 `getnote doctor -o json`，旧版用已有命令，最终均需实际链接测试。

```bash
python3 "SKILL/scripts/providers.py" collect --root "ROOT" --stdin
```

通过标准输入传完整分享文案或 URL，不拼到 Shell。此操作创建 Get笔记链接笔记。只读复用已有条目时附 `--getnote-id "实际笔记ID"`，核对原链接一致。脚本将原始内容与 AI 摘要分开保存。

保存是异步的，最多等待240秒；超时可能仍在服务端处理，不自动重复创建。先检查任务/条目，已有结果以 note ID 回读。`--retry` 仅在核对先前状态后，按用户重试要求使用。

安装/会员/授权依据：[getnote-cli 官方仓库](https://github.com/iswalle/getnote-cli)。以已安装版本 help 与当前官方文档为准。核对：2026-10-28。

## TikHub：备用，也负责发现链接

用普通话解释：这是按请求计费的外部数据服务，可以取得笔记资料及媒体地址，不是口播转写。公开播放量不可用，缺失指标记未知，不补零。

1. 到 [TikHub 官网](https://tikhub.io/) 注册登录，查看用户后台的当前价格、余额和 API 凭证。用户自行决定充值并操作。
2. 在用户自己的终端运行以下命令，隐藏输入凭证，不发到聊天：

```bash
python3 "SKILL/scripts/providers.py" configure-tikhub
```

保存到当前用户 `~/.config/ai-media-library/credentials.json`，Unix权限600；也兼容已有 `TIKHUB_API_TOKEN` / `TIKHUB_API_KEY` 环境变量。Windows还需核对用户目录 ACL，不能声称等同于 Unix600。值不能进入命令参数、公开配置或安装包。

3. 与用户确定本轮最多调用几次。首次建议3次，但不是固定规则。用 library configure 写入 `max_calls` 与 `tikhub_enabled: true` 后启用。后续按已确认范围执行，不逐条询问；未启用不调用。
4. 单独验证备用：

```bash
python3 "SKILL/scripts/providers.py" collect --root "ROOT" --provider tikhub --url "实际作品链接"
```

视频可能需要图文详情、视频详情两次请求。返回的推荐作品必须过滤，只取目标 ID 一致的原作品。检查正文、封面/图片、指标、视频地址后才记录备用可用。

依据：[图文详情](https://docs.tikhub.io/420136391e0)、[视频详情](https://docs.tikhub.io/420136392e0)、[计费与限制](https://tikhub.io/zh/faq)。错误 ID 也可能计费，不自动无限重试。核对：2026-10-28。

## 日常收集

贴链接：collect 默认 Get优先，失败或没有原始内容才用已配置 TikHub。成功部分保留；原文已有时去重。批量分享先拆独立链接，AI 累计每次输出 `tikhub_calls`，把本轮剩余额度传给 `--max-calls`；剩余0时停止收费采集，不让逐条调用重置预算。

关键词/对标：沿用已确认的关键词与真实主页。首次一个关键词或账号、第一页、最多3条；只给昵称时先消歧，不认领同名号。

```bash
python3 "SKILL/scripts/providers.py" discover --root "ROOT" --query "AI作图" --limit 3
python3 "SKILL/scripts/providers.py" discover --root "ROOT" --account "实际主页链接" --limit 3
```

发现只返回候选，未自动入库。AI按方向筛选，保留项逐条交 collect。本版只发现第一页；用户要求全量时明确未覆盖，不宣称全部同步，可继续处理用户提供的下一批链接。

入库后完整读每条原文、分清正文/图片文字/口播是否完整，写模板分类、借鉴点和 AI 归纳。通过 material-add 更新 `category`、`learning_point`、`ai_summary`；读完原文才标 `read_status: 已读`，只读摘要不能标。七类视频模板仅供参考，互动贴另列，新的模板可以增加。不得以补齐为名编写原文或指标。
