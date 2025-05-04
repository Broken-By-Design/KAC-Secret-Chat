import binascii
import os

def generate_random_string():

    random_hex = binascii.hexlify(os.urandom(16)).decode('ascii')
    
    return f"{random_hex}"

def get_online_users(connected_usernames: list[str]) -> list[str]:
    return list(connected_usernames)