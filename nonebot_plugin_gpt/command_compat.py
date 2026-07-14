"""旧命令迁移到 Alconna 时使用的兼容构造器。"""

from arclet.alconna import AllParam, Alconna, Args


def command_argument_text(value: object | None) -> str:
    """将 Alconna 捕获的参数统一为旧处理器所需的文本。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value)


def build_legacy_command(name: str, aliases: set[str] | None = None) -> Alconna:
    """保留 NoneBot 旧命令名称与别名，并允许别名后继续携带参数。"""
    command = Alconna(name, Args["argument?", AllParam])
    for alias in aliases or ():
        command.shortcut(alias, command=name, prefix=True)
    return command
