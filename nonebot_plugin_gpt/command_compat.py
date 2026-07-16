"""旧命令迁移到 Alconna 时使用的兼容构造器。"""

from collections.abc import Iterable

from arclet.alconna import AllParam, Alconna, Args, CommandMeta


def command_argument_text(value: object | None) -> str:
    """将 Alconna 捕获的参数统一为旧处理器所需的文本。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value)


def build_legacy_command(
    name: str,
    aliases: set[str] | None = None,
    address_prefixes: Iterable[str] = (),
) -> Alconna:
    """保留旧命令，并兼容称呼、命令和参数的连写形式。"""
    command = Alconna(
        name,
        Args["argument?", AllParam],
        separators={"", " "},
        meta=CommandMeta(compact=True),
    )
    command_names = {name, *(aliases or ())}
    for alias in command_names - {name}:
        command.shortcut(alias, command=name, prefix=True)
    for address in address_prefixes:
        normalized = str(address).strip()
        if not normalized:
            continue
        for command_name in command_names:
            command.shortcut(f"{normalized} {command_name}", command=name, prefix=True)
            command.shortcut(f"{normalized}{command_name}", command=name, prefix=True)
    return command
