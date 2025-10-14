import binascii
import os
import json
from google.genai import types

import utils.globals as globals

def generate_random_string():

    random_hex = binascii.hexlify(os.urandom(16)).decode('ascii')
    
    return f"{random_hex}"

def get_online_users(connected_usernames: list[str]) -> list[str]:
    return list(connected_usernames)


def add_chatlog_entry(message, nickname, timestamp, current_log_file, type: str = "text") -> None:
    chatlogs = []

    if os.path.exists(current_log_file):
        with open(current_log_file, 'r') as f:
            chatlogs = json.load(f)
    if type == "image":
        chatlogs.append({
            'id': message,
            'nickname': nickname,
            'timestamp': timestamp,
            'type': type
        })
    else:
        chatlogs.append({
            'message': message,
            'nickname': nickname,
            'timestamp': timestamp,
            'type': type
        })

    with open(current_log_file, 'w') as f:
        json.dump(chatlogs, f)


def add_to_prompt_history_safe(role: str, text: str, image_part: bytes = None, type: str = "text"):
    if type == "text":
        if len(globals.ai_prompt_history) <= 100:
            globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
        else:
            globals.ai_prompt_history.pop(0)
            globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
    elif type == "image":
        if not image_part:
            raise ValueError("image_part required when type='image'")
        if len(globals.ai_prompt_history) <= 100:
            globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part.from_text(text=text), image_part]))
        else:
            globals.ai_prompt_history.pop(0)
            # globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
            globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part.from_text(text=text), image_part]))