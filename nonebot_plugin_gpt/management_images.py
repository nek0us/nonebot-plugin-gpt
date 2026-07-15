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
    _usage_requests,
)


_STYLE = """
* { box-sizing: border-box; }
body { margin: 0; color: #1d2939; background: #f5f7fa; font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
.sheet { width: 900px; padding: 36px; background: #f5f7fa; }
.header { padding: 30px 32px; color: #ffffff; background: #12344d; border-radius: 8px; }
.eyebrow { margin: 0 0 8px; color: #b7d9d6; font-size: 15px; font-weight: 700; }
h1 { margin: 0; color: inherit; font-size: 32px; line-height: 1.2; }
.subtitle { margin: 10px 0 0; color: #d7e5ed; font-size: 16px; line-height: 1.55; }
.summary { display: flex; gap: 12px; margin: 20px 0; }
.metric { flex: 1; min-height: 90px; padding: 18px 20px; background: #ffffff; border: 1px solid #d9e2ec; border-radius: 8px; }
.metric-label { color: #627d98; font-size: 14px; }
.metric-value { margin-top: 7px; color: #102a43; font-size: 28px; font-weight: 700; }
.notice { margin: 0 0 20px; padding: 14px 16px; color: #7c2d12; background: #fff7ed; border-left: 4px solid #f97316; border-radius: 4px; font-size: 14px; line-height: 1.55; }
.account, .content { margin-top: 16px; padding: 22px 24px; background: #ffffff; border: 1px solid #d9e2ec; border-radius: 8px; }
.account-head { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.email { max-width: 600px; overflow-wrap: anywhere; color: #102a43; font-size: 19px; font-weight: 700; }
.badge { padding: 5px 10px; border-radius: 4px; font-size: 13px; font-weight: 700; white-space: nowrap; }
.ready { color: #0f5132; background: #d1fae5; }
.attention { color: #9a3412; background: #ffedd5; }
.details { margin: 14px 0 0; color: #486581; font-size: 15px; line-height: 1.65; }
.runtime { margin-top: 10px; color: #1f5f5b; font-size: 14px; }
.action { margin-top: 12px; padding: 10px 12px; color: #7c2d12; background: #fff7ed; border-radius: 4px; font-size: 14px; line-height: 1.5; }
.section { margin-top: 24px; }
h2 { margin: 0 0 14px; color: #102a43; font-size: 22px; }
p { margin: 10px 0; color: #334e68; font-size: 16px; line-height: 1.7; white-space: pre-wrap; }
ul { margin: 12px 0; padding-left: 22px; color: #334e68; }
li { margin: 9px 0; font-size: 16px; line-height: 1.55; }
.footer { margin-top: 18px; color: #829ab1; font-size: 13px; text-align: right; }
"""


def _document(title: str, subtitle: str, content: str) -> str:
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><style>{_STYLE}</style></head>
<body><main class=\"sheet\"><header class=\"header\"><p class=\"eyebrow\">NONEBOT PLUGIN</p><h1>{escape(title)}</h1><p class=\"subtitle\">{escape(subtitle)}</p></header>{content}<footer class=\"footer\">由 nonebot-plugin-gpt 生成</footer></main></body></html>"""


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
    available = sum(_account_available(account) for account in normalized)
    attention = sum(bool(_action_for(account)) for account in normalized)
    metrics = (
        f"<section class=\"summary\"><div class=\"metric\"><div class=\"metric-label\">已配置账户</div><div class=\"metric-value\">{len(normalized)}</div></div>"
        f"<div class=\"metric\"><div class=\"metric-label\">当前可用</div><div class=\"metric-value\">{available}</div></div>"
        f"<div class=\"metric\"><div class=\"metric-label\">需要处理</div><div class=\"metric-value\">{attention}</div></div></section>"
    )
    if not normalized:
        content = metrics + "<section class=\"content\"><p>当前没有已配置账户。</p></section>"
        return _document("工作状态", "账户、浏览器和模型能力概览", content)

    cards = []
    for account in normalized:
        email = escape(str(account.get("email", "未知账户")))
        is_available = _account_available(account)
        badge_class = "ready" if is_available else "attention"
        badge = "可用" if is_available else "需处理"
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


async def render_management_image(html: str) -> UniMessage:
    """使用 htmlkit 渲染管理视图，并封装为跨平台图片消息。"""
    from nonebot_plugin_htmlkit import html_to_pic

    image = await html_to_pic(
        html,
        dpi=120,
        max_width=920,
        device_height=10,
        default_font_size=15,
    )
    return UniMessage.image(raw=image, name="gpt-management.png")
