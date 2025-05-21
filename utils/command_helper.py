import utils.globals as globals
from utils.helpers import add_chatlog_entry, add_to_prompt_history_safe
import html
import requests

def parse_command(message: str, nickname: str, timestamp: str) -> None:
    if message.startswith("/8ball "):
        question = message.split(" ", 1)[1]
        if not question:
            globals.socketio.emit('chat_message', { 'message': f"{html.escape(nickname)}, Please include a question", 'nickname': "8-Ball", 'timestamp': timestamp, 'system': True })
            add_chatlog_entry(f"{html.escape(nickname)}, Please include a question", "8-Ball", timestamp, globals.current_log_file, type="system")
            return
        response = requests.get("https://api.killallchickens.org/fun/8ball").json()["response"]
        globals.socketio.emit('chat_message', { 'message': f"{html.escape(question)} → {response}", 'nickname': "8-Ball", 'timestamp': timestamp, 'system': True })
        add_chatlog_entry(f"{html.escape(question)} → {response}", "8-Ball", timestamp, globals.current_log_file, type="system")
    if message.startswith("/joke"):
        try:
            response = requests.get("https://api.killallchickens.org/fun/joke", timeout=3).json()
        except requests.exceptions.RequestException:
            globals.socketio.emit('chat_message', { 'message': "I couldn't fetch a joke! check the server status: https://status.killallchickens.org/report/uptime/a03d13d0a05da5a94df473ae71f8d648/", 'nickname': "Joke-Bot", 'timestamp': timestamp, 'system': True })
            add_chatlog_entry("I couldn't fetch a joke! check the server status: https://status.killallchickens.org/report/uptime/a03d13d0a05da5a94df473ae71f8d648/", "Joke-Bot", timestamp, globals.current_log_file, type="system")
            return
        if response["type"] == "single":
            globals.socketio.emit('chat_message', { 'message': response["joke"], 'nickname': "Joke-Bot", 'timestamp': timestamp, 'system': True })
            add_chatlog_entry(response["joke"], "Joke-Bot", timestamp, globals.current_log_file, type="system")
            add_to_prompt_history_safe("user", response["joke"], type="text")
            return
        if response["type"] == "twopart":
            globals.socketio.emit('chat_message', { 'message': f"{response['setup']} → {response['delivery']}", 'nickname': "Joke-Bot", 'timestamp': timestamp, 'system': True })
            add_chatlog_entry(f"{response['setup']} → {response['delivery']}", "Joke-Bot", timestamp, globals.current_log_file, type="system")
            add_to_prompt_history_safe("user", f"{response['setup']} → {response['delivery']}", type="text")
            return

    else:
        return