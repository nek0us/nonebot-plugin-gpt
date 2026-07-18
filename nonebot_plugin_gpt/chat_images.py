"""聊天 Markdown 的纵向图片渲染与用户模板支持。"""

from __future__ import annotations

from pathlib import Path

import markdown


_NATIVE_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
* { box-sizing: border-box; }
:root { --gpt-image-font-scale: {{ font_scale }}; }
body { margin: 0; background: #f5f6fb; color: #28364d; font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
.sheet { width: 680px; padding: 20px; }
.message { padding: 24px 25px; border: 1px solid #e2e5ef; border-radius: 14px; background: #ffffff; box-shadow: 0 6px 22px rgba(67, 76, 108, .08); }
.content { font-size: calc(18px * var(--gpt-image-font-scale)); line-height: 1.76; overflow-wrap: anywhere; }
.content > :first-child { margin-top: 0; }.content > :last-child { margin-bottom: 0; }
h1, h2, h3 { color: #354064; letter-spacing: 0; }
h1 { margin: 24px 0 16px; padding-left: 14px; border-left: 6px solid #8a72d6; font-size: calc(29px * var(--gpt-image-font-scale)); line-height: 1.3; }
h2 { margin: 22px 0 13px; padding-left: 12px; border-left: 5px solid #79a9dc; font-size: calc(24px * var(--gpt-image-font-scale)); line-height: 1.35; }
h3 { margin: 19px 0 10px; padding-left: 10px; border-left: 4px solid #e58ab0; font-size: calc(20px * var(--gpt-image-font-scale)); line-height: 1.4; }
p { margin: 12px 0; } ul, ol { margin: 12px 0; padding-left: 1.55em; } li { margin: 7px 0; } li::marker { color: #8a72d6; }
blockquote { margin: 15px 0; padding: 11px 15px; border-left: 4px solid #d6c8ff; border-radius: 0 9px 9px 0; background: #f6f2ff; color: #4b5370; }
code { padding: 2px 5px; border-radius: 4px; background: #f2f4f8; color: #a34b72; font-family: Consolas, monospace; }
pre { margin: 16px 0; padding: 15px; overflow-x: auto; border-radius: 10px; background: #293449; color: #edf2ff; } pre code { padding: 0; background: transparent; color: inherit; }
table { width: 100%; margin: 15px 0; border-collapse: separate; border-spacing: 0; overflow: hidden; border: 1px solid #e0e4ee; border-radius: 9px; font-size: calc(16px * var(--gpt-image-font-scale)); }
th { padding: 9px 11px; background: #eee9ff; color: #5d4aa3; text-align: left; } td { padding: 9px 11px; border-top: 1px solid #e9ecf2; } tr:nth-child(even) td { background: #fafbfe; }
a { color: #4779ba; text-decoration: none; overflow-wrap: anywhere; } img { display: block; max-width: 100%; height: auto; margin: 14px auto; border-radius: 9px; } hr { border: 0; border-top: 1px solid #e3e6ef; margin: 20px 0; }
</style></head><body><main class="sheet"><article class="message"><div class="content">{{ content }}</div></article></main></body></html>"""


_PLAIN_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
* { box-sizing: border-box; }
:root { --gpt-image-font-scale: {{ font_scale }}; }
body { margin: 0; background: #ffffff; color: #161616; font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
.sheet { width: 680px; padding: 22px 24px; }.content { font-size: calc(18px * var(--gpt-image-font-scale)); line-height: 1.76; overflow-wrap: anywhere; }.content > :first-child { margin-top: 0; }.content > :last-child { margin-bottom: 0; }
h1 { margin: 22px 0 15px; padding-left: 13px; border-left: 5px solid #111111; font-size: calc(28px * var(--gpt-image-font-scale)); } h2 { margin: 20px 0 12px; padding-left: 11px; border-left: 4px solid #333333; font-size: calc(23px * var(--gpt-image-font-scale)); } h3 { margin: 17px 0 9px; padding-left: 9px; border-left: 3px solid #555555; font-size: calc(20px * var(--gpt-image-font-scale)); }
p { margin: 12px 0; } ul, ol { margin: 12px 0; padding-left: 1.5em; } li { margin: 7px 0; } blockquote { margin: 15px 0; padding: 10px 14px; border-left: 3px solid #333333; background: #f5f5f5; }
code { padding: 2px 5px; background: #eeeeee; font-family: Consolas, monospace; } pre { margin: 16px 0; padding: 14px; overflow-x: auto; background: #171717; color: #f5f5f5; } pre code { padding: 0; background: transparent; color: inherit; }
table { width: 100%; margin: 15px 0; border-collapse: collapse; font-size: calc(16px * var(--gpt-image-font-scale)); } th, td { padding: 9px 10px; border: 1px solid #222222; text-align: left; } th { background: #eeeeee; } a { color: #111111; text-decoration: underline; overflow-wrap: anywhere; } img { display: block; max-width: 100%; height: auto; margin: 14px auto; } hr { border: 0; border-top: 1px solid #333333; margin: 20px 0; }
</style></head><body><main class="sheet"><article class="content">{{ content }}</article></main></body></html>"""


def _markdown_to_html(source: str) -> str:
    return markdown.markdown(
        source,
        extensions=["pymdownx.tasklist", "tables", "fenced_code", "codehilite", "pymdownx.tilde"],
    )


def _template_source(template: str) -> tuple[str, bool]:
    normalized = (template or "native").strip()
    mode = normalized.casefold()
    if mode in {"native", "原生"}:
        return _NATIVE_TEMPLATE, True
    if mode in {"off", "关", "关闭", "plain"}:
        return _PLAIN_TEMPLATE, True

    path = Path(normalized).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"聊天图片模板不存在：{path}")
    source = path.read_text(encoding="utf-8")
    if "{{ content }}" not in source:
        raise ValueError("聊天图片模板必须包含 {{ content }} 占位符")
    return source, False


def build_chat_html(markdown_text: str, *, template: str = "native", font_scale: float = 1.0) -> str:
    """将模型 Markdown 注入内置主题或用户提供的 HTML 模板。"""
    source, builtin = _template_source(template)
    if builtin:
        source = source.replace("{{ font_scale }}", f"{font_scale:.2f}")
    return source.replace("{{ content }}", _markdown_to_html(markdown_text))


async def render_chat_markdown(
    markdown_text: str,
    *,
    template: str = "native",
    font_scale: float = 1.0,
) -> bytes:
    """渲染适合群聊阅读的窄幅纵向聊天图片。"""
    from nonebot_plugin_htmlkit import html_to_pic

    return await html_to_pic(
        build_chat_html(markdown_text, template=template, font_scale=font_scale),
        dpi=110,
        max_width=720,
        device_height=10,
        default_font_size=16,
    )
