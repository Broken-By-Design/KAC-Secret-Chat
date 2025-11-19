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

import utils.censor as censor

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

globals.socketio = SocketIO(app, async_mode="eventlet", async_handlers=True, ping_timeout=30, ping_interval=30)
socketio = globals.socketio

app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=7)

app.config['CHAT_SECRET_KEY'] = os.getenv("CHAT_SECRET_KEY", None)
app.config['ADMIN_SECRET_KEY'] = os.getenv("ADMIN_SECRET_KEY", None)

app.config['GEMINI_API_KEY'] = os.getenv("GEMINI_API_KEY", None)

video_chat_users = globals.video_chat_users

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
    except mysql.connector.Error as err:
        print(f"⚠️ Database connection failed: {err}")
        print("Retrying in 3 seconds...")
        time.sleep(3)


ai_client = genai.Client(api_key=app.config['GEMINI_API_KEY'])

with open("ai_personality.txt", "r") as f:
    ai_personality = f.read()

_image_buffers: dict[str, list[bytes]] = defaultdict(list)

def run_periodic_ban_sync():
    """A daemon thread that periodically re-syncs the ban list."""
    while True:
        eventlet.sleep(300) 
        sync_ban_list_from_db()

def clear_chatlogs():
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
        filtered_logs = chatlogs
        for log in filtered_logs[-num_messages:]:
            chat_context += f"{log['nickname']}: {log['message']}\n"
    return chat_context

def load_recent_chat_context_dict(num_messages=10):
    chat_context = []
    if globals.current_log_file and os.path.exists(globals.current_log_file):
        with open(globals.current_log_file, "r") as f:
            chatlogs = json.load(f)
        filtered_logs = chatlogs
        for log in filtered_logs[-num_messages:]:
            chat_context.append(log)
    return chat_context

def initialize_ai_history_from_log(num_messages=100):

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
                globals.ai_prompt_history.append(
                        types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part.from_text(text=f"{log.get('nickname')} sent an image.")])
                    )

def generate_response(message: str, user: str, enable_google_search: bool = True, image = False, image_id = None):
    global ai_client

    google_search_tool = types.Tool(
       google_search = types.GoogleSearch(),
        )

    generate_content_config = types.GenerateContentConfig(
            system_instruction=ai_personality,
            tools=[google_search_tool] if enable_google_search else [],
            response_modalities=["TEXT"],
        )

    if image:
        if image_id:
            image_path = f"http://0.0.0.0:5000/get_image/{image_id}"
            image_bytes = requests.get(image_path).content

            mime_type = magic.from_buffer(image_bytes, mime=True)

            image_file = types.Part.from_bytes(
                data=image_bytes, mime_type=mime_type
            )
        else:
            raise ValueError("image_id required when image=True")
        tmp_history = globals.ai_prompt_history.copy()
        tmp_history.append([types.Part.from_text(text=f"{user}: {message}"), image_file])
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            config=generate_content_config,
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

    for part in response.candidates[0].content.parts:
        if part.text is not None:
            # print(part.text)
            add_to_prompt_history_safe("model", response.text)
            return response.text


def get_real_ip(request_obj):
    if 'Cf-Connecting-Ip' in request_obj.headers:
        return request_obj.headers.get('Cf-Connecting-Ip')

    if 'X-Forwarded-For' in request_obj.headers:
        return request_obj.headers.get('X-Forwarded-For').split(',')[0].strip()

    if 'HTTP_CF_CONNECTING_IP' in request_obj.environ:
        return request_obj.environ.get('HTTP_CF_CONNECTING_IP')

    if 'HTTP_X_FORWARDED_FOR' in request_obj.environ:
        return request_obj.environ.get('HTTP_X_FORWARDED_FOR').split(',')[0].strip()
    
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
        
        cursor.execute("SELECT target_ip, target_username, expires_at FROM BanList WHERE is_active = TRUE")
        active_bans = cursor.fetchall()
        
        temp_cache = {}
        for ban in active_bans:
            expires_at = ban['expires_at']
            if expires_at is None or expires_at > datetime.datetime.utcnow():
                temp_cache[f"{ban['target_username']}@{ban['target_ip']}"] = expires_at

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
        # globals.users_with_sid[nickname] = sid
        if nickname not in globals.users_with_sid:
            globals.users_with_sid[nickname] = set()
        globals.users_with_sid[nickname].add(sid)

        globals.users_with_IP[nickname] = user_ip

        if nickname in globals.users_to_jumpscare:
            socketio.emit('force_jumpscare', room=sid)

        if nickname in globals.users_to_crash:
            socketio.emit('force_crash', room=sid)

    


@socketio.on("request_status")
def handle_request_status():
    nickname = session.get('nickname')
    sid = request.sid
    if nickname:
        is_muted = nickname in globals.muted_users
        socketio.emit('user_status', {'is_muted': is_muted}, room=sid)

@socketio.on("disconnect")
def handle_disconnect():
    nickname_to_remove = None

    sid = request.sid

    if sid in video_chat_users:
        nickname = video_chat_users[sid]
        print(f"VIDEO LOUNGE: {nickname} ({sid}) left.")
        del video_chat_users[sid]
        if sid in globals.screen_sharers:
            globals.screen_sharers.remove(sid)
            socketio.emit('screen_sharing_stopped', {'sid': sid})
        socketio.emit('user_left_lounge', sid)

    for nickname, sids in list(globals.users_with_sid.items()):
        
        if sid in sids:
            nickname_to_remove = nickname
            break

    if nickname_to_remove:
        print(f"User disconnected: {nickname_to_remove}")

        if nickname_to_remove in globals.users_with_sid:
            globals.users_with_sid[nickname_to_remove].discard(sid)
            
            # Only fully remove the user if they have no more active connections
            if not globals.users_with_sid[nickname_to_remove]:
                del globals.users_with_sid[nickname_to_remove]
                
                if nickname_to_remove in globals.typing_users:
                    globals.typing_users.remove(nickname_to_remove)
                    socketio.emit('typing_update', {'users': list(globals.typing_users)})
                    
                if nickname_to_remove in globals.connected_usernames:
                    globals.connected_usernames.remove(nickname_to_remove)

                globals.users_with_IP.pop(nickname_to_remove, None)


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

@socketio.on("request_missed_messages")
def handle_request_missed_messages(data):
    """
    Handles a client's request for messages sent after a certain time.
    """
    after_timestamp_str = data.get('after')
    if not after_timestamp_str:
        return

    try:
        after_timestamp = datetime.datetime.fromisoformat(after_timestamp_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        print(f"Invalid timestamp format received: {after_timestamp_str}")
        return

    missed_messages = []
    if globals.current_log_file and os.path.exists(globals.current_log_file):
        with open(globals.current_log_file, 'r') as f:
            try:
                chatlogs = json.load(f)
                for log in chatlogs:
                    log_timestamp_str = log.get('timestamp')
                    if not log_timestamp_str:
                        continue
                    
                    try:
                        log_timestamp = datetime.datetime.fromisoformat(log_timestamp_str.replace('Z', '+00:00'))
                        if log_timestamp > after_timestamp:
                            missed_messages.append(log)
                    except (ValueError, TypeError):
                        continue
            except json.JSONDecodeError:
                print(f"Could not decode JSON from {globals.current_log_file}")

    if missed_messages:
        missed_messages.sort(key=lambda x: x['timestamp'])
        socketio.emit('missed_messages', missed_messages, room=request.sid)


@socketio.on("private_message")
def handle_private_message(data):
    """
    Handles private messages between users.
    Expected data: { to: recipientNickname, message: text, timestamp }
    """
    message = data.get('message')
    recipient = data.get('to')
    timestamp = data.get('timestamp')
    sender = session.get('nickname')
    
    if not sender or sender not in globals.connected_usernames:
        print(f"Private message rejected: sender {sender} not connected")
        return
    
    if not recipient or recipient not in globals.connected_usernames:
        print(f"Private message rejected: recipient {recipient} not connected")
        socketio.emit('private_message_error', {
            'error': f'User {recipient} is not online'
        }, room=request.sid)
        return
    
    print(f"Private message from {sender} to {recipient}: {message}")
    
    add_chatlog_entry(message, sender, timestamp, globals.current_log_file, type="dm", recipient=recipient)
    
    sender_sids = globals.users_with_sid.get(sender, set())
    recipient_sids = globals.users_with_sid.get(recipient, set())
    dm_payload = {
        'message': message,
        'from': sender,
        'to': recipient,
        'timestamp': timestamp
    }
    
    for recipient_sid in recipient_sids:
        socketio.emit('private_message', dm_payload, room=recipient_sid)
    
    for sender_sid in sender_sids:
        socketio.emit('private_message', dm_payload, room=sender_sid)

@socketio.on("chat_message")
def handle_chat_message(data):
    message = data.get('message')
    nickname = session.get('nickname')
    timestamp = data.get('timestamp')
    print("Message received:", message, "from", nickname)

    if nickname in globals.users_to_censor:
        message = censor.censor_message(message)
    
    if nickname not in globals.connected_usernames:
        globals.connected_usernames.add(nickname)
        if nickname not in globals.users_with_sid:
            globals.users_with_sid[nickname] = set()
        globals.users_with_sid[nickname].add(request.sid)
        globals.users_with_IP[nickname] = get_real_ip(request)

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
    full_bytes = b''.join(_image_buffers.pop(temp_id, []))

    image_hash = hashlib.sha256(full_bytes).hexdigest()
    images_dir = './chatlogs/images/'
    os.makedirs(images_dir, exist_ok=True)

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

    socketio.emit('add_image', {
        'id': final_id,
        'nickname': metadata['nickname'],
        'timestamp': metadata['timestamp']
    })

    add_chatlog_entry(final_id, metadata['nickname'], metadata['timestamp'], globals.current_log_file, type="image")
    if metadata["question"]:
        socketio.emit('chat_message', { 'message': "!bot "+metadata["question"], 'nickname': metadata['nickname'], 'timestamp': metadata['timestamp'] })
        add_chatlog_entry("!bot "+metadata["question"], metadata['nickname'], metadata['timestamp'], globals.current_log_file, type="text")
        response = generate_response(metadata["question"], user=metadata['nickname'], image=True, image_id=final_id)
        socketio.emit('chat_message', { 'message': response, 'nickname': "KAC-Bot", 'timestamp': datetime.datetime.now().isoformat() })
        add_chatlog_entry(response, "KAC-Bot", datetime.datetime.now().isoformat(), globals.current_log_file)
    else:
        add_to_prompt_history_safe("user", f"{metadata['nickname']}: sent an image.")

@socketio.on('typing')
def handle_typing(data):
    nickname = session.get('nickname')
    if nickname:
        globals.typing_users.add(nickname)
        socketio.emit('typing_update', {'users': list(globals.typing_users)})

@socketio.on('stop_typing')
def handle_stop_typing(data):
    nickname = session.get('nickname')
    if nickname and nickname in globals.typing_users:
        globals.typing_users.remove(nickname)
        socketio.emit('typing_update', {'users': list(globals.typing_users)})

@socketio.on('join_video_lounge')
def handle_join_video_lounge():
    sid = request.sid
    nickname = session.get('nickname', 'Anonymous')

    old_sid = None
    for s, n in video_chat_users.items():
        if n == nickname:
            old_sid = s
            break
            
    if old_sid:
        print(f"VIDEO LOUNGE: Detected refresh for {nickname}. Cleaning up old SID: {old_sid}")

        del video_chat_users[old_sid]
        socketio.emit('user_left_lounge', old_sid)
    users_in_lounge = [{'sid': user_sid, 'nickname': user_nick} for user_sid, user_nick in video_chat_users.items()]
    socketio.emit('all_users', users_in_lounge, room=sid)
    
    video_chat_users[sid] = nickname
    
    socketio.emit('user_joined_lounge', {'sid': sid, 'nickname': nickname}, skip_sid=sid)
    print(f"VIDEO LOUNGE: {nickname} ({sid}) joined.")

    for sharer_sid in globals.screen_sharers:
        socketio.emit('screen_sharing_started', {'sid': sharer_sid}, room=sid)


@socketio.on('webrtc_offer')
def handle_webrtc_offer(data):
    target_sid = data['targetSid']
    offer = data['offer']
    socketio.emit('webrtc_offer', {
        'offer': offer,
        'senderSid': request.sid,
        'senderNickname': video_chat_users.get(request.sid, 'Anonymous')
    }, room=target_sid)

@socketio.on('webrtc_answer')
def handle_webrtc_answer(data):
    target_sid = data['targetSid']
    answer = data['answer']
    socketio.emit('webrtc_answer', {
        'answer': answer,
        'senderSid': request.sid,
        'senderNickname': video_chat_users.get(request.sid, 'Anonymous')
    }, room=target_sid)

@socketio.on('webrtc_candidate')
def handle_webrtc_candidate(data):
    target_sid = data['targetSid']
    candidate = data['candidate']
    socketio.emit('webrtc_candidate', {
        'candidate': candidate,
        'senderSid': request.sid
    }, room=target_sid)

@socketio.on('screen_sharing_started')
def handle_screen_sharing_started():
    sid = request.sid
    globals.screen_sharers.add(sid)
    socketio.emit('screen_sharing_started', {'sid': sid}, skip_sid=sid)

@socketio.on('screen_sharing_stopped')
def handle_screen_sharing_stopped():
    sid = request.sid
    globals.screen_sharers.remove(sid)
    socketio.emit('screen_sharing_stopped', {'sid': sid}, skip_sid=sid)

@app.route('/')
def root_redirect():
    
    return render_template('decoy.html')

@app.route('/tests')
def testing_pages():
    return render_template('tests/tests.html')

@app.route('/tutors')
def video_lounge():
    if not session.get('logged_in') or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
        return redirect(url_for('index'))
    
    nickname = session.get('nickname', 'Guest')
    return render_template('video_chat.html', nickname=nickname)

@app.route('/student-portal')
def index():
    if session.get('logged_in') and session.get('acceptance_token') == app.config['CHAT_SECRET_KEY'] and session.get('nickname'):
        return render_template('chatroom.html', nickname=session.get('nickname'))
    else:
        return render_template('login.html')

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

@app.route('/set-nickname', methods=['POST'])
def set_nickname():
    if session.get('logged_in') and session.get('acceptance_token') == app.config['CHAT_SECRET_KEY']:
        nickname = request.form.get("nickname")
        if nickname in globals.connected_usernames:
            return render_template('nickname.html', error="User with that name already in chat")
        
        session['nickname'] = nickname
        
        socketio.emit('user_connected', nickname)
        return redirect(url_for('index'))

    else:
        return render_template('login.html')

@app.route('/get_chatlogs', methods=['GET'])
def get_chatlogs():
    if not session.get('logged_in') or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
            return "Unauthorized", 401
            
    if globals.current_log_file and os.path.exists(globals.current_log_file):
        with open(globals.current_log_file, 'r') as f:
            chatlogs = json.load(f)
        public_chatlogs = [log for log in chatlogs if log.get('type') != 'dm']
        return jsonify(public_chatlogs)
    else:
        return jsonify([])

@app.route('/get_dm_logs', methods=['GET'])
def get_dm_logs():
    """
    Retrieves DM history between the logged-in user and another user.
    Query parameter: with=<other_username>
    """
    if not session.get('logged_in') or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
        return "Unauthorized", 401
    
    current_user = session.get('nickname')
    other_user = request.args.get('with')
    
    if not current_user or not other_user:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    dm_logs = []
    
    if globals.current_log_file and os.path.exists(globals.current_log_file):
        with open(globals.current_log_file, 'r') as f:
            all_chatlogs = json.load(f)
        
        for log in all_chatlogs:
            if log.get('type') == 'dm':
                if (log.get('nickname') == current_user and log.get('recipient') == other_user) or \
                   (log.get('nickname') == other_user and log.get('recipient') == current_user):
                    dm_logs.append(log)
    
    return jsonify(dm_logs)

@app.route('/get_connected_users', methods=['GET'])
def get_connected_users_route():
    if not session.get('logged_in') or session.get('acceptance_token') != app.config['CHAT_SECRET_KEY']:
            return "Unauthorized", 401

    return jsonify(get_online_users(globals.connected_usernames))

@app.route('/get_image/<path:id>', methods=['GET'])
def get_image(id):
    filename = os.path.splitext(id)[0]  # strips extension
    _, ext = os.path.splitext(id)
    filepath = os.path.join("./chatlogs/images/", f"{filename}")

    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp', '.psd', '.raw', '.svg', '.heif', '.jp2', '.jpx', '.jpm', '.j2k', '.mj2']:
        full_path = filepath + ext
        if os.path.exists(full_path):
            return send_file(full_path)

    return "File not found", 404

@app.route('/game-gamble-d6eca0', methods=['GET'])
def gamble():
    return render_template('gamble.html')


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
        return None
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
        sids_to_kick = globals.users_with_sid.get(user, set())
        if sids_to_kick:
            globals.kicked_users.add(user)

            for sid_to_kick in list(sids_to_kick):
                socketio.emit('force_logout', {}, room=sid_to_kick)            
                print(f"Sent force_logout command to {user} (SID: {sid_to_kick}).")
                disconnect(sid_to_kick, namespace='/')
            
            kicked_count += 1

    if kicked_count == 0:
        return jsonify({"message": "No active users found with the provided names."}), 404
        
    return jsonify({"message": f"Successfully sent logout command to {kicked_count} user(s)."}), 200

@app.route("/admin/mute", methods=['POST'])
@admin_required
def mute_users():
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400

    users_to_kick = data['users']

    for user in users_to_kick:
        sids_to_kick = globals.users_with_sid.get(user)
        if sids_to_kick:
            globals.muted_users.add(user)
            
            for sid_to_kick in list(sids_to_kick):
                socketio.emit('force_mute', {}, room=sid_to_kick)            
                print(f"Sent force_mute command to {user} (SID: {sid_to_kick}).")
        
    return jsonify({"message": f"Successfully sent mute command"}), 200

@app.route("/admin/unmute", methods=['POST'])
@admin_required
def unmute_users():
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400

    users_to_kick = data['users']

    for user in users_to_kick:
        sids_to_kick = globals.users_with_sid.get(user)
        if sids_to_kick:
            globals.muted_users.remove(user)

            for sid_to_kick in list(sids_to_kick):
                socketio.emit('force_unmute', {}, room=sid_to_kick)            
                print(f"Sent force_unmute command to {user} (SID: {sid_to_kick}).")
        
    return jsonify({"message": f"Successfully sent unmute command"}), 200


@app.route("/admin/ban", methods=['POST'])
@app.route("/admin/ip-ban", methods=['POST'])
@admin_required
def ip_ban_users():
    """Bans the IPs of selected users and writes them to the database."""
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400
        
    users_for_ip_ban = data['users']
    duration = data.get('duration', 'permanent')
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
        
        sql = """
            INSERT INTO BanList (target_ip, target_username, expires_at, is_active)
            VALUES (%s, %s, %s, TRUE)
            ON DUPLICATE KEY UPDATE
                expires_at = VALUES(expires_at),
                is_active = TRUE
        """
        
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

    banned_users = {user for user, _ in users_with_ips}
    for user, user_ip in list(globals.users_with_IP.items()):
        if user in banned_users:
            sids_to_kick = globals.users_with_sid.get(user)
            if sids_to_kick:
                for sid_to_kick in list(sids_to_kick):
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
        print(f"An error occurred while resetting the chat: {e}")
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
    duration = data.get('duration', 'permanent')
    expiry_date = get_ban_expiry(duration)
    
    for user in users_for_jumpscare:
        globals.users_to_jumpscare.add(user)
        for sid in globals.users_with_sid.get(user, set()):
            socketio.emit('force_jumpscare', {}, room=sid)
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
    return jsonify({"message": "Message sent to chat."}), 200

@app.route("/admin/update-bans", methods=["POST"])
@admin_required
def update_bans():
    sync_ban_list_from_db()
    return jsonify({"message": "Ban list has been updated from the database."}), 200

@app.route("/admin/reset-bot-memory", methods=["POST"])
@admin_required
def reset_bot_memory():
    """
    Resets the AI's conversation memory.
    """
    try:
        globals.ai_prompt_history = []
        print("In-memory AI prompt history has been cleared.")
        return jsonify({"message": "Bot's memory has been successfully reset."}), 200
    except Exception as e:
        print(f"An error occurred while resetting the bot's memory: {e}")
        return jsonify({"message": "An error occurred during the bot's memory reset."}), 500

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
        for sid in globals.users_with_sid.get(user, set()):
            socketio.emit('force_crash', {}, room=sid)

    return jsonify({"message": "User(s) have been crashed."}), 200

@app.route("/admin/censor-users", methods=["POST"])
@admin_required
def censor_users():
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400

    users_to_censor = data['users']

    for user in users_to_censor:
        # print(f"Crashing {user}")
        globals.users_to_censor.add(user)
        # for sid in globals.users_with_sid.get(user, set()):
        #     socketio.emit('force_crash', {}, room=sid)

    return jsonify({"message": "User(s) have been crashed."}), 200

@app.route("/admin/uncensor-users", methods=["POST"])
@admin_required
def uncensor_users():
    data = request.get_json()
    if not data or 'users' not in data:
        return jsonify({"message": "Invalid request. 'users' key is missing."}), 400

    users_to_censor = data['users']

    for user in users_to_censor:
        # print(f"Crashing {user}")
        globals.users_to_censor.remove(user)
        # for sid in globals.users_with_sid.get(user, set()):
        #     socketio.emit('force_crash', {}, room=sid)

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
