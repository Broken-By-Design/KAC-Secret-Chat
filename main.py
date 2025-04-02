import eventlet
eventlet.monkey_patch(os=False)


import os
import datetime
from dotenv import load_dotenv
import schedule
from threading import Thread
import time
import json
from google import genai
from google.genai import types
import eventlet
# from google.genai.types import Tool, GoogleSearch

from flask import Flask, render_template, request, make_response, redirect, url_for, jsonify
from flask_socketio import SocketIO


load_dotenv()


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "P%22%3BgzPe%5Ck%5D%3BgV-%7B%255TGSPYX%40OE7%5C.%40JsSuuoxHR%3A%3C1yBR%21N%28mm")

socketio = SocketIO(app, async_mode="eventlet")

app.config['CHAT_SECRET_KEY'] = os.getenv("CHAT_SECRET_KEY", None)
app.config['GEMINI_API_KEY'] = os.getenv("GEMINI_API_KEY", None)

ai_client = genai.Client(api_key=app.config['GEMINI_API_KEY'])

with open("ai_personality.txt", "r") as f:
    ai_personality = f.read()

current_log_file = None

connected_usernames = []

def clear_chatlogs():
    global current_log_file
    chatlogs_dir = 'chatlogs'

    for filename in os.listdir(chatlogs_dir):
        file_path = os.path.join(chatlogs_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    current_log_file = os.path.join(chatlogs_dir, f"{today}.json")

    with open(current_log_file, 'w') as f:
        json.dump([], f)

    print(f"New log file created: {current_log_file}")

def add_chatlog_entry(message, nickname, timestamp, msg_type: str = "text"):
    global current_log_file
    # # Ensure current_log_file is set. If not, try to initialize it.
    # if not current_log_file:
    #     print("Warning: current_log_file was None, reinitializing chatlog status.")
    #     check_chatlog_status()
    #     if not current_log_file:
    #         print("Error: Unable to set current_log_file. Chatlog entry not added.")
    #         return

    chatlogs = []

    if os.path.exists(current_log_file):
        with open(current_log_file, 'r') as f:
            chatlogs = json.load(f)

    chatlogs.append({
        'message': message,
        'nickname': nickname,
        'timestamp': timestamp,
        'type': msg_type
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



def generate_response(message: str, user: str, enable_google_search: bool = True):
    global ai_client

    
    chat_context = load_recent_chat_context(num_messages=20)
    people_online = "".join([f"{name}\n" for name in connected_usernames])
    # Build a full prompt that includes the chat history and the new message
    full_prompt = f"Users connected:\n{people_online}Here is the conversation so far:\n{chat_context}\nKAC-Bot:"
    print(full_prompt)

    # full_prompt = f"{user} asks: {message}"

    google_search_tool = types.Tool(
        google_search = types.GoogleSearch()
        )

    generate_content_config = types.GenerateContentConfig(
            system_instruction=ai_personality,
            tools=[google_search_tool] if enable_google_search else [],
            response_modalities=["TEXT"],
        )

    response = ai_client.models.generate_content(
        model="gemini-2.0-flash",
        config=generate_content_config,
        contents=full_prompt,
    )
    return response

@socketio.on("connect")
def handle_connect():
    nickname = request.args.get('nickname')
    print(f"User connected: {nickname}")

    # if nickname not in connected_usernames:
    #     socketio.emit('user_connected', nickname)
    if nickname:
        connected_usernames.append(nickname)
    

@socketio.on("disconnect")
def handle_disconnect():
    nickname = request.cookies.get('nickname')
    print(f"User disconnected: {nickname}")
    connected_usernames.remove(nickname)
    # socketio.emit('user_disconnected', nickname)

@socketio.on("chat_message")
def handle_chat_message(data):
    message = data.get('message')
    nickname = data.get('nickname')
    timestamp = data.get('timestamp')
    
    # print(f"Received message: {message} from {nickname} at {timestamp}")
    if message == "/clear":
        socketio.emit('clear_chat', room=request.sid)
        return

    socketio.emit('chat_message', { 'message': message, 'nickname': nickname, 'timestamp': timestamp })

    add_chatlog_entry(message, nickname, timestamp)

    if message.startswith("!bot "):
        response = generate_response(message, user=nickname) # .removeprefix("!bot ")?
        message = response.text
        timestamp = datetime.datetime.now().isoformat()
        socketio.emit('chat_message', { 'message': message, 'nickname': "KAC-Bot", 'timestamp': timestamp })
        add_chatlog_entry(message, "KAC-Bot", timestamp)

    if message == "/clear":
        # socketio.emit('clear_chat', {}, to)
        socketio.emit('clear_chat', room=request.sid)

@socketio.on("send_image")
def handle_image(data):
    print("Received image")
    image = data.get('image')
    nickname = data.get('nickname')
    timestamp = data.get('timestamp')

    socketio.emit('send_image', { 'image': image, 'nickname': nickname, 'timestamp': timestamp })

    add_chatlog_entry(image, nickname, timestamp, msg_type="image")

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
            response = make_response(render_template('chatroom.html'))
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
    return jsonify(connected_usernames)

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


if __name__ == '__main__':
    check_chatlog_status()
    run_scheduled_task()
    socketio.run(app)