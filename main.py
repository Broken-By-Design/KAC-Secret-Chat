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

# import asyncio

from utils import bot_functions

# from google.genai.types import Tool, GoogleSearch

from flask import Flask, render_template, request, make_response, redirect, url_for, jsonify, send_file
from flask_socketio import SocketIO

from utils.helpers import *


load_dotenv()


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "P%22%3BgzPe%5Ck%5D%3BgV-%7B%255TGSPYX%40OE7%5C.%40JsSuuoxHR%3A%3C1yBR%21N%28mm")

socketio = SocketIO(app, async_mode="eventlet", async_handlers=True)

app.config['CHAT_SECRET_KEY'] = os.getenv("CHAT_SECRET_KEY", None)
app.config['GEMINI_API_KEY'] = os.getenv("GEMINI_API_KEY", None)

ai_client = genai.Client(api_key=app.config['GEMINI_API_KEY'])

with open("ai_personality.txt", "r") as f:
    ai_personality = f.read()

current_log_file = None

connected_usernames = set()

typing_users = set()

ai_prompt_history = []

_image_buffers: dict[str, list[bytes]] = defaultdict(list)


def clear_chatlogs():
    global current_log_file
    chatlogs_dir = 'chatlogs'

    if not os.path.exists(os.path.join(chatlogs_dir, "images")) or not os.path.exists(chatlogs_dir):
        os.makedirs(os.path.join(chatlogs_dir, "images"))

    for filename in os.listdir(chatlogs_dir):
        file_path = os.path.join(chatlogs_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    current_log_file = os.path.join(chatlogs_dir, f"{today}.json")

    with open(current_log_file, 'w') as f:
        json.dump([], f)

    print(f"New log file created: {current_log_file}")

def add_chatlog_entry(message, nickname, timestamp, type: str = "text"):
    global current_log_file

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

def schedule_task():
    schedule.every().day.at("00:00").do(clear_chatlogs)

    while True:
        schedule.run_pending()
        eventlet.sleep(60)

def load_recent_chat_context(num_messages=10):
    chat_context = ""
    if current_log_file and os.path.exists(current_log_file):
        with open(current_log_file, "r") as f:
            chatlogs = json.load(f)
        # Filter out messages from 'KAC-Bot' and take the last num_messages messages
        # filtered_logs = [log for log in chatlogs if log['nickname'] != "KAC-Bot"]
        filtered_logs = chatlogs
        for log in filtered_logs[-num_messages:]:
            chat_context += f"{log['nickname']}: {log['message']}\n"
    return chat_context

def load_recent_chat_context_dict(num_messages=10):
    chat_context = []
    if current_log_file and os.path.exists(current_log_file):
        with open(current_log_file, "r") as f:
            chatlogs = json.load(f)
        # Filter out messages from 'KAC-Bot' and take the last num_messages messages
        # filtered_logs = [log for log in chatlogs if log['nickname'] != "KAC-Bot"]
        filtered_logs = chatlogs
        for log in filtered_logs[-num_messages:]:
            chat_context.append(log)
    return chat_context

def add_to_prompt_history_safe(role: str, text: str, image_part: bytes = None, type: str = "text"):
    global ai_prompt_history

    if type == "text":
        if len(ai_prompt_history) <= 20:
            ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
        else:
            ai_prompt_history.pop(0)
            ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
    elif type == "image":
        if not image_part:
            raise ValueError("image_part required when type='image'")
        if len(ai_prompt_history) <= 20:
            ai_prompt_history.append(types.Content(role=role, parts=[types.Part.from_text(text=text), image_part]))
        else:
            ai_prompt_history.pop(0)
            # ai_prompt_history.append(types.Content(role=role, parts=[types.Part(text=text)]))
            ai_prompt_history.append(types.Content(role=role, parts=[types.Part.from_text(text=text), image_part]))


# def get_online_users() -> list[str]:
#     global connected_usernames
#     # print("Getting online users")
#     # return connected_usernames
#     return list(set(connected_usernames))

# def initialize_ai_history_from_log(num_messages=20):
#     global ai_prompt_history

#     if not ai_prompt_history:
#         recent_logs = load_recent_chat_context_dict(num_messages=num_messages)
#         if not recent_logs:
#             return

#         ai_prompt_history = [
#             types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part(text=log['message'] if log["type"] == "text" else f"{log.get('nickname')} sent an image.")])
#             for log in recent_logs
#         ]

def initialize_ai_history_from_log(num_messages=20):
    global ai_prompt_history

    if not ai_prompt_history:
        recent_logs = load_recent_chat_context_dict(num_messages=num_messages)
        if not recent_logs:
            return

        ai_prompt_history = []

        for log in recent_logs:
            if log["type"] == "text":
                ai_prompt_history.append(
                    types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part(text=log['message'])])
                )
            elif log["type"] == "image":
                # image_id = log['id']  # Assuming 'id' is used for the image identifier
                # image_pattern = f'chatlogs/images/{image_id}.*'
                # matched_files = glob.glob(image_pattern)
                ai_prompt_history.append(
                        types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part.from_text(text=f"{log.get('nickname')} sent an image.")])
                    )

                # print(full_image_pathc)
                # if matched_files:
                #     image_path = matched_files[0]
                #     print(image_path)
                #     with open(image_path, 'rb') as img_file:
                #         image_bytes = img_file.read()
                #         image_part = types.Part.from_uri(data=image_bytes, mime_type="image/*")
                #         ai_prompt_history.append(
                #             types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part.from_text(text=f"{log.get('nickname')} sent an image."), image_part])
                #         )
                # else:
                #     ai_prompt_history.append(
                #         types.Content(role="user" if log.get('nickname') != 'KAC-Bot' else "model", parts=[types.Part.from_text(text=f"{log.get('nickname')} sent an image. (Image missing)")]
                #     ))


def generate_response(message: str, user: str, enable_google_search: bool = True, image = False, image_id = None, request_cookies = None):
    global ai_client
    global ai_prompt_history

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
            image_file = types.Part.from_bytes(
                data=image_bytes, mime_type="image/*"
            )
            # print(f"Image file: {image_file}")
            # image_file = ai_client.files.upload(file="")
        else:
            raise ValueError("image_id required when image=True")
        tmp_history = ai_prompt_history.copy()
        tmp_history.append([types.Part.from_text(text=f"{user}: {message}"), image_file])
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash",
            config=generate_content_config,
            # contents=ai_prompt_history,
            contents=tmp_history
        )
        add_to_prompt_history_safe("user", f"{user} sent an image and asked {message}", type="text")
        add_to_prompt_history_safe("model", response.text)
        return response.text

    response = ai_client.models.generate_content(
        model="gemini-2.0-flash",
        config=generate_content_config,
        contents=ai_prompt_history,
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
        
    #     ai_prompt_history.append(types.Content(role="model", parts=[types.Part(function_call=tool_call)],))
    #     ai_prompt_history.append(types.Content(role="function", parts=[function_response_part]))

    #     final_response = ai_client.models.generate_content(
    #         model="gemini-2.0-flash",
    #         # system_instruction=ai_personality,
    #         config=generate_content_config,
    #         contents=ai_prompt_history,
    #     )
    #     return final_response.text
    # else:
    #     return response.text


@socketio.on("connect")
def handle_connect():
    nickname = request.args.get('nickname')
    print(f"User connected: {nickname}")

    # if nickname not in connected_usernames:
    #     socketio.emit('user_connected', nickname)
    if nickname:
        connected_usernames.add(nickname)
    

@socketio.on("disconnect")
def handle_disconnect():
    nickname = request.cookies.get('nickname')
    print(f"User disconnected: {nickname}")
    if nickname and nickname in connected_usernames:
        connected_usernames.remove(nickname)

    if nickname and nickname in typing_users:
        typing_users.remove(nickname)
        socketio.emit('typing_update', {'users': list(typing_users)})
    # socketio.emit('user_disconnected', nickname)

@socketio.on("chat_message")
def handle_chat_message(data):
    print(ai_prompt_history)
    message = data.get('message')
    nickname = data.get('nickname')
    timestamp = data.get('timestamp')
    
    # print(f"Received message: {message} from {nickname} at {timestamp}")
    if message == "/clear":
        socketio.emit('clear_chat', room=request.sid)
        return

    if message.startswith("/highlight"):
        message = message.removeprefix("/highlight ")
        if message:
            socketio.emit('chat_message', { 'message': message, 'nickname': nickname, 'timestamp': timestamp, 'highlight': True })
            add_chatlog_entry(message, nickname, timestamp, type="highlight")
            return

    socketio.emit('chat_message', { 'message': message, 'nickname': nickname, 'timestamp': timestamp })

    add_chatlog_entry(message, nickname, timestamp)

    add_to_prompt_history_safe("user", f"{nickname}: {message}")

    if message.startswith("!bot "):
        print(f"Asking bot: `{message}`")
        message = generate_response(message, user=nickname) 
        # message = 
        timestamp = datetime.datetime.now().isoformat()
        if message.startswith("/highlight "):
            message = message.removeprefix("/highlight ")
            socketio.emit('chat_message', { 'message': message, 'nickname': "KAC-Bot", 'timestamp': timestamp, 'highlight': True })
            add_chatlog_entry(message, "KAC-Bot", timestamp, type="highlight")
        else:
            socketio.emit('chat_message', { 'message': message, 'nickname': "KAC-Bot", 'timestamp': timestamp })
            add_chatlog_entry(message, "KAC-Bot", timestamp)

    if message.startswith("/online"):
        online_users = get_online_users(connected_usernames)
        socketio.emit('chat_message', { 'message': f"{nickname}, The users online are: {', '.join(online_user for online_user in online_users[:-1])}{' and' if len(online_users) > 1 else ''} {online_users[-1]}", 'nickname': "KAC-Bot", 'timestamp': timestamp, 'system': True })
        # eventlet.sleep(0.7)
        add_chatlog_entry(f"{nickname}, The users online are: {', '.join(online_user for online_user in online_users[:-1])}{' and' if len(online_users) > 1 else ''} {online_users[-1]}", "KAC-Bot", timestamp, type="system")
    
    if message.startswith("/help"):
        socketio.emit('chat_message', { 'message': html.escape(f"{nickname}, The commands are: !bot <message>, /clear, /online, /hightlight <message>, and /cloak"), 'nickname': "KAC-Bot", 'timestamp': timestamp, 'system': True })
        # eventlet.sleep(0.7)
        add_chatlog_entry(html.escape(f"{nickname}, The commands are: !bot <message>, /clear, /online, and /hightlight <message>"), "KAC-Bot", timestamp, type="system")
    
    


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

    add_chatlog_entry(final_id, metadata['nickname'], metadata['timestamp'], type="image")
    # add_to_prompt_history_safe("user", f"{metadata['nickname']}: sent an image.")
    if metadata["question"]:
        socketio.emit('chat_message', { 'message': "!bot "+metadata["question"], 'nickname': metadata['nickname'], 'timestamp': metadata['timestamp'] })
        add_chatlog_entry("!bot "+metadata["question"], metadata['nickname'], metadata['timestamp'], type="text")
        response = generate_response(metadata["question"], user=metadata['nickname'], image=True, image_id=final_id, request_cookies={'acceptance_cookie': acceptance_cookie})
        socketio.emit('chat_message', { 'message': response, 'nickname': "KAC-Bot", 'timestamp': datetime.datetime.now().isoformat() })
        add_chatlog_entry(response, "KAC-Bot", datetime.datetime.now().isoformat())
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
        typing_users.add(nickname)
        # Broadcast updated list
        socketio.emit('typing_update', {'users': list(typing_users)})

@socketio.on('stop_typing')
def handle_stop_typing(data):
    nickname = data.get('nickname')
    if nickname and nickname in typing_users:
        typing_users.remove(nickname)
        socketio.emit('typing_update', {'users': list(typing_users)})

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
        if request.form.get("nickname") in connected_usernames:
            return render_template('nickname.html', error="User with that name already in chat")
        response = make_response(redirect(url_for('index')))
        response.set_cookie('nickname', request.form.get("nickname"))
        socketio.emit('user_connected', request.form.get("nickname"))
        return response
    else:
        return render_template('login.html')

@app.route('/get_chatlogs', methods=['GET'])
def get_chatlogs():
    global current_log_file
    acceptance_cookie = request.cookies.get('acceptance_cookie')
    if (not acceptance_cookie) or (acceptance_cookie != app.config['CHAT_SECRET_KEY']):
            return "Unauthorized", 401
    if current_log_file and os.path.exists(current_log_file):
        with open(current_log_file, 'r') as f:
            chatlogs = json.load(f)
        return jsonify(chatlogs)
    else:
        return jsonify([])

@app.route('/get_connected_users', methods=['GET'])
def get_connected_users():
    global connected_usernames
    acceptance_cookie = request.cookies.get('acceptance_cookie')
    if (not acceptance_cookie) or (acceptance_cookie != app.config['CHAT_SECRET_KEY']):
            return "Unauthorized", 401
    return jsonify(get_connected_users(connected_usernames))

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

def run_scheduled_task():
    scheduler_thread = Thread(target=schedule_task)
    scheduler_thread.daemon = True
    scheduler_thread.start()

def check_chatlog_status():
    global current_log_file
    chatlogs_dir = "chatlogs"
    today_file = os.path.join(chatlogs_dir, datetime.datetime.now().strftime('%Y-%m-%d') + ".json")

    if not os.path.exists(chatlogs_dir):
        os.makedirs(chatlogs_dir)

    if os.path.exists(today_file):
        current_log_file = today_file
        print(f"Today log file exists. Using it: {current_log_file}")
    else:
        clear_chatlogs()

    if current_log_file is None:
        current_log_file = today_file  # Ensure it is always set

with app.app_context():
    check_chatlog_status()
    run_scheduled_task()
    initialize_ai_history_from_log()


if __name__ == '__main__':
    # gunicorn.run(app)
    socketio.run(app)
