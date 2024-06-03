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
dirs_to_move = ["group", "private", "ban", "white", "person", "cdk", "conversation", "mdstatus.json"]

# 兼容性更新
if os.name == 'nt':
    incorrect_dir = Path(os.getcwd())
    if incorrect_dir.exists() and incorrect_dir.is_dir():
        for dir_name in dirs_to_move:
            src_dir = incorrect_dir / dir_name
            dest_dir = data_dir / dir_name
            if src_dir.exists() and src_dir.is_dir():
                shutil.move(str(src_dir), str(dest_dir))

# 群聊会话
grouppath = data_dir / "group"
grouppath.mkdir(parents=True, exist_ok=True)
grouppath = data_dir / "group" / "group.json"
grouppath.touch()
if not grouppath.stat().st_size:
    grouppath.write_text("{}") 
# 私聊会话    
privatepath = data_dir / "private"
privatepath.mkdir(parents=True, exist_ok=True)
privatepath = data_dir / "private" / "private.json"
privatepath.touch()
if not privatepath.stat().st_size:
    privatepath.write_text("{}")
# 屏蔽词汇        
banpath = data_dir / "ban"
banpath.mkdir(parents=True, exist_ok=True)
ban_str_path = data_dir / "ban" / "ban_str.ini"
ban_str_path.touch()

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
    tmp = {'group':[],'private':[],'qqgroup':[],'qqguild':[]}
    whitepath.write_text(json.dumps(tmp)) 
    
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

# cdk
cdkpath = data_dir / "cdk"
cdkpath.mkdir(parents=True, exist_ok=True)
cdklistpath = cdkpath / "cdklist.json"
cdklistpath.touch()
if not cdklistpath.stat().st_size:
    cdklistpath.write_text("{}")  
    
cdksource = cdkpath / "cdksource.json"
cdksource.touch()
if not cdksource.stat().st_size:
    cdksource.write_text("{}")   
    
# md状态存储
mdstatus = data_dir / "mdstatus.json"
mdstatus.touch()
if not mdstatus.stat().st_size:
    tmp = {"group":[],"private":[]}
    mdstatus.write_text(json.dumps(tmp))  
