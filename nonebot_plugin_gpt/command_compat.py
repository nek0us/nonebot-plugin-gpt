"""旧命令迁移到 Alconna 时使用的兼容构造器。"""

from collections.abc import Iterable

from arclet.alconna import AllParam, Alconna, Args, CommandMeta


_registered_command_names: set[str] = set()


def command_argument_text(value: object | None) -> str:
    """将 Alconna 捕获的参数统一为旧处理器所需的文本。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value)


def preferred_address_prefix(values: Iterable[object]) -> str:
    """选取可复制到命令文本中的首个有效机器人昵称。"""
    for value in values:
        prefix = str(value).strip()
        if prefix:
            return prefix
    return ""


def is_registered_command_text(
    value: str,
    address_prefixes: Iterable[str] = (),
) -> bool:
    """判断已显式称呼机器人的文本是否属于本插件已注册命令。"""
    candidate = value.strip()
    for prefix in sorted(
        (str(item).strip() for item in address_prefixes if str(item).strip()),
        key=len,
        reverse=True,
    ):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):].lstrip(" \t,，:：;；")
            break
    return any(candidate.startswith(name) for name in _registered_command_names)


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
    _registered_command_names.update(command_names)
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
