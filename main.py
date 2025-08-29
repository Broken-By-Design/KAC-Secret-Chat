import eventlet
eventlet.monkey_patch()


import os
import glob
import datetime
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

from flask import Flask, render_template, request, make_response, redirect, url_for, jsonify, send_file
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

app.config['CHAT_SECRET_KEY'] = os.getenv("CHAT_SECRET_KEY", None)
app.config['ADMIN_SECRET_KEY'] = os.getenv("ADMIN_SECRET_KEY", None)

app.config['GEMINI_API_KEY'] = os.getenv("GEMINI_API_KEY", None)

db_config = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
}

db_pool = None
while db_pool is None:
    try:
        print("Attempting to connect to the database...")
        db_pool = mysql.connector.pooling.MySQLConnectionPool(pool_name="chat_pool",
                                                              pool_size=10,
                                                              **db_config)
        print("✅ Successfully created database connection pool.")
        # If the connection is successful, the loop will exit.
    except mysql.connector.Error as err:
        print(f"⚠️ Database connection failed: {err}")
        print("Retrying in 5 seconds...")
        time.sleep(5)


ai_client = genai.Client(api_key=app.config['GEMINI_API_KEY'])

with open("ai_personality.txt", "r") as f:
    ai_personality = f.read()

# globals.current_log_file = globals.globals.current_log_file

# globals.connected_usernames = globals.globals.connected_usernames

# globals.typing_users = set()

# globals.ai_prompt_history = []

_image_buffers: dict[str, list[bytes]] = defaultdict(list)


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


def generate_response(message: str, user: str, enable_google_search: bool = True, image = False, image_id = None, request_cookies = None):
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
        if not request_cookies:
            raise ValueError("request_cookies(dict) required when image=True")
        if image_id:
            image_path = f"http://0.0.0.0:5000/get_image/{image_id}"
            image_bytes = requests.get(image_path, cookies=request_cookies).content

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

@socketio.on("connect")
def handle_connect():
    user_ip = get_real_ip(request)
    nickname = request.args.get('nickname')
    sid = request.sid
    print(f"User connected: {nickname}")

    conn = None
    cursor = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # --- LOGICAL FIX: Query by IP address only ---
        cursor.execute(
            "SELECT target_username, expires_at FROM BanList WHERE target_ip = %s AND target_username = %s AND is_active = TRUE", (user_ip, nickname)
        )
        ban_record = cursor.fetchone()
        
        if ban_record:
            expires_at = ban_record['expires_at']
            
            # Check if the ban is active
            if expires_at is None or expires_at > datetime.datetime.utcnow():
                banned_username = ban_record['target_username']
                print(f"Connection rejected for banned user '{banned_username}' at IP: {user_ip}")

                # --- CRITICAL BUG FIX: Handle None for permanent bans ---
                expiry_str = None
                if expires_at:
                    expiry_str = expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                
                # Now we can safely emit the event
                socketio.emit('display_banned', {'expires_at': expiry_str}, room=sid, callback=lambda: disconnect(sid))

                return

            else:
                # The ban has expired, so we can deactivate it
                print(f"Deactivating expired ban for IP: {user_ip}")
                cursor.execute("UPDATE BanList SET is_active = FALSE WHERE target_ip = %s", (user_ip,))
                conn.commit()

    except mysql.connector.Error as err:
        print(f"Database error during connection check: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # if nickname not in globals.connected_usernames:
    #     socketio.emit('user_connected', nickname)
    if nickname:
        globals.connected_usernames.add(nickname)
        globals.users_with_sid[nickname] = sid
        globals.users_with_IP[nickname] = user_ip

        if nickname in globals.users_to_jumpscare:
            socketio.emit('force_jumpscare', room=sid)


    # print(globals.users_with_sid)
    

@socketio.on("disconnect")
def handle_disconnect():
    nickname = request.cookies.get('nickname')
    print(f"User disconnected: {nickname}")

    if nickname:
        if nickname in globals.typing_users:
            globals.typing_users.remove(nickname)
            socketio.emit('typing_update', {'users': list(globals.typing_users)})
            
        if nickname in globals.connected_usernames:
            globals.connected_usernames.remove(nickname)

        if nickname in globals.users_with_sid:
            globals.users_with_sid.pop(nickname)
        
        if nickname in globals.users_with_IP:
            globals.users_with_IP.pop(nickname)
        
    
    # socketio.emit('user_disconnected', nickname)

@socketio.on("user_jumpscared")
def remove_from_jumpscare_list(data):
    nickname = data.get('nickname')
    if nickname in globals.users_to_jumpscare:
        globals.users_to_jumpscare.remove(nickname)

@socketio.on("chat_message")
def handle_chat_message(data):
    print(globals.ai_prompt_history)
    message = data.get('message')
    nickname = data.get('nickname')
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
    # Quickly stash the chunk and return
    temp_id = data['id']
    chunk = data['chunk']
    _image_buffers[temp_id].append(chunk)

    if data['is_last']:
        acceptance_cookie = request.cookies.get('acceptance_cookie')
        socketio.start_background_task(
            assemble_and_emit_image, temp_id, data['metadata'], acceptance_cookie
        )

def assemble_and_emit_image(temp_id, metadata, acceptance_cookie):
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
        response = generate_response(metadata["question"], user=metadata['nickname'], image=True, image_id=final_id, request_cookies={'acceptance_cookie': acceptance_cookie})
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
    nickname = data.get('nickname')
    if nickname:
        globals.typing_users.add(nickname)
        # Broadcast updated list
        socketio.emit('typing_update', {'users': list(globals.typing_users)})

@socketio.on('stop_typing')
def handle_stop_typing(data):
    nickname = data.get('nickname')
    if nickname and nickname in globals.typing_users:
        globals.typing_users.remove(nickname)
        socketio.emit('typing_update', {'users': list(globals.typing_users)})

@app.route('/')
def index():
    acceptance_cookie = request.cookies.get('acceptance_cookie')
    nickname_cookie = request.cookies.get('nickname')
    if (
        (acceptance_cookie) and (acceptance_cookie == app.config['CHAT_SECRET_KEY']) and
        (nickname_cookie)
        ):
        return render_template('chatroom.html')
    else:
        return render_template('login.html')
    # return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    
    if request.form.get("password") == app.config['CHAT_SECRET_KEY']:
        if request.cookies.get("nickname"):
            response = make_response(redirect(url_for('index')))
        else:
            response = make_response(render_template('nickname.html'))
        response.set_cookie('acceptance_cookie', request.form.get("password"), max_age=datetime.timedelta(weeks=1))
        return response
    else:
        return render_template('login.html', error="Incorrect password")
    # response = app.make_response(render_template('chatroom.html'))
    # response.set_cookie('acceptance_cookie', 'true')
    # return response

@app.route('/set-nickname', methods=['POST'])
def set_nickname():
    acceptance_cookie = request.cookies.get('acceptance_cookie')
    if (acceptance_cookie) and (acceptance_cookie == app.config['CHAT_SECRET_KEY']):
        if request.form.get("nickname") in globals.connected_usernames:
            return render_template('nickname.html', error="User with that name already in chat")
        response = make_response(redirect(url_for('index')))
        response.set_cookie('nickname', request.form.get("nickname"))
        socketio.emit('user_connected', request.form.get("nickname"))
        return response
    else:
        return render_template('login.html')

@app.route('/get_chatlogs', methods=['GET'])
def get_chatlogs():
    # global globals.current_log_file
    acceptance_cookie = request.cookies.get('acceptance_cookie')
    if (not acceptance_cookie) or (acceptance_cookie != app.config['CHAT_SECRET_KEY']):
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
    acceptance_cookie = request.cookies.get('acceptance_cookie')
    if (not acceptance_cookie) or (acceptance_cookie != app.config['CHAT_SECRET_KEY']):
            return "Unauthorized", 401
    return jsonify(get_connected_users(globals.connected_usernames))

@app.route('/get_image/<path:id>', methods=['GET'])
def get_image(id):
    acceptance_cookie = request.cookies.get('acceptance_cookie')
    if (not acceptance_cookie) or (acceptance_cookie != app.config['CHAT_SECRET_KEY']):
        return "Unauthorized", 401

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

def admin_required(f):
    """Checks for the admin cookie before allowing access to a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_cookie = request.cookies.get('admin_acceptance_cookie')
        if not admin_cookie or admin_cookie != app.config['ADMIN_SECRET_KEY']:
            return jsonify({"message": "Authentication required"}), 401
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

@app.route('/admin', methods=['GET'])
def admin_panel():
    acceptance_cookie = request.cookies.get('admin_acceptance_cookie')
    if ((acceptance_cookie) and (acceptance_cookie == app.config['ADMIN_SECRET_KEY'])):
        return render_template('admin/admin.html')
    else:
        return render_template('admin/admin-login.html')

@app.route('/admin-login', methods=['POST'])
def admin_login():
    if request.form.get("password") == app.config['ADMIN_SECRET_KEY']:
        response = make_response(redirect(url_for('admin_panel')))
        response.set_cookie('admin_acceptance_cookie', request.form.get("password"), max_age=datetime.timedelta(days=1))
        return response
    else:
        return render_template('admin/admin-login.html', error="Incorrect password")


@app.route('/get-users', methods=['GET'])
@admin_required
def get_users():
    print(get_real_ip(request))
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

    except mysql.connector.Error as err:
        print(f"Database error during ban: {err}")
        return jsonify({"message": "A database error occurred."}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

    # After banning, kick all users from those IPs
    for user, user_ip in list(globals.users_with_IP.items()):
        if user in [user for user, _ in users_with_ips]:
            sid_to_kick = globals.users_with_sid.get(user)
            if sid_to_kick:
                socketio.emit('force_logout', {}, room=sid_to_kick)
                print(f"Sent force_logout command to {user} (SID: {sid_to_kick}).")
                disconnect(sid_to_kick, namespace='/')
    
    return jsonify({"message": f"Successfully banned and kicked users from IPs: {', '.join(ips_to_ban)}"}), 200

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
        add_chatlog_entry(message, nickname, timestamp, globals.current_log_file, type="system" if is_system else "text")
    elif is_system:
        socketio.emit('system_message', { 'message': message })
        #add_chatlog_entry(message, "KAC-Bot", timestamp, globals.current_log_file, type="system" if is_system else "text")
    return jsonify({"message": "Message sent to chat."}), 200

@app.route("/jumpscare/<path:filename>", methods=["GET"])
def jumpscare_file(filename):
    jumpscare_dir = os.path.join(app.root_path, "jumpscare")

    safe_path = os.path.abspath(os.path.join(jumpscare_dir, filename))
    if not safe_path.startswith(jumpscare_dir):
        abort(403)

    if not os.path.isfile(safe_path):
        abort(404)

    return send_file(safe_path), 200

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


if __name__ == '__main__':
    # gunicorn.run(app)
    socketio.run(app)
