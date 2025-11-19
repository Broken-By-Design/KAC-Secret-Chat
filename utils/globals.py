socketio = None


current_log_file = None

connected_usernames = set()

typing_users = set()

ai_prompt_history = []

users_with_sid = {} # dict[str, set[str]]

users_with_IP = {}

users_to_jumpscare = set()
users_to_crash = set()
users_to_censor = set()

kicked_users = set()
muted_users = set()

banned_ips_cache = {}

video_chat_users = {}
screen_sharers = set()