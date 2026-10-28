# 小红书爆款素材+选题工作台搭建

让 AI 带你配置 Get笔记和 TikHub，在自己的电脑上搭建爆款素材库和选题库，再用它们持续创作小红书内容。

**版本：v0.1.2** · Skill 标识：`ai-media-library`

## 安装

### Codex

把下面这段话复制给 Codex：

```text
请从 https://github.com/wangguoqing123/ai-media-library 安装「小红书爆款素材+选题工作台搭建」Skill。
Skill 在仓库根目录，标识为 ai-media-library。保留其他已有 Skill。
安装后告诉我如何开始使用；如果已经安装，先核对版本和本地改动，再处理更新。
```

也可以下载 [通用安装包](https://github.com/wangguoqing123/ai-media-library/raw/v0.1.2/dist/ai-media-library-bundle.zip)，解压后让 AI 先执行 `python3 install.py --check`，通过后执行 `python3 install.py`。默认安装到当前用户的 Codex skills 目录，已有同名目录不会覆盖。下次会话即可识别，未识别时重新打开会话。

### WorkBuddy

下载 [WorkBuddy 安装包](https://github.com/wangguoqing123/ai-media-library/raw/v0.1.2/dist/ai-media-library-workbuddy.zip)，在 WorkBuddy 的技能管理中导入 ZIP。安装后调用本 Skill；未识别时重启 WorkBuddy。

## 开始搭建

在电脑上新建一个自己的空文件夹，用 Codex 或 WorkBuddy 打开，对 AI 说：

```text
使用「小红书爆款素材+选题工作台搭建」，在当前文件夹搭建我自己的爆款素材库和选题库。
先读取我已确认的账号方向；没有的信息再逐步问我，不要编造。
带我检查和配置 Get笔记、TikHub。默认 Get笔记提取，TikHub 备用。
不要让我把凭证发到聊天里。先用一条真实作品跑通，再扩展选题、让我选择后入库。
最后打开工作台，教我关闭后如何再打开。
```

本机需要 Python 3.9+。没有 Python、Node/npm 或 Get笔记 CLI 时，AI 会按系统指导安装。安装 Skill 不代表外部服务已经授权，仍需要使用自己的账号配置并完成实际测试。

## 配置两个工具

**Get笔记：默认提取原文。** AI 先检查现有安装和登录状态。缺少时按 [官方说明](https://github.com/iswalle/getnote-cli) 安装：

```bash
npm install -g @getnote/cli
getnote auth login
```

在浏览器完成本人账号授权，已有有效授权直接沿用。官方 OpenAPI 需要会员权限；由用户自行决定开通。登录后还要用一条真实小红书链接测试，不能只凭登录成功判断内容可提取。

**TikHub：备用资料提取，也负责按关键词或对标账号发现新作品。** 到 [TikHub 官网](https://tikhub.io/) 登录，查看当前价格、余额和 API 凭证。请 AI 找到安装后的本 Skill 路径，给你一条可直接执行的本地配置命令。在自己的终端隐藏输入凭证，不能贴到聊天：

```bash
python3 scripts/providers.py configure-tikhub
```

这条相对命令在 Skill 目录里运行；AI 应替新手换成实际绝对路径。随后确定每次调用上限，再启用并测试备用。TikHub 按请求计费；默认一次请求取得正文和元资料，需要视频地址时用 --video-url，才额外请求。详细指导在 [配置教程](references/setup-and-collection.md)。

## 平时怎么用

- “收集这几个作品链接，保留原文和来源，按模板分类。”
- “看看这个对标账号最近有哪些值得参考的内容，先查第一页。”
- “完整阅读新素材，给我扩展几个适合自己账号的选题，我选好再入库。”
- “这个选题开始制作了，更新为制作中。”
- “这条已经发布，补上作品链接。”
- “打开我的工作台。”

工作台分别显示 Get笔记和 TikHub 的最近实测状态，失败不会借用旧原文显示通过。支持查看原始内容与 AI 归纳、分类搜索、选题依据和准备材料、更新制作进度，数据保存在自己的文件夹里。采集和选题分析由当前 AI 助手执行，页面不会自行调用另一个大模型，也不会自动发布。

## 提取范围和真实状态

- Get笔记原文、服务摘要和 AI 归纳分开保存；原帖标题与 Get生成标题也分开。只有链接时，在已配置的 TikHub 预算内补齐原题；没拿到则显示待补。同一作品按 ID 去重。
- TikHub 能取得笔记正文、封面/图片、互动数据和视频地址等，但不提供口播转写。口播稿、图片文字缺失时明确标待补，不用正文冒充。
- 关键词/账号发现目前只查第一页；不宣称覆盖全部历史作品。付费调用受用户设置的上限约束。
- 22项回归检查通过；Get笔记1.8.2真实链接采集、TikHub独立提取、Get不可用后的真实备用切换和关键词发现均已实测通过。初次注册扫码授权借用现有账号，Windows与WorkBuddy实际设备仍需各自验证。
- 安装包不包含作者凭证、登录状态、私有工作台或演示数据库。

## 目录

`SKILL.md` 是入口；`references/` 是配置、操作、选题规则和课程真实案例；`scripts/` 提供建库、提取和本机页面；`assets/` 是页面模板；`dist/` 提供安装包和 SHA-256。

[安装与使用说明](dist/安装与使用说明.md) · [详细命令](references/commands.md)
