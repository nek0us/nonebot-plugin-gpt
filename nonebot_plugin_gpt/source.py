import os
import json
import shutil
from pathlib import Path
from nonebot import require
require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store  # noqa: E402


nb_project = os.path.basename(os.getcwd())

plugin_data_dir: Path = store.get_data_dir("nonebot_plugin_gpt")
data_dir = plugin_data_dir / nb_project

# 需要移动的文件夹列表
dirs_to_move = ["ban", "white", "person", "conversation"]

# 兼容性更新
if os.name == 'nt':
    incorrect_dir = Path(os.getcwd())
    if incorrect_dir.exists() and incorrect_dir.is_dir():
        for dir_name in dirs_to_move:
            src_dir = incorrect_dir / dir_name
            dest_dir = data_dir / dir_name
            if src_dir.exists() and src_dir.is_dir():
                shutil.move(str(src_dir), str(dest_dir))

# 屏蔽词汇        
banpath = data_dir / "ban"
banpath.mkdir(parents=True, exist_ok=True)
ban_str_path = data_dir / "ban" / "ban_str.ini"
ban_str_path.touch()
if not ban_str_path.stat().st_size:
    ban_str_path.write_text("",encoding='utf-8')

# 屏蔽用户    
banpath = data_dir / "ban" / "ban_user.json"
banpath.touch()
if not banpath.stat().st_size:
    banpath.write_text("{}")     


# 3.5白名单用户    
whitepath = data_dir / "white" 
whitepath.mkdir(parents=True, exist_ok=True)
whitepath = whitepath / "white_list.json" 
whitepath.touch()
if not whitepath.stat().st_size:
    whitepath.write_text(json.dumps({"version": 2, "sessions": []}))
    
# plus状态存储表
plusstatus = data_dir / "white" / "plus_status.json"
plusstatus.touch()
if not plusstatus.stat().st_size:
    tmp = {"status":True}
    plusstatus.write_text(json.dumps(tmp))
        
# 人设r18与归属扩展
personpath = data_dir / "person"
personpath.mkdir(parents=True, exist_ok=True)
personpath = data_dir / "person" / "personality_user.json"
personpath.touch()
if not personpath.stat().st_size:
    personpath.write_text("{}")        

# gpt会话存储
chatpath = data_dir / "conversation"
conversation_store_path = chatpath / "sessions.json"
