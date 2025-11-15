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
    """Add a chat log entry using append-only writes for better performance."""
    if type == "image":
        entry = {
            'id': message,
            'nickname': nickname,
            'timestamp': timestamp,
            'type': type
        }
    else:
        entry = {
            'message': message,
            'nickname': nickname,
            'timestamp': timestamp,
            'type': type
        }
    
    # Use append-only writes for better performance
    # Read the entire file only when it doesn't exist or is malformed
    try:
        if os.path.exists(current_log_file) and os.path.getsize(current_log_file) > 2:
            # File exists and has content beyond empty array
            # Read the file to append properly
            with open(current_log_file, 'r+') as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                if file_size > 2:  # More than just "[]"
                    # Move back to before the closing bracket
                    f.seek(file_size - 1)
                    f.truncate()
                    # Add comma and new entry
                    f.write(',' + json.dumps(entry) + ']')
                else:
                    # Empty array, just add the entry
                    f.seek(1)
                    f.truncate()
                    f.write(json.dumps(entry) + ']')
        else:
            # Create new file with first entry
            with open(current_log_file, 'w') as f:
                json.dump([entry], f)
    except (json.JSONDecodeError, IOError):
        # If file is corrupted, recreate it
        with open(current_log_file, 'w') as f:
            json.dump([entry], f)


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