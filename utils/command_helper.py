import utils.globals as globals
from utils.helpers import add_chatlog_entry, add_to_prompt_history_safe
import html
import requests

def parse_command(message: str, nickname: str, timestamp: str) -> None:
    url = "https://api.killallchickens.org"
    request_headers = { "Origin": "https://chat.killallchickens.org", "Referer": "https://chat.killallchickens.org" }
    # Add timeout to prevent hanging requests
    REQUEST_TIMEOUT = 5  # seconds
    
    if message.startswith("/8ball "):
        question = message.split(" ", 1)[1]
        if not question:
            globals.socketio.emit('chat_message', { 'message': f"{html.escape(nickname)}, Please include a question", 'nickname': "8-Ball", 'timestamp': timestamp, 'system': True })
            add_chatlog_entry(f"{html.escape(nickname)}, Please include a question", "8-Ball", timestamp, globals.current_log_file, type="system")
            return
        try:
            response = requests.get(f"{url}/fun/8ball", timeout=REQUEST_TIMEOUT).json()["response"]
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            globals.socketio.emit('chat_message', { 'message': f"I couldn't fetch a response! Please try again later.", 'nickname': "8-Ball", 'timestamp': timestamp, 'system': True })
            add_chatlog_entry(f"I couldn't fetch a response! Please try again later.", "8-Ball", timestamp, globals.current_log_file, type="system")
            return
        globals.socketio.emit('chat_message', { 'message': f"{html.escape(question)} → {response}", 'nickname': "8-Ball", 'timestamp': timestamp, 'system': True })
        add_chatlog_entry(f"{html.escape(question)} → {response}", "8-Ball", timestamp, globals.current_log_file, type="system")
    if message.startswith("/joke"):
        try:
            ip_response = requests.get("https://api.ipify.org?format=json", timeout=REQUEST_TIMEOUT)
            ip = ip_response.json().get("ip")
            print(f"Public IP is {ip}")
            response = requests.get(f"{url}/fun/joke?api_key=9813a54654f81bcc3f69fe1489f05e016d944c0b7d85df43feec77bf89ae97e7", timeout=REQUEST_TIMEOUT, headers=request_headers).json()
        except requests.exceptions.RequestException:
            globals.socketio.emit('chat_message', { 'message': f"I couldn't fetch a joke! check the server status: https://status.killallchickens.org/report/uptime/a03d13d0a05da5a94df473ae71f8d648/", 'nickname': "Joke-Bot", 'timestamp': timestamp, 'system': True })
            add_chatlog_entry(f"I couldn't fetch a joke! check the server status: https://status.killallchickens.org/report/uptime/a03d13d0a05da5a94df473ae71f8d648/", "Joke-Bot", timestamp, globals.current_log_file, type="system")
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