"""旧命令迁移到 Alconna 时使用的兼容构造器。"""

from arclet.alconna import Alconna, Args


def build_legacy_command(name: str, aliases: set[str] | None = None) -> Alconna:
    """保留 NoneBot 旧命令名称与别名，并允许别名后继续携带参数。"""
    command = Alconna(name, Args["argument?", str])
    for alias in aliases or ():
        command.shortcut(alias, command=name, prefix=True)
    return command
