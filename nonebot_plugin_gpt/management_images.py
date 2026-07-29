"""将帮助与账户状态渲染为适合聊天平台阅读的信息图片。"""

from __future__ import annotations

from html import escape
from typing import Any

from nonebot_plugin_alconna.uniseg import UniMessage

from .help_views import format_help
from .management_views import (
    _action_for,
    _account_available,
    _as_int,
    _plan_name,
    _runtime_name,
    _runtime_summary,
    _status_counts,
    _usage_requests,
)


_STYLE = """
* { box-sizing: border-box; }
body { margin: 0; color: #29384f; background: #f6f7fb; font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
.sheet { width: 960px; padding: 30px; background: #f6f7fb; }
.header { padding: 24px 28px; border: 1px solid #e3e6f0; border-left: 7px solid #8c75d9; border-radius: 10px; background: #ffffff; }
h1 { margin: 0; color: #2c3654; font-size: 30px; line-height: 1.25; }
.subtitle { margin: 8px 0 0; color: #737b91; font-size: 14px; line-height: 1.55; }
.summary { display: flex; gap: 12px; margin: 18px 0; }
.metric { flex: 1; min-height: 90px; padding: 18px 20px; border: 1px solid #e3e6f0; border-radius: 8px; background: #ffffff; }
.metric:nth-child(1) { background: #eef5ff; border-color: #d7e8fb; }.metric:nth-child(2) { background: #fff1f6; border-color: #ffdce9; }.metric:nth-child(3) { background: #f2efff; border-color: #ded5ff; }
.metric-label { color: #5b6680; font-size: 14px; }.metric-value { margin-top: 7px; color: #354064; font-size: 28px; font-weight: 700; }
.notice { margin: 0 0 18px; padding: 14px 16px; color: #934565; background: #fff1f6; border-left: 4px solid #e58ab0; border-radius: 5px; font-size: 14px; line-height: 1.55; }
.account, .content { margin-top: 16px; padding: 22px 24px; background: #ffffff; border: 1px solid #e3e6f0; border-radius: 8px; }
.account-head { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.email { max-width: 600px; overflow-wrap: anywhere; color: #354064; font-size: 19px; font-weight: 700; }
.badge { padding: 5px 10px; border-radius: 4px; font-size: 13px; font-weight: 700; white-space: nowrap; }
.ready { color: #0f5132; background: #d1fae5; }
.attention { color: #934565; background: #fff0f6; }
.details { margin: 14px 0 0; color: #4b5872; font-size: 15px; line-height: 1.65; }
.runtime { margin-top: 10px; color: #466f9d; font-size: 14px; }
.action { margin-top: 12px; padding: 10px 12px; color: #6651a8; background: #f2efff; border-radius: 5px; font-size: 14px; line-height: 1.5; }
.section { margin-top: 24px; }
h2 { margin: 0 0 14px; color: #4c5d88; font-size: 22px; }
p { margin: 10px 0; color: #3f4d66; font-size: 16px; line-height: 1.7; white-space: pre-wrap; }
ul { margin: 12px 0; padding-left: 22px; color: #3f4d66; }
li { margin: 9px 0; font-size: 16px; line-height: 1.55; }
li::marker { color: #8c75d9; }
"""


def _document(title: str, subtitle: str, content: str) -> str:
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><style>{_STYLE}</style></head>
<body><main class=\"sheet\"><header class=\"header\"><h1>{escape(title)}</h1><p class=\"subtitle\">{escape(subtitle)}</p></header>{content}</main></body></html>"""


def build_help_html(topic: str = "") -> str:
    """生成主题帮助图片的 HTML，不依赖运行时渲染器。"""
    text = format_help(topic)
    lines = [line.strip() for line in text.splitlines()]
    title = lines[0] if lines else "GPT 帮助"
    body = []
    list_items: list[str] = []

    def flush_list() -> None:
        if list_items:
            body.append("<ul>" + "".join(f"<li>{escape(item)}</li>" for item in list_items) + "</ul>")
            list_items.clear()

    for line in lines[1:]:
        if not line:
            flush_list()
            continue
        if line.startswith("- "):
            list_items.append(line[2:])
            continue
        flush_list()
        body.append(f"<p>{escape(line)}</p>")
    flush_list()
    return _document(title, "按主题查看命令与权限说明", f"<section class=\"content\">{''.join(body)}</section>")


def build_account_status_html(status: dict[str, Any], *, failure_summary: str = "") -> str:
    """生成管理员账户状态图片的 HTML，不包含凭据与上游原始错误。"""
    accounts = status.get("accounts")
    normalized = [account for account in accounts if isinstance(account, dict)] if isinstance(accounts, list) else []
    configured, available, attention = _status_counts(status, normalized)
    metrics = (
        f"<section class=\"summary\"><div class=\"metric\"><div class=\"metric-label\">已配置账户</div><div class=\"metric-value\">{configured}</div></div>"
        f"<div class=\"metric\"><div class=\"metric-label\">当前可用</div><div class=\"metric-value\">{available}</div></div>"
        f"<div class=\"metric\"><div class=\"metric-label\">需要处理</div><div class=\"metric-value\">{attention}</div></div></section>"
    )
    if not normalized:
        content = metrics + "<section class=\"content\"><p>当前没有已配置账户。</p></section>"
        return _document("工作状态", "账户、浏览器和模型能力概览", content)

    cards = []
    for account in normalized:
        email = "共享核心" if account.get("shared_core") else escape(str(account.get("email", "未知账户")))
        is_available = _account_available(account)
        badge_class = "ready" if is_available else "attention"
        badge = "可用" if is_available else "需处理"
        if account.get("shared_core"):
            details = f"共享核心汇总　·　运行 {_runtime_name(account)}<br>账户明细仅在核心控制台展示"
        else:
            details = (
                f"套餐 {_plan_name(account)}　·　运行 {_runtime_name(account)}<br>"
                f"会话 {_as_int(account.get('conversation_count'))}　·　"
                f"已观测模型 {_as_int(account.get('observed_model_count'))}　·　"
                f"本进程请求 {_usage_requests(account)}"
            )
        runtime = _runtime_summary(account)
        action = _action_for(account)
        cards.append(
            f"<section class=\"account\"><div class=\"account-head\"><div class=\"email\">{email}</div>"
            f"<span class=\"badge {badge_class}\">{badge}</span></div><div class=\"details\">{details}</div>"
            + (f"<div class=\"runtime\">{escape(runtime)}</div>" if runtime else "")
            + (f"<div class=\"action\">{escape(action)}</div>" if action else "")
            + "</section>"
        )
    notice = f"<p class=\"notice\">聊天失败汇总：{escape(failure_summary)}</p>" if failure_summary else ""
    return _document("工作状态", "账户、浏览器和模型能力概览", metrics + notice + "".join(cards))


def _reading_style(font_scale: float) -> str:
    return f"""
:root {{ --gpt-image-font-scale: {font_scale:.2f}; }}
.sheet {{ width: 760px; padding: 22px; }}
h1 {{ font-size: calc(30px * var(--gpt-image-font-scale)); }}
.subtitle, .metric-label, .notice, .runtime, .action {{ font-size: calc(15px * var(--gpt-image-font-scale)); }}
.metric-value {{ font-size: calc(27px * var(--gpt-image-font-scale)); }}
.email {{ font-size: calc(18px * var(--gpt-image-font-scale)); }}
.details, p, li {{ font-size: calc(17px * var(--gpt-image-font-scale)); line-height: 1.7; }}
h2 {{ font-size: calc(23px * var(--gpt-image-font-scale)); }}
"""


async def render_management_image(html: str, *, font_scale: float = 1.0) -> UniMessage:
    """使用 htmlkit 渲染管理视图，并封装为跨平台图片消息。"""
    from nonebot_plugin_htmlkit import html_to_pic

    image = await html_to_pic(
        html.replace("</style>", _reading_style(font_scale) + "</style>", 1),
        dpi=120,
        max_width=800,
        device_height=10,
        default_font_size=16,
    )
    return UniMessage.image(raw=image, name="gpt-management.png")
