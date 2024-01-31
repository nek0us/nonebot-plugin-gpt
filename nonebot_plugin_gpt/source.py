import json
import os
from pathlib import Path
from nonebot import require
require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

nb_project = os.getcwd().rsplit("/")[-1]

plugin_data_dir: Path = store.get_data_dir("nonebot_plugin_gpt")
data_dir = plugin_data_dir / nb_project

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

# 白名单用户    
whitepath = data_dir / "white" 
whitepath.mkdir(parents=True, exist_ok=True)
whitepath = whitepath / "white_list.json" 
whitepath.touch()
if not whitepath.stat().st_size:
    tmp = {'group':[],'private':[],'qqgroup':[],'qqguild':[]}
    whitepath.write_text(json.dumps(tmp)) 
        
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