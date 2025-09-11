import eventlet
eventlet.monkey_patch()

import os
import glob
import datetime
from zoneinfo import ZoneInfo
from datetime import timezone
from dotenv import load_dotenv
import schedule
# from threading import Thread
from eventlet.green.threading import Thread
import time
import json
from google import genai
from google.genai import types
import binascii
import hashlib
from collections import defaultdict
import html
import requests
import utils.globals as globals
from utils.command_helper import parse_command
# import asyncio

from utils.helpers import add_chatlog_entry, add_to_prompt_history_safe

# from google.genai.types import Tool, GoogleSearch

import mysql.connector
from mysql.connector import pooling
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix

from flask import Flask, render_template, request, make_response, redirect, url_for, jsonify, send_file, session
from flask_socketio import SocketIO, disconnect

from utils.helpers import *

import magic


load_dotenv()


app = Flask(__name__)

app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "P%22%3BgzPe%5Ck%5D%3BgV-%7B%255TGSPYX%40OE7%5C.%40JsSuuoxHR%3A%3C1yBR%21N%28mm")

globals.socketio = SocketIO(app, async_mode="eventlet", async_handlers=True)
socketio = globals.socketio

app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=7)

app.config['CHAT_SECRET_KEY'] = os.getenv("CHAT_SECRET_KEY", None)
app.config['ADMIN_SECRET_KEY'] = os.getenv("ADMIN_SECRET_KEY", None)

app.config['GEMINI_API_KEY'] = os.getenv("GEMINI_API_KEY", None)

@app.after_request
def clear_old_insecure_cookies(response):
    old_cookies = ['acceptance_cookie', 'nickname', 'admin_acceptance_cookie']
    for cookie_name in old_cookies:
        if cookie_name in request.cookies:
            response.delete_cookie(cookie_name)
            print(f"Instructed browser to delete old cookie: {cookie_name}")
    return response

@app.after_request
def set_session_permanent(response):
    if session.permanent == True:
        return response
    
    session.permanent = True
    return response

@app.before_request
def check_if_kicked():
    """
    If a user's nickname is in the kicked_users set, clear their
    session to log them out, and then remove them from the set
    so they can log back in again.
    """
    nickname = session.get('nickname')
    if nickname and nickname in globals.kicked_users:
        globals.kicked_users.remove(nickname)
        
        session.pop('logged_in', None)
        session.pop('acceptance_token', None)
        
        print(f"Enforced kick for user {nickname}. Their session has been cleared.")
        
        return redirect(url_for('index'))

@app.before_request
def check_ban_status():
    """
    Runs before every request to check if the user's IP is in the
    database's BanList. If so, it stops the request and shows the banned page.
    """
    # We don't need to run this check on the banned page itself, or we'll get a redirect loop.
    if request.endpoint == 'banned_page' or request.path.startswith('/static/') or request.path.startswith('/admin') or request.path.startswith('/get-users'):
        return

    user_ip = get_real_ip(request)
    user_nickname = session.get('nickname')
    
    if f"{user_nickname}@{user_ip}" in globals.banned_ips_cache:
        expires_at_utc = globals.banned_ips_cache[f"{user_nickname}@{user_ip}"]
        if expires_at_utc is None or expires_at_utc > datetime.datetime.utcnow():
            if expires_at_utc:
                chicago_tz = ZoneInfo("America/Chicago")
                expires_at_utc_aware = expires_at_utc.replace(tzinfo=timezone.utc)
                expires_at_chicago = expires_at_utc_aware.astimezone(chicago_tz)
                expiry_str = expires_at_chicago.strftime("%Y-%m-%d %H:%M:%S %Z")
            else:
                expiry_str = "Permanent"
            
            return render_template('BANNED.html', expiry=expiry_str)

db_config = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
}

testing = False

db_pool = None
while db_pool is None:
    if testing:
        break
    try:
        print("Attempting to connect to the database...")
        db_pool = mysql.connector.pooling.MySQLConnectionPool(pool_name="chat_pool",
                                                              pool_size=10,
                                                              **db_config)
        print("✅ Successfully created database connection pool.")
        # If the connection is successful, the loop will exit.
    except mysql.connector.Error as err:
        print(f"⚠️ Database connection failed: {err}")
        print("Retrying in 3 seconds...")
        time.sleep(3)


ai_client = genai.Client(api_key=app.config['GEMINI_API_KEY'])

with open("ai_personality.txt", "r") as f:
    ai_personality = f.read()

# globals.current_log_file = globals.globals.current_log_file

# globals.connected_usernames = globals.globals.connected_usernames

# globals.typing_users = set()

# globals.ai_prompt_history = []

_image_buffers: dict[str, list[bytes]] = defaultdict(list)

def run_periodic_ban_sync():
    """A daemon thread that periodically re-syncs the ban list."""
    while True:
        eventlet.sleep(300) 
        sync_ban_list_from_db()

def clear_chatlogs():
    # global globals.current_log_file
    chatlogs_dir = 'chatlogs'

    if not os.path.exists(os.path.join(chatlogs_dir, "images")) or not os.path.exists(chatlogs_dir):
        os.makedirs(os.path.join(chatlogs_dir, "images"))

    for filename in os.listdir(chatlogs_dir):
        file_path = os.path.join(chatlogs_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    globals.current_log_file = os.path.join(chatlogs_dir, f"{today}.json")

    with open(globals.current_log_file, 'w') as f:
        json.dump([], f)

    print(f"New log file created: {globals.current_log_file}")


def schedule_task():
    schedule.every().day.at("00:00").do(clear_chatlogs)

    while True:
        schedule.run_pending()
        eventlet.sleep(60)

def load_recent_chat_context(num_messages=10):
    chat_context = ""
    if globals.current_log_file and os.path.exists(globals.current_log_file):
        with open(globals.current_log_file, "r") as f:
            chatlogs = json.load(f)
        # Filter out messages from 'KAC-Bot' and take the last num_messages messages
        # filtered_logs = [log for log in chatlogs if log['nickname'] != "KAC-Bot"]
        filtered_logs = chatlogs
        for log in filtered_logs[-num_messages:]:
            chat_context += f"{log['nickname']}: {log['message']}\n"
    return chat_context

def load_recent_chat_context_dict(num_messages=10):
    chat_context = []
    if globals.current_log_file and os.path.exists(globals.current_log_file):
        with open(globals.current_log_file, "r") as f:
            chatlogs = json.load(f)
        # Filter out messages from 'KAC-Bot' and take the last num_messages messages
        # filtered_logs = [log for log in chatlogs if log['nickname'] != "KAC-Bot"]
        filtered_logs = chatlogs
        for log in filtered_logs[-num_messages:]:
            chat_context.append(log)
    return chat_context

# def add_to_prompt_history_safe(role: str, text: str, image_part: bytes = None, type: str = "text"):
#     # global globals.ai_prompt_history

#     if type == "text":
#         if len(globals.ai_prompt_history) <= 20:
#             globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
#         else:
#             globals.ai_prompt_history.pop(0)
#             globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
#     elif type == "image":
#         if not image_part:
#             raise ValueError("image_part required when type='image'")
#         if len(globals.ai_prompt_history) <= 20:
#             globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part.from_text(text=text), image_part]))
#         else:
#             globals.ai_prompt_history.pop(0)
#             # globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
#             globals.ai_prompt_history.append(types.Content(role=role, parts=[types.Part.from_text(text=text), image_part]))


# def get_online_users() -> list[str]:
#     global globals.connected_usernames
#     # print("Getting online users")
#     # return globals.connected_usernames
#     return list(set(globals.connected_usernames))

# def initialize_ai_history_from_log(num_messages=20):
#     global globals.ai_prompt_history

#     if not globals.ai_prompt_history:
#         recent_logs = load_recent_chat_context_dict(num_messages=num_messages)
#         if not recent_logs:
#             return

#         globals.ai_prompt_history = [
#             types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part(text=log['message'] if log["type"] == "text" else f"{log.get('nickname')} sent an image.")])
#             for log in recent_logs
#         ]

def initialize_ai_history_from_log(num_messages=20):
    # global globals.ai_prompt_history

    if not globals.ai_prompt_history:
        recent_logs = load_recent_chat_context_dict(num_messages=num_messages)
        if not recent_logs:
            return

        globals.ai_prompt_history = []

        for log in recent_logs:
            if log["type"] == "text":
                globals.ai_prompt_history.append(
                    types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part(text=log['message'])])
                )
            elif log["type"] == "image":
                # image_id = log['id']  # Assuming 'id' is used for the image identifier
                # image_pattern = f'chatlogs/images/{image_id}.*'
                # matched_files = glob.glob(image_pattern)
                globals.ai_prompt_history.append(
                        types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part.from_text(text=f"{log.get('nickname')} sent an image.")])
                    )

                # print(full_image_pathc)
                # if matched_files:
                #     image_path = matched_files[0]
                #     print(image_path)
                #     with open(image_path, 'rb') as img_file:
                #         image_bytes = img_file.read()
                #         image_part = types.Part.from_uri(data=image_bytes, mime_type="image/*")
                #         globals.ai_prompt_history.append(
                #             types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part.from_text(text=f"{log.get('nickname')} sent an image."), image_part])
                #         )
                # else:
                #     globals.ai_prompt_history.append(
                #         types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part.from_text(text=f"{log.get('nickname')} sent an image. (Image missing)")]
                #     ))


def generate_response(message: str, user: str, enable_google_search: bool = True, image = False, image_id = None):
    global ai_client
    # global globals.ai_prompt_history

    google_search_tool = types.Tool(
       google_search = types.GoogleSearch(),
        )

    generate_content_config = types.GenerateContentConfig(
            system_instruction=ai_personality,
            tools=[google_search_tool] if enable_google_search else [],
            response_modalities=["TEXT"],
        )

    if image:
        # if not request_cookies:
        #     raise ValueError("request_cookies(dict) required when image=True")
        if image_id:
            image_path = f"http://0.0.0.0:5000/get_image/{image_id}"
            image_bytes = requests.get(image_path).content

            mime_type = magic.from_buffer(image_bytes, mime=True)

            image_file = types.Part.from_bytes(
                data=image_bytes, mime_type=mime_type
            )
            # print(f"Image file: {image_file}")
            # image_file = ai_client.files.upload(file="")
        else:
            raise ValueError("image_id required when image=True")
        tmp_history = globals.ai_prompt_history.copy()
        tmp_history.append([types.Part.from_text(text=f"{user}: {message}"), image_file])
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            config=generate_content_config,
            # contents=globals.ai_prompt_history,
            contents=tmp_history
        )
        add_to_prompt_history_safe("user", f"{user} sent an image and asked {message}", type="text")
        add_to_prompt_history_safe("model", response.text)
        return response.text

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        config=generate_content_config,
        contents=globals.ai_prompt_history,
    )

    # print(f"Done!\tResponse: {response.text}")

    # add_to_prompt_history_safe("model", response.text)

    for part in response.candidates[0].content.parts:
        if part.text is not None:
            # print(part.text)
            add_to_prompt_history_safe("model", response.text)
            return response.text

    # if response.text:
    #     return response.text
    # else:
    #     print(response)
    #     return "Failed to generate a response. If you are a developer please check the logs."

    # tool_call = response.candidates[0].content.parts[0].function_call

    # tool_call = None
    # for part in response.candidates[0].content.parts:
    #     if part.function_call:
    #         tool_call = part.function_call
    #         break # Found the first function call

    # if tool_call and tool_call.name == "get_online_users":
    #     result = get_online_users()
    #     print("Called get_online_users function, result:", result)
    #     function_response_part = types.Part.from_function_response(
    #         name=tool_call.name,
    #         response={"result": result},
    #     )
        
    #     globals.ai_prompt_history.append(types.Content(role="model", parts=[types.Part(function_call=tool_call)],))
    #     globals.ai_prompt_history.append(types.Content(role="function", parts=[function_response_part]))

    #     final_response = ai_client.models.generate_content(
    #         model="gemini-2.0-flash",
    #         # system_instruction=ai_personality,
    #         config=generate_content_config,
    #         contents=globals.ai_prompt_history,
    #     )
    #     return final_response.text
    # else:
    #     return response.text


def get_real_ip(request_obj):
    """
    Safely gets the real IP address from a request, prioritizing Cloudflare's
    header and then falling back to standard proxy headers.
    """

    # 1. Prioritize Cloudflare's header. This is the most reliable in your setup.
    #    The raw header name is 'Cf-Connecting-Ip', which Flask makes available
    #    in the headers dictionary.
    if 'Cf-Connecting-Ip' in request_obj.headers:
        return request_obj.headers.get('Cf-Connecting-Ip')

    # 2. Fallback to the standard 'X-Forwarded-For' header.
    #    This is for environments without Cloudflare.
    if 'X-Forwarded-For' in request_obj.headers:
        # The header can contain a list of IPs; the first one is the original client.
        return request_obj.headers.get('X-Forwarded-For').split(',')[0].strip()

    if 'HTTP_CF_CONNECTING_IP' in request_obj.environ:
        return request_obj.environ.get('HTTP_CF_CONNECTING_IP')

    # 2. Fallback to the standard 'X-Forwarded-For' header.
    #    Header 'X-Forwarded-For' becomes 'HTTP_X_FORWARDED_FOR'.
    if 'HTTP_X_FORWARDED_FOR' in request_obj.environ:
        # The header can contain a list of IPs; the first one is the original client.
        return request_obj.environ.get('HTTP_X_FORWARDED_FOR').split(',')[0].strip()
        
    # 3. Final fallback to the direct connection address.
    return request_obj.remote_addr

def sync_ban_list_from_db():
    if testing:
        return
    
    print("SYNCING BAN LIST: Reloading active bans from database into cache...")
    
    conn = None
    cursor = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Select all bans that are currently marked as active
        cursor.execute("SELECT target_ip, target_username, expires_at FROM BanList WHERE is_active = TRUE")
        active_bans = cursor.fetchall()
        
        temp_cache = {}
        for ban in active_bans:
            # Check if the ban has expired right here. No need to cache expired bans.
            expires_at = ban['expires_at']
            if expires_at is None or expires_at > datetime.datetime.utcnow():
                temp_cache[f"{ban['target_username']}@{ban['target_ip']}"] = expires_at

        # Atomically replace the old cache with the new one
        globals.banned_ips_cache = temp_cache
        
        print(f"SYNC COMPLETE: Loaded {len(globals.banned_ips_cache)} active bans into cache.")

    except mysql.connector.Error as err:
        print(f"DATABASE ERROR during ban list sync: {err}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@socketio.on("connect")
def handle_connect():
    user_ip = get_real_ip(request)
    nickname = session.get('nickname')
    sid = request.sid
    print(f"User connected: {nickname}")

    if session.get('logged_in') != True or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
        disconnect()
        return

    if nickname:
        globals.connected_usernames.add(nickname)
        globals.users_with_sid[nickname] = sid
        globals.users_with_IP[nickname] = user_ip

        if nickname in globals.users_to_jumpscare:
            socketio.emit('force_jumpscare', room=sid)

        if nickname in globals.users_to_crash:
            socketio.emit('force_crash', room=sid)

    # print(globals.users_with_sid)
    

@socketio.on("disconnect")
def handle_disconnect():
    nickname_to_remove = None
    for nickname, sid in globals.users_with_sid.items():
        if sid == request.sid:
            nickname_to_remove = nickname
            break

    if nickname_to_remove:
        print(f"User disconnected: {nickname_to_remove}")

        if nickname_to_remove in globals.typing_users:
            globals.typing_users.remove(nickname_to_remove)
            socketio.emit('typing_update', {'users': list(globals.typing_users)})
            
        if nickname_to_remove in globals.connected_usernames:
            globals.connected_usernames.remove(nickname_to_remove)

        globals.users_with_sid.pop(nickname_to_remove, None)
        globals.users_with_IP.pop(nickname_to_remove, None)
        
    
    # socketio.emit('user_disconnected', nickname)

@socketio.on("user_jumpscared")
def remove_from_jumpscare_list(data):
    nickname = session.get('nickname')
    if nickname in globals.users_to_jumpscare:
        globals.users_to_jumpscare.remove(nickname)

@socketio.on("user_crashed")
def remove_from_jumpscare_list(data):
    nickname = session.get('nickname')
    if nickname in globals.users_to_crash:
        globals.users_to_crash.remove(nickname)

@socketio.on("chat_message")
def handle_chat_message(data):
    print(globals.ai_prompt_history)
    message = data.get('message')
    nickname = session.get('nickname')
    timestamp = data.get('timestamp')
    print("Message received:", message, "from", nickname)

    if nickname not in globals.connected_usernames:
        globals.connected_usernames.add(nickname)
        globals.users_with_sid[nickname] = request.sid
        globals.users_with_IP[nickname] = get_real_ip(request)

    # print(f"Received message: {message} from {nickname} at {timestamp}")
    if message == "/clear":
        socketio.emit('clear_chat', room=request.sid)
        return

    if message.startswith("/highlight"):
        message = message.removeprefix("/highlight ")
        if message:
            socketio.emit('chat_message', { 'message': message, 'nickname': nickname, 'timestamp': timestamp, 'highlight': True })
            add_chatlog_entry(message, nickname, timestamp, globals.current_log_file, type="highlight")
            return

    socketio.emit('chat_message', { 'message': message, 'nickname': nickname, 'timestamp': timestamp })

    add_chatlog_entry(message, nickname, timestamp, globals.current_log_file)

    add_to_prompt_history_safe("user", f"{nickname}: {message}")

    if message.lower().startswith("!bot "):
        print(f"Asking bot: `{message}`")
        message = generate_response(message, user=nickname) 
        # message = 
        timestamp = datetime.datetime.now().isoformat()
        if message.startswith("/highlight "):
            message = message.removeprefix("/highlight ")
            socketio.emit('chat_message', { 'message': message, 'nickname': "KAC-Bot", 'timestamp': timestamp, 'highlight': True })
            add_chatlog_entry(message, "KAC-Bot", timestamp, globals.current_log_file, type="highlight")
        else:
            socketio.emit('chat_message', { 'message': message, 'nickname': "KAC-Bot", 'timestamp': timestamp })
            add_chatlog_entry(message, "KAC-Bot", timestamp, globals.current_log_file)
    elif message.startswith("/online"):
        online_users = get_online_users(globals.connected_usernames)
        socketio.emit('chat_message', { 'message': f"{nickname}, The users online are: {', '.join(online_user for online_user in online_users[:-1])}{', and' if len(online_users) > 1 else ''} {online_users[-1]}", 'nickname': "KAC-Bot", 'timestamp': timestamp, 'system': True })
        add_chatlog_entry(f"{nickname}, The users online are: {', '.join(online_user for online_user in online_users[:-1])}{', and' if len(online_users) > 1 else ''} {online_users[-1]}", "KAC-Bot", timestamp, globals.current_log_file, type="system")
    elif message.startswith("/help"):
        socketio.emit('chat_message', { 'message': html.escape(f"{nickname}, The commands are: !bot <message>, /clear, /online, /hightlight <message>, and /cloak"), 'nickname': "KAC-Bot", 'timestamp': timestamp, 'system': True })
        add_chatlog_entry(html.escape(f"{nickname}, The commands are: !bot <message>, /clear, /online, and /hightlight <message>"), "KAC-Bot", timestamp, globals.current_log_file, type="system")
    else:
        parse_command(message, nickname, timestamp)
    


@socketio.on('image_chunk')
def handle_image_chunk(data):
    if not session.get('logged_in') or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
        disconnect()
        return

    temp_id = data['id']
    chunk = data['chunk']
    _image_buffers[temp_id].append(chunk)

    if data['is_last']:
        data['metadata']['nickname'] = session.get('nickname')
        socketio.start_background_task(
            assemble_and_emit_image, temp_id, data['metadata']
        )

def assemble_and_emit_image(temp_id, metadata):
    # join all the chunks
    full_bytes = b''.join(_image_buffers.pop(temp_id, []))

    # dedupe / hash / write to disk
    image_hash = hashlib.sha256(full_bytes).hexdigest()
    images_dir = './chatlogs/images/'
    os.makedirs(images_dir, exist_ok=True)

    # see if it already exists
    existing_id = None
    for fn in os.listdir(images_dir):
        path = os.path.join(images_dir, fn)
        if os.path.isfile(path) and hashlib.sha256(open(path, 'rb').read()).hexdigest() == image_hash:
            existing_id = os.path.splitext(fn)[0]
            break

    final_id = existing_id or generate_random_string()
    if not existing_id:
        _, ext = os.path.splitext(metadata.get('name', ''))
        ext = ext.lower() or '.png'
        out_path = os.path.join(images_dir, f"{final_id}{ext}")
        with open(out_path, 'wb') as f:
            f.write(full_bytes)

    # emit the event once the image is saved
    socketio.emit('add_image', {
        'id': final_id,
        'nickname': metadata['nickname'],
        'timestamp': metadata['timestamp']
    })

    add_chatlog_entry(final_id, metadata['nickname'], metadata['timestamp'], globals.current_log_file, type="image")
    # add_to_prompt_history_safe("user", f"{metadata['nickname']}: sent an image.")
    if metadata["question"]:
        socketio.emit('chat_message', { 'message': "!bot "+metadata["question"], 'nickname': metadata['nickname'], 'timestamp': metadata['timestamp'] })
        add_chatlog_entry("!bot "+metadata["question"], metadata['nickname'], metadata['timestamp'], globals.current_log_file, type="text")
        response = generate_response(metadata["question"], user=metadata['nickname'], image=True, image_id=final_id)
        socketio.emit('chat_message', { 'message': response, 'nickname': "KAC-Bot", 'timestamp': datetime.datetime.now().isoformat() })
        add_chatlog_entry(response, "KAC-Bot", datetime.datetime.now().isoformat(), globals.current_log_file)
    else:
        add_to_prompt_history_safe("user", f"{metadata['nickname']}: sent an image.")


# @socketio.on('image_chunk')
# def handle_image_chunk(data):
#     temp_id = data['id']
#     chunk = data['chunk']  # this arrives as bytes
#     metadata = data['metadata']
#     is_last = data['is_last']
#     # print("recieved image chunk from: ", temp_id)
#     _image_buffers[temp_id].append(chunk)

#     if not is_last:
#         return

#     if is_last:
#         full_bytes = b''.join(_image_buffers.pop(temp_id))
#         # proceed to dedupe/hash/save like your existing handle_image
#         image_hash = hashlib.sha256(full_bytes).hexdigest()
#         image_hash = hashlib.sha256(full_bytes).hexdigest()
#         images_dir = './chatlogs/images/'
#         os.makedirs(images_dir, exist_ok=True)

#         existing_id = None
#         for fn in os.listdir(images_dir):
#             path = os.path.join(images_dir, fn)
#             if not os.path.isfile(path):
#                 continue
#             with open(path, 'rb') as f:
#                 if hashlib.sha256(f.read()).hexdigest() == image_hash:
#                     existing_id = os.path.splitext(fn)[0]
#                     break

#         if existing_id:
#             final_id = existing_id
#         else:
#             final_id = generate_random_string()
#             name = metadata.get('name', '')
#             _, ext = os.path.splitext(name)
#             ext = ext.lower()
#             out_path = os.path.join(images_dir, f"{final_id}{ext}")
#             with open(out_path, 'wb') as f:
#                 f.write(full_bytes)


#         socketio.emit('add_image', {
#           'id': final_id,
#           'nickname': metadata['nickname'],
#           'timestamp': metadata['timestamp']
#         })

#         add_chatlog_entry(final_id, metadata['nickname'], metadata['timestamp'], type="image")

@socketio.on('typing')
def handle_typing(data):
    nickname = session.get('nickname')
    if nickname:
        globals.typing_users.add(nickname)
        # Broadcast updated list
        socketio.emit('typing_update', {'users': list(globals.typing_users)})

@socketio.on('stop_typing')
def handle_stop_typing(data):
    nickname = session.get('nickname')
    if nickname and nickname in globals.typing_users:
        globals.typing_users.remove(nickname)
        socketio.emit('typing_update', {'users': list(globals.typing_users)})

@app.route('/')
def root_redirect():
    # if session.get('logged_in') and session.get('acceptance_token') == app.config['CHAT_SECRET_KEY'] and session.get('nickname'):
    #     return redirect(url_for('index'))
    
    return render_template('decoy.html')

@app.route('/student-portal')
def index():
    # acceptance_cookie = request.cookies.get('acceptance_cookie')
    # nickname_cookie = request.cookies.get('nickname')
    if session.get('logged_in') and session.get('acceptance_token') == app.config['CHAT_SECRET_KEY'] and session.get('nickname'):
        return render_template('chatroom.html')
    else:
        return render_template('login.html')
    # return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    
    if request.form.get("password") == app.config['CHAT_SECRET_KEY']:
        session['acceptance_token'] = request.form.get("password")
        session['logged_in'] = True

        if session.get('nickname') and session.get('nickname') != None:
            return redirect(url_for('index'))
        else:
            return render_template('nickname.html')
    else:
        return render_template('login.html', error="Incorrect password")
    # response = app.make_response(render_template('chatroom.html'))
    # response.set_cookie('acceptance_cookie', 'true')
    # return response

@app.route('/set-nickname', methods=['POST'])
def set_nickname():
    if session.get('logged_in') and session.get('acceptance_token') == app.config['CHAT_SECRET_KEY']:
        nickname = request.form.get("nickname")
        if nickname in globals.connected_usernames:
            return render_template('nickname.html', error="User with that name already in chat")
        
        session['nickname'] = nickname
        
        socketio.emit('user_connected', nickname)
        return redirect(url_for('index'))

        # response = make_response(redirect(url_for('index')))
        # response.set_cookie('nickname', request.form.get("nickname"))
        # socketio.emit('user_connected', request.form.get("nickname"))
        # return response
    else:
        return render_template('login.html')

@app.route('/get_chatlogs', methods=['GET'])
def get_chatlogs():
    # global globals.current_log_file
    if not session.get('logged_in') or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
            return "Unauthorized", 401
            
    if globals.current_log_file and os.path.exists(globals.current_log_file):
        with open(globals.current_log_file, 'r') as f:
            chatlogs = json.load(f)
        return jsonify(chatlogs)
    else:
        return jsonify([])

@app.route('/get_connected_users', methods=['GET'])
def get_connected_users():
    # global globals.connected_usernames
    if not session.get('logged_in') or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
            return "Unauthorized", 401

    return jsonify(get_connected_users(globals.connected_usernames))

@app.route('/get_image/<path:id>', methods=['GET'])
def get_image(id):
    # if not session.get('logged_in') or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
    #     return "Unauthorized", 401

    # Just grab the filename without extension
    filename = os.path.splitext(id)[0]  # strips extension
    _, ext = os.path.splitext(id)
    filepath = os.path.join("./chatlogs/images/", f"{filename}")

    # If you want to allow files *with* extension too
    # you can loop through allowed extensions and check if the file exists
    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp', '.psd', '.raw', '.svg', '.heif', '.jp2', '.jpx', '.jpm', '.j2k', '.mj2']:
        full_path = filepath + ext
        if os.path.exists(full_path):
            return send_file(full_path)  # or whatever you need to do

    return "File not found", 404

@app.route('/game-gamble-d6eca0', methods=['GET'])
def gamble():
    return render_template('gamble.html')

# --- ADMIN ---

# def admin_required(f):
#     """Checks for the admin cookie before allowing access to a route."""
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         admin_cookie = request.cookies.get('admin_acceptance_cookie')
#         if not admin_cookie or admin_cookie != app.config['ADMIN_SECRET_KEY']:
#             return jsonify({"message": "Authentication required"}), 401
#         return f(*args, **kwargs)
#     return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            if request.path.startswith('/get-users') or request.path.startswith('/admin/'):
                 return jsonify({"message": "Authentication required"}), 401
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_ban_expiry(duration_str):
    """Calculates an expiry datetime object from a string."""
    if duration_str == 'permanent':
        return None  # NULL in the database means permanent
    elif duration_str == '1d':
        return datetime.datetime.utcnow() + datetime.timedelta(days=1)
    elif duration_str == '7d':
        return datetime.datetime.utcnow() + datetime.timedelta(weeks=1)
    return None

@app.route('/crash', methods=["GET"])
def hell():
    return render_template('pain.html')

@app.route('/admin', methods=['GET'])
def admin_panel():
    if session.get('is_admin'):
        return render_template('admin/admin.html')
    else:
        return render_template('admin/admin-login.html')

@app.route('/admin-login', methods=['POST'])
def admin_login():
    if request.form.get("password") == app.config['ADMIN_SECRET_KEY']:
        session['is_admin'] = True
        response = make_response(redirect(url_for('admin_panel')))
        return response
    else:
        return render_template('admin/admin-login.html', error="Incorrect password")


@app.route('/get-users', methods=['GET'])
@admin_required
def get_users():
    print(get_real_ip(request))
    print(globals.users_with_IP)
    return jsonify(globals.users_with_IP)

@app.route("/admin/kick", methods=['POST'])
@admin_required
def kick_users():
    """
    Handles "kicking" users by sending a command to their browser
    to delete the auth cookie and then disconnects them.
    """
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400

    users_to_kick = data['users']
    kicked_count = 0
    print(f"--- KICK ACTION: Received request to log out {', '.join(users_to_kick)} ---")

    for user in users_to_kick:
        sid_to_kick = globals.users_with_sid.get(user)
        if sid_to_kick:
            globals.kicked_users.add(user)

            socketio.emit('force_logout', {}, room=sid_to_kick)            
            print(f"Sent force_logout command to {user} (SID: {sid_to_kick}).")
            disconnect(sid_to_kick, namespace='/')
            
            kicked_count += 1

    if kicked_count == 0:
        return jsonify({"message": "No active users found with the provided names."}), 404
        
    return jsonify({"message": f"Successfully sent logout command to {kicked_count} user(s)."}), 200

@app.route("/admin/ban", methods=['POST'])
@app.route("/admin/ip-ban", methods=['POST'])
@admin_required
def ip_ban_users():
    """Bans the IPs of selected users and writes them to the database."""
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400
        
    users_for_ip_ban = data['users']
    duration = data.get('duration', 'permanent')  # Default to permanent if not specified
    expiry_date = get_ban_expiry(duration)
    
    users_with_ips = [
        (user, globals.users_with_IP.get(user))
        for user in users_for_ip_ban
        if globals.users_with_IP.get(user)
    ]

    if not users_with_ips:
        return jsonify({"message": "Could not find IPs for any of the selected users."}), 404

    ips_to_ban = {ip for _, ip in users_with_ips}


    print(f"--- IP BAN ACTION: Banning IPs {', '.join(ips_to_ban)} for {duration} ---")

    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # This SQL statement will INSERT a new ban or UPDATE an existing one for the same IP.
        # It's a very efficient way to handle bans.
        sql = """
            INSERT INTO BanList (target_ip, target_username, expires_at, is_active)
            VALUES (%s, %s, %s, TRUE)
            ON DUPLICATE KEY UPDATE
                expires_at = VALUES(expires_at),
                is_active = TRUE
        """
        
        # Prepare data for bulk insertion/update
        ban_data = [(ip, user, expiry_date) for user, ip in users_with_ips]
        cursor.executemany(sql, ban_data)
        conn.commit()

        for user, ip in users_with_ips:
            globals.banned_ips_cache[f"{user}@{ip}"] = expiry_date

    except mysql.connector.Error as err:
        print(f"Database error during ban: {err}")
        return jsonify({"message": "A database error occurred."}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

    # After banning, kick all users from those IPs
    banned_users = {user for user, _ in users_with_ips}
    for user, user_ip in list(globals.users_with_IP.items()):
        if user in banned_users:
            sid_to_kick = globals.users_with_sid.get(user)
            if sid_to_kick:
                globals.kicked_users.add(user)
                socketio.emit('force_logout', {}, room=sid_to_kick)
                print(f"Sent force_logout command to {user} (SID: {sid_to_kick}).")
                disconnect(sid_to_kick, namespace='/')
    
    return jsonify({"message": f"Successfully banned and kicked users from IPs: {', '.join(ips_to_ban)}"}), 200

@app.route("/banned", methods=['GET'])
def banned_page():
    expiry = request.args.get('expires_at')
    return render_template('BANNED.html', expiry=expiry)

@app.route("/admin/reset-chat", methods=["POST"])
@admin_required
def reset_chat():
    """
    Clears the chat logs on disk, resets the AI's conversation memory,
    and instructs all connected clients to clear their chat windows.
    """
    try:

        clear_chatlogs()

        globals.ai_prompt_history = []
        print("In-memory AI prompt history has been cleared.")

        socketio.emit('chat_cleared', {})

        print("Sent 'chat_cleared' event to all clients.")
        return jsonify({"message": "Chat has been successfully reset."}), 200

    except Exception as e:
        # Log the error for debugging purposes.
        print(f"An error occurred while resetting the chat: {e}")
        # Return an error response to the admin panel.
        return jsonify({"message": "An error occurred during the chat reset."}), 500

@app.route("/admin/reload-all", methods=["POST"])
@admin_required
def reload_all():
    socketio.emit("force_reload", {})
    return jsonify({"message": "Everyone has been reloaded."}), 200

@app.route("/admin/cloak-all", methods=["POST"])
@admin_required
def cloak_all():
    socketio.emit("force_cloak", {})
    return jsonify({"message": "Everyone has been cloaked."}), 200

@app.route("/admin/jumpscare", methods=["POST"])
@admin_required
def jumpscare():
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400
        
    users_for_jumpscare = data['users']
    duration = data.get('duration', 'permanent')  # Default to permanent if not specified
    expiry_date = get_ban_expiry(duration)
    
    for user in users_for_jumpscare:
        globals.users_to_jumpscare.add(user)
        socketio.emit('force_jumpscare', {}, room=globals.users_with_sid.get(user))
    return jsonify({"message": "User(s) have been jumpscared."}), 200


@app.route("/admin/system-message", methods=["POST"])
@app.route("/admin/user-message", methods=["POST"])
@admin_required
def send_message_admin():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"message": "Invalid request. 'message' key is missing."}), 400

    message = data['message']
    is_system = False
    nickname = data.get('username', None)
    if not nickname:
        is_system = True
    timestamp = datetime.datetime.now().isoformat()

    if not is_system:
        socketio.emit('chat_message', { 'message': message, 'nickname': nickname, 'timestamp': timestamp, 'system': False })
        add_chatlog_entry(message, nickname, timestamp, globals.current_log_file)
    elif is_system:
        socketio.emit('system_message', { 'message': message, 'highlight': True })
        #add_chatlog_entry(message, "KAC-Bot", timestamp, globals.current_log_file, type="system" if is_system else "text")
    return jsonify({"message": "Message sent to chat."}), 200

@app.route("/admin/update-bans", methods=["POST"])
@admin_required
def update_bans():
    sync_ban_list_from_db()
    return jsonify({"message": "Ban list has been updated from the database."}), 200

@app.route("/admin/pinned-message", methods=["POST"])
@admin_required
def add_pinned_message():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"message": "Invalid request. 'message' key is missing."}), 400

    message = data['message']
    nickname = session.get('nickname', 'Admin')
    socketio.emit('add_pinned_msg', { 'message': message, 'nickname': nickname })
    return jsonify({"message": "Pinned message updated."}), 200

@app.route("/jumpscare/<path:filename>", methods=["GET"])
def jumpscare_file(filename):
    jumpscare_dir = os.path.join(app.root_path, "jumpscare")

    safe_path = os.path.abspath(os.path.join(jumpscare_dir, filename))
    if not safe_path.startswith(jumpscare_dir):
        abort(403)

    if not os.path.isfile(safe_path):
        abort(404)

    return send_file(safe_path), 200

@app.route("/admin/crash-users", methods=["POST"])
@admin_required
def crash_users():
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400

    users_to_crash = data['users']

    for user in users_to_crash:
        # print(f"Crashing {user}")
        globals.users_to_crash.add(user)
        socketio.emit('force_crash', {}, room=globals.users_with_sid.get(user))

    return jsonify({"message": "User(s) have been crashed."}), 200


def run_scheduled_task():
    scheduler_thread = Thread(target=schedule_task)
    scheduler_thread.daemon = True
    scheduler_thread.start()

def check_chatlog_status():
    # global globals.current_log_file
    chatlogs_dir = "chatlogs"
    today_file = os.path.join(chatlogs_dir, datetime.datetime.now().strftime('%Y-%m-%d') + ".json")

    if not os.path.exists(chatlogs_dir):
        os.makedirs(chatlogs_dir)

    if os.path.exists(today_file):
        globals.current_log_file = today_file
        print(f"Today log file exists. Using it: {globals.current_log_file}")
    else:
        clear_chatlogs()

    if globals.current_log_file is None:
        globals.current_log_file = today_file  # Ensure it is always set

with app.app_context():
    check_chatlog_status()
    run_scheduled_task()
    initialize_ai_history_from_log()

    sync_ban_list_from_db()
    ban_sync_thread = Thread(target=run_periodic_ban_sync)
    ban_sync_thread.daemon = True
    ban_sync_thread.start()


if __name__ == '__main__':
    # gunicorn.run(app)
    socketio.run(app)
