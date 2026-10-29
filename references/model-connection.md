# 沿用搭建平台的模型

用什么平台搭建，就连接该平台已有本机引擎和默认模型。记录在 DATA/工作台设置.json；首次由 --builder 写入，之后重开保留。设置允许用户明确切换平台并重新测试，但不能因某平台未登录就偷偷切换。

这会另起一次非交互模型请求，不是把当前聊天窗口内容搬走，也不承诺复用当前聊天的临时模型覆盖。调用沿用平台本机授权与默认模型/额度，不要求另填一把模型API密钥。不要读出或复制登录 Token，不修改全局模型配置。

## Codex

先点设置中的“测试连接”。适配器优先找已安装桌面应用附带的 Codex CLI，其次 PATH 中 codex。必要时可用 WORKBENCH_CODEX_BIN 指向用户自己的可执行文件，不写死作者路径。

实际通过 codex exec 非交互调用，提示词走 stdin，--output-schema 校验JSON，--output-last-message 保存结果；使用 --ephemeral、--sandbox read-only，不使用跳过审批或沙箱的危险选项。先检查当前CLI的 --help，有版本差异就按官方说明处理。

未找到CLI：帮助安装或找到桌面版自带命令；未授权：引导在自己终端/客户端登录；额度或网络错误：展示真实原因，等待本人处理后再测，不自动重试。

官方依据：[Codex非交互命令](https://learn.chatgpt.com/docs/developer-commands#codex-exec)。

## WorkBuddy

优先使用已安装 WorkBuddy 桌面应用内置的引擎；macOS打包版可能需要 Node及其 lite bundle 入口（适配器已处理）。其次检查本机 workbuddy/codebuddy CLI，但需确认是用户用于 WorkBuddy 的授权环境，不能把另一套陌生账号当成已连通。

调用 --print --output-format json --json-schema，--tools 空串禁用工具。需要同时检查 installed 和真实响应结果；只找到应用或显示帮助不算模型测试通过。登录错误由用户在自己的 WorkBuddy/官方CLI内完成，不从应用缓存提取Token。

WorkBuddy版本/系统可能不同；当前安装若没有可调用入口，AI按本机 help 和 [官方无头模式](https://www.workbuddy.ai/docs/cli/headless) 定向适配并实测，不能改用另家模型或固定题目交差。Windows设备需各自验证。

## 结果与资料边界

连接测试只请求一个JSON响应；生成用所选素材，校验句子长度、数量、真实来源。失败保存任务和错误，不写假完成。主提示词在设置可改；本次完整提示词在采集批次的最近任务可看。DATA/.ai/ 是个人任务记录，不包含到可分享Skill。
