<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/NoneBotPlugin.svg" width="240" alt="NoneBotPluginText"></p>
</div>

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

自用的使用浏览器ChatGPT接入Nonebot2，兼容 onebot v11 与 qq 适配器

### 使用条件

需要纯净ip用来过cf，另外根据使用账号数量需要相应多的内存

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-gpt

</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details>
<summary>pip</summary>

    pip install nonebot-plugin-gpt
</details>
<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-gpt
</details>
<details>
<summary>poetry</summary>

    poetry add nonebot-plugin-gpt
</details>
<details>
<summary>conda</summary>

    conda install nonebot-plugin-gpt
</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_gpt"]

</details>

<details open>
<summary>升级插件版本</summary>

    pip install nonebot-plugin-gpt -U

</details>

## ⚙️ 配置

在 nonebot2 项目的`.env`文件中添加下表中的必填配置

| 配置项 | 必填 | 默认值 | 类型 | 说明 |
|:-----:|:----:|:----:|:----:|:----:|
| gpt_session | 是 | 无 | List[Dict[str,str]] | openai账号密码 |
| gpt_proxy | 否 | 无 | str | 使用的代理 |
| arkose_status | 否 | false | bool | gpt是否开启了arkose验证 |
| group_chat | 否 | true | bool | 群里开启多人识别 |
| gpt_chat_start | 否 | [] | list | 聊天前缀，参考nb命令前缀 |
| gpt_chat_start_in_msg | 否 | false | bool | 命令前缀是否包含在消息内 |
| begin_sleep_time | 否 | false | bool | 关闭启动等待时间（建议账号数量大于5开启） |
| gpt_chat_priority | 否 | 90 | int | gpt聊天响应优先级 |
| gpt_command_priority | 否 | 19 | int | gpt命令响应优先级 |
| gpt_white_list_mode | 否 | true | bool | 聊天白名单模式 |
| gpt_replay_to_replay | 否 | false | bool | 是否响应"回复消息" |
| gpt_ban_str | 否 | 无 | List[str] | 黑名单屏蔽词列表 |
| gpt_manage_ids | 否 | 无 | List[str] | 超管群/频道id，通过日志等方式获得 |
| gpt_lgr_markdown| 否 | false | bool | 以拉格兰md消息回复 |
| gpt_httpx| 否 | false | bool | 使用httpx |

```bash
# gpt配置示例
# 当mode为空或者为openai时，建议提前手动登录一次获取session_token填入（成功使用后可删除session_token项），mode目前不支持苹果账号
gpt_session='[
    {
        "email": "xxxx@hotmail.com",
        "password": "xxxx",
        "session_token": "ey....", 
    },
    {
        "email": "aaaa@gmail.com",
        "password": "xxxx",
        "mode": "google",
    },
    {
        "email": "bbb@sss.com",
        "password": "xxxx",
        "mode": "microsoft",
        "help_email": "xxx@xx.com"
    },
]'

gpt_proxy='http://127.0.0.1:8080'

arkose_status=false

group_chat=true

gpt_chat_start=[]

gpt_chat_start_in_msg=false

begin_sleep_time=true

gpt_chat_priority=90

gpt_command_priority=19

gpt_white_list_mode=true

gpt_replay_to_replay=false

gpt_ban_str='[
    "我是猪",
    "你是猪",
]'
# qq适配器使用的超管群id
gpt_manage_ids=['qq group id......']
# onebot适配器 拉格兰md消息兼容
gpt_lgr_markdown=false
# 使用httpx（暂不完善）
gpt_httpx=false

# 插件需要一些其他的Nonebot基础配置，请检查是否存在
# 机器人名
nickname=["bot name"]
# 超管QQ（onebot用）
SUPERUSERS=["qq num"]

```

## 🎉 使用
### 指令表
| 指令 | 适配器 | 权限 | 需要@ | 范围 |  说明 |
|:-----:|:----:|:----:|:----:|:----:|:----:|
| @bot 聊天内容... | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | @或者叫名+内容 开始聊天，随所有者白名单模式设置改变 |
| 初始化 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 初始化<人设名> |
| 重置 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 回到初始化人设后的第二句话时 |
| 重置上一句 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 刷新上一句的回答 |
| 回到过去 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 回到过去 <对话序号/p_id/最后一次出现的关键词> ，回到括号内的对话时间点|
| 人设列表 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看可用人设列表 |
| 查看人设 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看人设的具体内容 |
| 添加人设 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 添加人设 (人设名) |
| 历史聊天 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看当前人格历史聊天记录 |
| 删除人设 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除人设 (人设名) |
| 黑名单列表 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看黑名单列表 |
| 解黑 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 解黑<账号> ，解除黑名单 |
| 白名单列表 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看白名单列表 |
| 添加白名单 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 添加白名单 <账号/群号> (个人/群) ，添加白名单，最后不写默认为群 |
| 删除白名单 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除白名单 <账号/群号> (个人/群) ，删除白名单，最后不写默认为群 |
| 工作状态 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看当前所有账号的工作状态 |
| 获取本地id | qq | 无/白名单 | 是 | 群聊/频道 | 群聊内获取id |
| 生成cdk | qq | 超管群 | 是 | 群聊/频道 | 生成cdk <群号/其他信息>，以绑定信息方式生成白名单cdk |
| 出现吧 | qq | 无 | 是 | 群聊/频道 | 出现吧 \<cdk\>，以绑定id形式使用cdk加入白名单 |
| 结束吧 | qq | 白名单 | 是 | 群聊/频道 | 结束吧 ，用户自主解除白名单 |

<为必填内容>，(为选填内容)

## 常见问题
### 微软辅助邮箱验证
当触发验证后，会在启动目录生成带有启动账号名称的文件，键入收到的验证码并保存，即可自动验证。留意日志输出提示

### 更新日志
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
