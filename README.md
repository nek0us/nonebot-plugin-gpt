<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/NoneBotPlugin.svg" width="240" alt="NoneBotPluginText"></p>
</div>

> 智能体功能的配置、权限与受管服务示例见 [docs/agent.md](docs/agent.md)。

<div align="center">

# nonebot-plugin-gpt


_✨ NoneBot GPT ✨_


<a href="./LICENSE">
    <img src="https://img.shields.io/github/license/nek0us/nonebot-plugin-gpt.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-gpt">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-gpt.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">

</div>



## 📖 介绍

基于浏览器 ChatGPT 会话的 NoneBot2 插件。聊天和管理命令使用 Alconna 与 UniMessage，支持接入不同适配器，并提供逻辑会话、人设、授权、富文本和受控智能体能力。

| 能力 | 说明 |
| --- | --- |
| 跨平台聊天 | 使用 NoneBot 统一事件和 UniMessage，不依赖 OneBot 专属消息类型。 |
| 逻辑会话 | 群聊/频道共享会话，私聊独立；支持初始化、重置、回退、历史与切换。 |
| 人设与上下文 | 支持公开/私有人设、自动初始化、会话内人设强化与上下文摘要迁移。 |
| 富文本输出 | 根据内容和适配器能力输出文本或 Markdown 图片，支持自定义聊天图片模板。 |
| 授权管理 | 支持会话/个人白名单、一次性 CDK、黑名单、Plus 权限、账户状态与本机控制台。 |


### 使用条件

需要能正常访问 ChatGPT 的网络环境。首次登录、Cloudflare 验证、邮箱验证码和浏览器启动故障建议在带桌面的环境中排查；多账号常驻会增加内存占用。

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-gpt

</details>

<details>
<summary>使用包管理器安装</summary>
在 NoneBot2 项目根目录打开命令行，根据使用的包管理器执行其一：

<details>
<summary>pip</summary>

    pip install nonebot-plugin-gpt
</details>
<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-gpt
</details>
<details>
<summary>uv</summary>

    uv add nonebot-plugin-gpt
</details>
<details>
<summary>poetry</summary>

    poetry add nonebot-plugin-gpt
</details>
打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_gpt"]

</details>

<details open>
<summary>升级插件版本</summary>

    pip install nonebot-plugin-gpt -U

    pdm update nonebot-plugin-gpt

    uv lock --upgrade-package nonebot-plugin-gpt
    uv sync

</details>

## ⚙️ 配置

在 NoneBot2 项目的 `.env` 文件中添加下列配置。列表和对象建议使用 JSON，并把整个值包在单引号中。

| 配置项 | 必填 | 默认值 | 类型 | 说明 |
|:-----:|:----:|:----:|:----:|:----:|
| gpt_session | 是 | 无 | JSON List[Dict] | ChatGPT 账号列表；`email`、`password` 必填，`mode` 可为 `openai`（默认）、`microsoft`、`google`。请使用 JSON。 |
| gpt_proxy | 否 | 无 | str | 提供给核心浏览器运行时的代理地址，例如 `http://127.0.0.1:7890`；用于访问 ChatGPT，不影响 NoneBot 的其他网络请求。 |
| gpt_group_chat | 否 | true | bool | 群聊/频道向模型附加固定 `[群聊发言者]` 标签，包含稳定身份与可用显示名，帮助模型区分成员。 |
| gpt_chat_start | 否 | [] | list | 机器人文字称呼/聊天前缀；普通聊天与插件命令均需 @ 机器人或以此、`NICKNAME` 中的名称开头，避免群聊误触发 |
| gpt_chat_start_in_msg | 否 | false | bool | 是否把 `gpt_chat_start` 路由前缀原样交给模型；false 时会移除纯路由前缀，但 `NICKNAME` 的自然称呼会保留原句主语 |
| gpt_empty_trigger_prompt | 否 | 有人在呼唤你…… | str | 仅提及机器人或只发送聊天前缀时交给模型的角色化提示 |
| gpt_direct_address_context_enabled | 否 | false | bool | 是否额外向模型解释“用户正在直接称呼机器人”；默认关闭，保留如“bot今天吃什么”的原始主语，减少内部提示干扰 |
| gpt_direct_address_context_prompt | 否 | 见配置默认值 | str | 开启上述开关后附加的称呼语境提示；仅供模型理解，不会发送给用户 |
| gpt_begin_sleep_time | 否 | false | bool | 启动登录时随机错开账号，减少多账号同时登录；账号少时通常关闭。 |
| gpt_chat_priority | 否 | 90 | int | 普通聊天匹配器优先级。只有与其他插件抢占消息时才需要调整，数值越小越先执行。 |
| gpt_command_priority | 否 | 19 | int | 插件命令匹配器优先级。通常保持比聊天优先，以便“重置”等命令不会被当作普通对话。 |
| gpt_white_list_mode | 否 | true | bool | `true` 时普通聊天要求会话白名单或个人白名单；管理权限、CDK 兑换仍有独立规则。 |
| gpt_plus_white_list_mode | 否 | true | bool | `true` 时高级模型切换需要 Plus 授权；关闭后是否有高级账户仍由上游账户能力决定。 |
| gpt_replay_to_replay | 否 | false | bool | 是否将“回复机器人上一条消息”的事件视为聊天触发。开启会增加群聊中的触发机会。 |
| gpt_ban_str | 否 | `[]` | JSON List[str] | 屏蔽词列表；命中后消息不会交给模型。不要把它当作完整内容安全系统。 |
| gpt_manage_ids | 否 | `[]` | JSON List[str] | 额外管理会话的稳定访问范围标识。管理员在目标会话使用“会话标识”取得该值后配置。 |
| gpt_save_screen| 否 | false | bool | 保存额外的登录、刷新、渲染失败截图。截图可能含账号或聊天内容，以便debug。 |
| gpt_headless| 否 | true | bool | 是否无头运行 Firefox。以便debug。 |
| gpt_local_js| 否 | false | bool | `false` 使用联网兼容脚本，便于跟随网页更新；`true` 使用本地缓存，适合网络排障但可能过期。 |
| gpt_control_host | 否 | 127.0.0.1 | str | 核心账户控制台监听地址。 |
| gpt_control_port | 否 | 无 | int | 控制台端口；留空不开启。设置为 `8765` 时从本机访问 `http://127.0.0.1:8765`。 |
| gpt_control_api_key | 否 | 自动生成 | str | 控制台 API 密钥。 |
| gpt_free_image| 否 | false | bool | 允许免费账户上传图片；额度较低且受上游限制，默认关闭。 |
| gpt_file_upload | 否 | false | bool | 允许上传跨平台消息中的普通文件、音频、语音和视频；默认关闭，开启后会下载适配器提供的 URL 或读取原始附件内容。 |
| gpt_file_max_size | 否 | 20971520 | int | 单个普通附件的最大字节数，默认 20 MiB，范围为 1 KiB 至 100 MiB；超限附件不会下载或上传。 |
| gpt_force_upgrade_model| 否 | true | bool | 避免已保存逻辑会话继续选择不适合免费账户的旧模型偏好。 |
| gpt_render_mode | 否 | auto | auto/text/image | 富文本输出全局默认策略：`auto` 按内容和适配器能力选择，`text` 始终文本，`image` 优先图片；可用“输出模式”在当前聊天范围单独覆盖，`默认`恢复此配置；渲染异常会回退文本。 |
| gpt_chat_image_template | 否 | native | native/off/路径 | 聊天 Markdown 转图样式。`native` 是粉蓝紫纵向主题，`off` 是黑白纵向主题；也可填写含 `{{ content }}` 的自定义 HTML 模板路径。 |
| gpt_image_font_scale | 否 | 1.0 | 0.85-1.25 | 内置聊天图片、历史聊天、帮助和列表图片的阅读字号缩放。默认 `1.0` 已按手机竖屏优化；`1.1` 适合偏好稍大字体的场景，`0.9` 可在信息密集时略微缩小。自定义聊天 HTML 模板需自行控制字体，不受此项影响。 |
| gpt_history_anonymize | 否 | false | bool | 历史聊天是否隐藏群聊发言者昵称；默认 false，历史图片会显示当时记录的昵称，开启后统一显示为“用户”。 |
| gpt_management_recall_after | 否 | 0 | int | 多页帮助、列表、历史等管理输出的自动撤回秒数；`0` 关闭，适配器不支持撤回时自动忽略。 |
| gpt_context_compaction_mode | 否 | summarize_restart | off/reinforce/summarize_restart | 接近上下文上限时：关闭、仅补发人设、或摘要后迁移到新逻辑会话。 |
| gpt_context_compaction_threshold | 否 | 0.6 | 0.1-0.95 | 估算上下文达到模型上限比例时触发维护。 |
| gpt_context_compaction_min_tokens | 否 | 0 | int | 估算 token 未达到此值不触发维护；0 表示只看比例。 |
| gpt_error_message | 否 | 抱歉，这次没能顺利回应。请稍后再试；若持续发生，请联系机器人管理员。 | str | 聊天请求失败时发送的中性提示，可按机器人身份自定义 |
| gpt_conversation_recovery_message | 否 | 当前对话已无法继续，请重新初始化人设后再试。 | str | 原会话绑定的账号已移除或停用时发送的提示，不暴露账号状态，可按机器人身份自定义 |
| gpt_auto_init_group | 否 | false | bool | 群聊或频道首次有效聊天时自动加载群聊默认人设；不会覆盖已有逻辑会话。 |
| gpt_auto_init_friend | 否 | false | bool | 私聊首次有效聊天时自动加载私聊默认人设；不会覆盖已有逻辑会话。 |
| gpt_init_group_persona_name | 否 | 空 | str | 群聊自动初始化使用的人设名称。配置不存在的人设会跳过自动初始化并创建普通会话。 |
| gpt_init_friend_persona_name | 否 | 空 | str | 私聊自动初始化使用的人设名称，行为同上。 |
| gpt_agent_enabled | 否 | false | bool | 启用受控智能体入口。入口仍只允许 `SUPERUSERS`，`gpt_manage_ids` 不会获得智能体权限。 |
| gpt_agent_confirm_timeout | 否 | 60 | 10-3600 | 单次待确认操作的有效秒数；超时后需要重新计划或重新执行。 |
| gpt_agent_session_approval_timeout | 否 | 1800 | 60-86400 | 仅“本机只读”临时授权的有效秒数；写入、网络和进程控制始终逐次确认。 |
| gpt_agent_plan_timeout | 否 | 300 | 30-3600 | 模型返回并经插件校验的计划有效秒数；仅原超级用户可在原聊天范围执行一次。 |
| gpt_agent_workspace | 否 | 空 | Path | 智能体文件工具的受限工作目录；只允许其中的相对路径，拒绝绝对路径和 `..` 越界。 |
| gpt_agent_managed_services | 否 | `[]` | JSON List[Dict] | 管理员预先声明的 `pid_file` 或 `tcp` 服务；模型不能传入任意进程、端口或 shell 命令。 |

> `gpt_init_group_pernal_name` 与 `gpt_init_friend_pernal_name` 是历史拼写，仅保留兼容读取；新配置请使用带 `persona` 的字段。`begin_sleep_time`、`gpt_lgr_markdown`、`gpt_httpx`、`gpt_url_replace` 已废弃，分别迁移为 `gpt_begin_sleep_time`、`gpt_render_mode`，或直接删除。

```env
# 账号列表请使用 JSON；session_token 只能辅助短期恢复，不能替代长期重新登录。
# Microsoft 账户可按需配置 help_email；gptplus 只表示优先候选，已弃用，实际能力以账户探测结果为准。mode目前不支持苹果账号
gpt_session='[
    {
        "email": "xxxx@hotmail.com",
        "password": "xxxx"
    },
    {
        "email": "aaaa@gmail.com",
        "password": "xxxx",
        "mode": "google"
    },
    {
        "email": "bbb@outlook.com",
        "password": "xxxx",
        "mode": "microsoft",
        "help_email": "xxx@xx.com"
    },
]'


gpt_proxy='http://127.0.0.1:8080'
# gpt_proxy='http://username:password@127.0.0.1:8080'

gpt_group_chat=true

gpt_chat_start=[]

gpt_chat_start_in_msg=false

# NICKNAME 是机器人称呼列表；插件通过 Alconna 的跨平台原始消息抽象保留称呼语境
# 仅 @机器人或只发送聊天前缀时，交给模型生成符合人设的自然回应
gpt_empty_trigger_prompt="有人在呼唤你。请以当前人设自然回应。"

gpt_begin_sleep_time=true

gpt_chat_priority=90

gpt_command_priority=19

gpt_white_list_mode=true

gpt_replay_to_replay=false

gpt_ban_str='[
    "我是猪",
    "你是猪",
]'
# 管理访问范围标识，可在目标会话执行“会话标识”获取
gpt_manage_ids='["adapter:bot:session"]'
# 发送消息异常和刷新cookie异常截图保存（登录失败截图固定开启，截图保存在bot目录screen下）
gpt_save_screen=false

# 使用无头浏览器
gpt_headless=true

# 使用本地js
gpt_local_js=false

# 核心账户控制台，默认关闭；仅建议监听本机地址
gpt_control_host=127.0.0.1
gpt_control_port=8765
gpt_control_api_key='replace-with-a-long-random-secret'

# 开启免费账户图片识别（大概每天5额度）
gpt_free_image=false

# 上传文件、音频和视频给当前 ChatGPT 会话；默认关闭以避免自动下载大文件
gpt_file_upload=false
# 单个普通附件最大 20 MiB
gpt_file_max_size=20971520

# 强制升级基础模型，如4o-mini升级到4-1-mini
gpt_force_upgrade_model=true

# 富文本输出策略：auto、text、image
gpt_render_mode="auto"

# 聊天 Markdown 转图主题：
# native：默认粉蓝紫纵向卡片；off：黑白纵向阅读样式（也兼容“关”）；
# 也可填自定义 HTML 模板的绝对路径。模板必须包含 {{ content }} 占位符。
# 可复制 nonebot_plugin_gpt/templates/chat-image-template.html 后自行修改。
gpt_chat_image_template="native"

# 图片阅读字号缩放：默认值适合手机竖屏；可在 0.85-1.25 之间微调
# 仅影响内置聊天主题、历史聊天与管理长图；自定义 HTML 模板请直接修改模板 CSS
gpt_image_font_scale=1.0

# 接近上下文上限时，摘要后迁移到新逻辑会话；长期角色扮演建议保留默认值。
gpt_context_compaction_mode="summarize_restart"
gpt_context_compaction_threshold=0.6
gpt_context_compaction_min_tokens=0

# 多页帮助、列表、历史等管理输出在 60 秒后自动撤回；0 表示关闭
gpt_management_recall_after=60

# 默认保留原始主语，不再向模型额外解释称呼来源。
# 仅在确实需要兼容旧的称呼语境逻辑时开启，并可自行改写附加提示。
gpt_direct_address_context_enabled=false
gpt_direct_address_context_prompt="【对话语境】用户正在直接称呼你，请结合当前人设自然理解消息中的主语，不要提及这段提示。"

# 请求失败时的用户提示，可按机器人身份调整
gpt_error_message="抱歉，这次没能顺利回应。请稍后再试；若持续发生，请联系机器人管理员。"

# 原会话依赖的账号已移除或停用时的提示；不会暴露账号和风控细节
gpt_conversation_recovery_message="当前对话已无法继续，请重新初始化人设后再试。"

# 首次有效聊天时自动初始化人设。它不会覆盖手动初始化或已有逻辑会话。
gpt_auto_init_group=true
gpt_auto_init_friend=true
gpt_init_group_persona_name="群聊"
gpt_init_friend_persona_name="单人"

# 启用仅超级用户可调用的智能体只读工具
gpt_agent_enabled=false
gpt_agent_confirm_timeout=60
gpt_agent_session_approval_timeout=1800
gpt_agent_plan_timeout=300
# 文件工具只允许访问此工作目录；不需要文件能力时保持未配置。
gpt_agent_workspace="./data/agent-workspace"
gpt_agent_managed_services='[{"name":"bot","kind":"pid_file","pid_file":"/run/nonebot.pid","restart_command":["systemctl","restart","nonebot"],"restart_check_seconds":5},{"name":"local-api","kind":"tcp","host":"127.0.0.1","port":8080}]'
    

# 插件需要一些其他的Nonebot基础配置，请检查是否存在
# 机器人名
NICKNAME=["bot name"]
# 超级管理员用户标识（由所用适配器决定）
SUPERUSERS=["admin user id"]

```

## 🎉 使用

所有聊天和插件命令都需要先 **@ 机器人**，或以 `NICKNAME` / `gpt_chat_start` 中配置的机器人名称开头；这条规则同样适用于 `兑换`、帮助和管理命令。命令与第一个参数可连写或以空格分隔，例如 `bot名 输出模式文本` 和 `bot名 输出模式 文本` 都会切换到文本输出。

### 指令表
| 指令 | 适配器 | 权限 | 需要@ | 范围 |  说明 |
|:-----:|:----:|:----:|:----:|:----:|:----:|
| GPT帮助 / 聊天帮助 [主题] | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 以 `@机器人 GPT帮助` 或 `机器人昵称 GPT帮助` 触发；查看总览或会话、人设、模型、管理、授权、智能体帮助。 |
| @bot 聊天内容... | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | @或者叫名+内容 开始聊天，随所有者白名单模式设置改变 |
| 初始化 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 初始化(人设名) |
| plus初始化 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | plus初始化(人设名) 会使用plus账户新开会话，可切换plus模型 |
| 重置 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 用当前人设开启新的逻辑会话 |
| 重置上一句 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 刷新上一句的回答 |
| 回到过去 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 回到过去 <历史聊天可见轮次/p_id/最后一次出现的关键词>，回到对应时间点 |
| 人设列表 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看可用人设列表 |
| 查看人设 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看人设的具体内容 |
| 添加人设 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 添加人设 (人设名) |
| 历史聊天 [范围] [倒序] | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看当前人格历史聊天记录；人设初始化内容不会展示，可通过 - 或 : 限定范围，如 `2-4`；添加“倒序”会从最新轮次开始展示，但保留原轮次编号。 |
| 历史会话 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看当前群聊私聊的会话列表，上限30 |
| 切换会话 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 切换会话 序列号，根据会话列表序号切换会话 |
| 输出模式 [自动/文本/图片/默认] | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看或覆盖当前聊天范围的富文本输出策略；`默认`恢复 `gpt_render_mode`。 |
| 删除人设 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除人设 (人设名) |
| 黑名单列表 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看黑名单列表 |
| 解黑 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 解黑<账号> ，解除黑名单 |
| 白名单列表 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看白名单列表 |
| 工作状态 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看当前所有账号的工作状态 |
| 智能体 | 兼容 | 仅超级管理员 | 是 | 群聊/私聊/频道 | 需启用 gpt_agent_enabled；“计划 <任务>”只生成受控工具建议，需在原聊天范围使用“执行 <编号>”才会运行对应工具；“审计 [数量]”查看当前运行的无敏感操作记录 |
| 生成cdk [来源] | 兼容 | 仅超级管理员 | 是 | 任意会话 | 生成一次性会话白名单 CDK，并记录创建者、创建会话与可选来源备注 |
| 生成个人cdk [来源] | 兼容 | 仅超级管理员 | 是 | 任意会话 | 生成一次性个人白名单 CDK，兑换者可在同一适配器的任意会话聊天 |
| 兑换 <CDK> | 兼容 | 无 | 是 | 群聊/私聊/频道 | 使用 `@机器人 兑换 <CDK>` 或 `机器人昵称 兑换 <CDK>`；根据 CDK 类型授权当前会话或兑换者本人，兼容旧别名“出现吧”，每个 CDK 只能兑换一次 |
| cdk列表 / 作废cdk <CDK> | 兼容 | 仅超级管理员 | 是 | 任意会话 | 查看 CDK 来源和兑换范围，或作废未兑换的 CDK |
| 退出白名单 / 退出个人白名单 | 兼容 | 白名单 | 是 | 群聊/私聊/频道 | 分别撤销当前访问范围或当前用户的白名单；前者兼容旧别名“结束吧” |
| 添加plus | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 添加plus <稳定标识>，授予自动选择付费账户的权限 |
| 删除plus | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除plus <稳定标识>，撤销付费账户权限 |
| plus切换 | 兼容 | Plus 权限 | 是 | 群聊/私聊/频道 | plus切换 <模型别名或完整模型名>，只更新当前逻辑会话 |
| 全局plus | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 全局plus 开启/关闭，关闭时禁止普通用户的付费模型切换 |
| 会话标识 | 兼容 | 超级管理员/管理会话 | 是 | 任意会话 | 显示当前访问范围标识，用于授权与管理配置 |
| 删除白名单 | 兼容 | 超级管理员/管理会话 | 是 | 任意会话 | 删除白名单 [访问范围标识]；省略时删除当前会话范围 |
| 添加白名单 | 兼容 | 超级管理员/管理会话 | 是 | 任意会话 | 添加白名单 [plus] [访问范围标识]；省略时添加当前会话范围 |

> <为必填内容>，(为选填内容)

> 逻辑会话由用户可见的会话列表管理。模型切换不会泄露或展示底层 ChatGPT 会话 ID。

> 所有插件入口都要求适配器识别为提及机器人，或消息以 `NICKNAME` / `gpt_chat_start` 的名称开头。私聊是否天然满足提及条件由适配器决定；为避免“发了指令却没反应”，所有平台的聊天、CDK、帮助和管理命令都建议明确 @ 或使用名称前缀。

### 群聊、上下文与图片输出

- `gpt_group_chat=true` 时，每一条群聊输入都会在发送给模型前附加固定的 `[群聊发言者]` 标签，包含稳定身份与适配器可用的显示名。它只辅助模型区分成员，不会强制替换模型回复，也不会出现在历史聊天图片中。
- `gpt_history_anonymize=false` 时，历史聊天会将上述内部标签投影为“用户 · 昵称”；标签本身与完整平台身份不会显示。需要隐藏群成员昵称时设为 true。
- 群聊和频道按稳定访问范围共享同一逻辑会话；私聊按用户独立。`历史会话` 的编号按最近使用排序，`切换会话 <编号>` 必须使用该列表里的编号。
- `summarize_restart` 会在接近上下文上限时摘要并迁移到新逻辑会话；`reinforce` 仅补发人设。需要手动强化角色时可用 `初始化 <人设名> 继续`。
- `gpt_render_mode=auto` 会根据内容复杂度与适配器能力选择文本或图片。长帮助、历史、名单等管理内容优先分页图片；多页时优先以合并引用消息发送。
- `输出模式 [自动/文本/图片/默认]` 只影响当前适配器内的当前群聊、私聊或频道。该偏好独立于逻辑会话，因此重置、初始化人设或切换逻辑会话后仍会保留；使用 `@机器人 输出模式 默认` 或 `机器人昵称 输出模式 默认` 即可恢复 `gpt_render_mode` 的全局默认策略。

### 自定义聊天图片模板

`gpt_chat_image_template` 仅控制聊天 Markdown 转图片的主题，不影响纯文本输出或管理页面。内置值：`native`/`原生` 为粉蓝紫纵向卡片，`off`/`关`/`plain` 为黑白纵向样式。内置主题、历史聊天和管理长图默认采用窄一些的纵向阅读栏，并由 `gpt_image_font_scale` 统一调整阅读字号。

也可以复制 [`nonebot_plugin_gpt/templates/chat-image-template.html`](nonebot_plugin_gpt/templates/chat-image-template.html) 后自行修改：

```env
gpt_chat_image_template="./data/gpt/chat-template.html"
```

模板必须包含 `{{ content }}` 占位符，插件会把 Markdown 转换后的 HTML 注入其中。自定义模板由其自身 CSS 完全控制，因此不会自动应用 `gpt_image_font_scale`；需要更大字体或更窄正文时，请直接调整模板中的 `.sheet` 与 `.content`。模板不存在、缺少占位符或渲染失败时会自动回退为文本，不会中断聊天。

> 白名单分为会话授权与个人授权：会话授权使用访问范围标识，会将同一群或频道的不同用户归为同一授权范围；个人授权使用“适配器 + 平台（适用时）+ 用户 ID”，仅在同一平台生效。Satori 会额外纳入其 `login.platform`，不会混淆它承载的不同平台。旧版 `group/private/qqgroup/qqguild` 数据会保留兼容读取，其中旧版 `private` 白名单继续按 OneBot 用户在群聊和私聊中生效。

### CDK 授权

超级用户在任意会话执行 `生成cdk [来源备注]` 后，将机器人返回的兑换指令发送到目标群、私聊或频道即可完成会话授权：`@机器人 兑换 <CDK>`，或 `机器人昵称 兑换 <CDK>`。该兑换码只可使用一次，自动绑定目标会话的跨平台访问范围标识，不需要手写群号或适配器类型。

若需要给某一个人加白，使其在未授权群中也能正常提及机器人聊天，使用 `生成个人cdk [来源备注]`。目标用户在同一适配器任意私聊、群聊或频道发送 `@机器人 兑换 <CDK>` 或 `机器人昵称 兑换 <CDK>` 后，个人授权会绑定该用户；不同平台的用户 ID 不会互相冲突。

旧版 `cdklist.json` 与 `cdksource.json` 会在首次启动时迁移：未使用的 CDK 可以继续兑换；已经兑换的旧 QQ 记录会保留审计信息，但旧数据只有裸群号/频道号，无法安全推导为新范围标识，因此不会被自动授权。管理员可在 `cdk列表` 查看这些“旧版已兑换待确认”记录，并按需重新发放 CDK。


## 常见问题
### cloudflare验证
先检查网络、代理和账号状态。首次登录、Cloudflare、邮箱验证码或 Firefox 启动异常时，将 `gpt_headless=false`，在有桌面的机器上观察浏览器并完成必要的人机验证；不要依赖旧版手工复制会话文件的做法。


### 浏览器问题
浏览器安装或损坏时尝试：`playwright_firefox install firefox`。账号控制台会展示“需要处理”“临时异常”等状态；完成验证后可在本机控制台点击重试登录。

安装更新playwright_firefox时出现 .lock 文件报错时，请删除该文件。

### 微软辅助邮箱验证
Microsoft 可能要求辅助邮箱验证。按登录页面和本机控制台的提示完成验证；不要在机器人聊天、日志或截图中公开验证码。

### openai邮箱验证码
OpenAI 原生登录会先尝试密码。上游要求邮箱验证码时，按本机控制台的待处理状态输入验证码后继续。

### 谷歌登录方式
Google 登录受其自身风控和浏览器环境影响较大。优先在同一机器的可见浏览器中完成 Google 侧验证；不要把导出的 Cookie 或任何会话信息提交、转发或写入公开配置。

### markdown发送问题
插件不依赖各平台不一致的原生 Markdown 协议。复杂 Markdown、链接、表格和长内容会按 `gpt_render_mode` 转为兼容的纵向图片；普通内容仍尽量以文本发送。可通过 `gpt_chat_image_template` 调整聊天图片主题。

### 历史聊天问题
历史聊天会隐藏初始化、强化人设等私有提示词，并将其余对话从第 1 轮重新编号；`回到过去 <编号>`使用的也是这个可见编号。历史较长时会分页为图片，渲染或适配器不支持时才回退为分页文本。可使用`2-5`或`:5`限定查看范围，也可追加“倒序”，例如 `历史聊天 2-5 倒序`；倒序只改变展示顺序，不会改变编号或回退目标。

历史图片中的普通 Markdown 链接会显示为“标题[编号]”，图片页底部会列出对应标题和域名，随后补发一条含完整 URL 的文本消息，便于复制或在支持的平台直接打开。网页私有引用标记依赖上游元数据；旧历史未保存来源映射时会被隐藏，不会伪造出处。

### 合并消息图片异常
使用llonebot可能导致发出的合并消息的图片，在旧版pcqq上无法显示，临时解决方法是，手动转发该消息一次


### 数据缓存
由 `nonebot-plugin-localstore` 决定。请通过该插件的文档或运行环境查看实际数据目录；不要在脚本中假定固定的旧版会话目录。
见 nonebot_plugin_localstore 插件说明，通常为用户目录下 
```bash
# linux
~/.local/share/nonebot2/nonebot_plugin_gpt/\{bot_name\}
```
```bash
# windows
C:\Users\UserName\AppData\Local\nonebot2\nonebot_plugin_gpt\\{bot_name\}
```

### 自动初始化人设

纯新部署可以直接聊天；如果自动初始化配置的人设尚未创建或已删除，插件会跳过自动初始化，让用户首条消息创建普通无角色会话，不会自动套用“默认”人设。1.0.3版本历史人设和旧授权数据会在启动时尽力迁移。

### 长列表输出

帮助、工作状态、黑白名单、人设、CDK、历史会话和历史聊天会优先分页图片。多页图片优先使用 Alconna 合并引用消息发送；当前适配器不支持时才逐张发送，渲染环境异常时回退分页文本。人设、黑白名单、白名单和 CDK 列表均最新在前；人设继续保留原始编号。

### 管理员与白名单

`SUPERUSERS` 与 `gpt_manage_ids` 指定的管理会话可以在未加白的范围内执行管理命令。普通聊天始终遵守 `gpt_white_list_mode`，不会因管理员偶然发言绕过群聊白名单。会话 CDK 用于授权当前聊天范围；个人 CDK 用于授权兑换者在同一适配器的其他会话。

### 智能体Agent

暂未实现，相关命令可忽略

### 更新日志
2026.07.16 1.1.3
1. 跨平台支持（未全量测试）
2. 更稳定的底层依赖


2025.08.11 1.0.3
1. 修复cf问题
2. 修复openai和microsoft登录问题
3. google暂时无法登录，等待后续修复
4. openai可能也无法登录


2025.07.27 1.0.2
1. 修复windows下无法使用的问题
2. 修复onebot适配器bug导致发不出合并消息
3. 优化带有元数据的markdown消息展示


2025.07.20 1.0.1
1. 升级httpx版本至0.28.1，修复其参数
2. 优化底层，增强可用性，如果有问题请尝试`playwright_firefox install firefox`
3. 增加了历史会话列表
4. 增加了切换历史会话功能
5. 默认会开启联网搜索，下版本增加独立会话开关
6. 修复联网搜索导致的消息不完整
7. 增加了gpt生成和搜索到图片的获取展示
8. 更新模型列表与官网一致，增加了强制升级基础模型功能（gpt-4-1-mini）
9. 增加了历史聊天树
10. 增加历史聊天转图片问题，详见上方说明
11. 更改了plus相关逻辑，现在切换模型不会切换会话，但只有被标记为使用plus账号的会话，才能切换模型
12. 轻微改变`工作状态`显示


2025.02.09 0.0.43
1. 添加openai登录验证码填写功能
2. 修复微软账户登录步骤
3. 修复消息有时接收处理错误的问题


2024.12.12 0.0.42
1. 更新可用性
2. 调整黑名单列表为100条一张图，多图发送


2024.12.01 0.0.40
1. 修复插件无法使用的问题
2. 优化工作状态查看，增加白名单状态
3. 添加发送消息异常和刷新cookie异常截图保存（登录失败截图固定开启，截图保存在bot目录screen下）
4. readme添加cf验证操作步骤说明


2024.07.28 0.0.39
1. 添加使用plus模型时，可上传文件（目前只支持图片）
2. 继续尝试修复长时间运行时，access_token过期未自动刷新的问题


2024.07.21 0.0.37
1. 添加并修改默认使用模型喂gpt-4o-mini（3.5仍然可用但性能下降很多）（4om和3.5免费用户都可用，但3.5预计迟早下架，所以不建议使用，也就偷个懒，不添加非plus用户切换3.5功能了）
2. 更新openai接口


2024.07.16 0.0.36
1. 修复0.0.35版本中，未正确捕获自身入群事件的问题
2. 自动初始化人设添加频道相关支持
3. 尝试修复长时间运行时，access_token过期未自动刷新的问题


2024.07.15 0.0.35
1. 修复0.0.34造成的gpt plus账户会话失败的问题
2. 优化添加人设名称识别
3. 添加新功能，入群/加好友后，自动初始化人设，让bot一个人出门在外也更加顺畅


2024.07.12 0.0.34
1. 修复部分消息接收失败问题


2024.07.11 0.0.33
1. 添加QQ适配器 Url 输出替换
2. 优化登录流程
3. 优化消息超时问题
4. 添加代理用的用户名密码


2024.06.23 0.0.32
1. 修复多账户下相关命令换号发送的情况
2. 优化了登录部分
3. 修复上次更新导致的一个bug，让私聊用户丢失了原有的会话，本次更新后原有私聊用户会话会切换回去，在两次更新期间的新用户会话会丢失（偷个懒，就不做迁移了）


2024.06.15 0.0.31
1. 优化登录方式
2. 优化google登录缓存
3. 优化白名单列表，新增部分plus白名单单独显示，提示两种白名单模式独立运作


2024.06.11 0.0.29
1. 修复openai新cookie跨域问题
2. 修复google登录问题
3. 优化了token和状态显示


2024.06.04 0.0.28
1. 添加gptplus账户支持及其gpt4 4o模型使用
2. 修复windows下数据目录异常问题
3. 添加QQ适配器图片发送支持
4. 优化图片间距
5. 修复添加账户后，会话数计数错误


2024.05.20 0.0.26
1. 修复非全局代理下，websocket灰度账号代理未生效的问题


2024.05.16 0.0.25
1. 修复websocket账号未正常工作的bug
2. 跟进openai新（旧）token验证
3. 修正工作状态会话数标题错误
4. 为白名单列表添加cdk生成源信息，方便溯源


2024.05.10 0.0.24
1. 跟进新token生成验证
2. 为初始化人设异常时添加错误提示


2024.05.07 0.0.23
1. 修复webssocket url未更新
2. 优化工作状态输出会话数遮蔽问题
3. 修复空数据时未正确重试的问题
4. 兼容pyd2


2024.05.06 0.0.20
1. 优化登录和消息接收流程
2. 优化初始化时多bot账号主体发送消息不对的问题
3. 兼容新websocket接收方式（我以为都SSE了）
   
   
2024.05.04 0.0.18
1. 跟进openai新搞得幺蛾子验证（加班太累了，更晚了）
2. markdown被人作没了，唉（吐槽）
3. 目前只简单实现了新验证，代码很乱，抽空应该会优化


2024.04.18 0.0.17
1. 跟进新markdown发送方式


2024.04.17 0.0.15
1. 尝试解决持久连接接收不到消息的问题
2. 添加markdown消息用户自定义开关（QQ适配器md能力待支持）
3. 优化markdown消息发送时，人设名未匹配消除的问题


2024.03.24 0.0.13
1. 修复qq适配器的人设列表无法显示的问题
2. 添加了会话超时时间，避免意外情况导致session阻塞
3. 优化了工作状态显示，目前login为登录中，登陆后未工作则为ready
4. 添加了全cookie保存，降低重新登录异常的风险


2024.03.22  0.0.12
1. 临时修复了一些错误
2. 优化多账户私聊混乱问题


2024.03.20
1. 没有新功能增加，临时更新一下添加httpx关闭配置（现默认关闭），目前它还有些问题。新流程还没写完，等下次放假。


2024.03.17
1. 优化了底层代码，减少错误，暂不支持gpt plus账号（待填坑）
2. 支持拉格兰md发送


2024.03.13
1. 兼容拉格兰合并转发，修复合并转发失败的问题
2. 添加自定义聊天前缀，现在可以不用@也能触发了


2024.03.11
1. 临时修复200问题（chatgpt新的websocket问题），最近好忙，等闲了的时候再优化，有什么问题都可以先提issue


2024.02.19
1. 临时修复200问题 与 添加 微软辅助邮箱验证

## 待续
自用挺久了，匆忙改改发出来，很多东西还没补充
