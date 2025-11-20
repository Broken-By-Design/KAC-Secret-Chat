import re
import unicodedata
from difflib import SequenceMatcher

# Your censor list
with open("badwords.txt", "r", encoding="utf-8") as f:
    CENSOR_WORDS = [f.strip().lower() for f in f.readlines() if f.strip()]

CENSOR_CHAR = '#'

def normalize_char(char: str) -> str:
    """
    Normalize a character by handling homoglyphs and character substitutions.
    Examples:
        '1' (digit one) → 'i'
        '0' (digit zero) → 'o'
        'ı' (dotless i) → 'i'
        'é' (accented e) → 'e'
    """
    # Remove accents/diacritics (é → e, ü → u, etc.)
    char_normalized = unicodedata.normalize('NFD', char)
    char_normalized = ''.join(c for c in char_normalized if unicodedata.category(c) != 'Mn')
    char_normalized = char_normalized.lower()
    
    # Map common leetspeak/homoglyphs to letters
    substitutions = {
        '0': 'o', 'O': 'o',
        '1': 'i', '!': 'i', '|': 'i',
        '3': 'e', 'ε': 'e',
        '4': 'a', '@': 'a',
        '5': 's', '$': 's',
        '7': 't',
        '8': 'b',
        '9': 'g', 'q': 'g',
        'ß': 'ss',  # German eszett
    }
    
    if char_normalized in substitutions:
        return substitutions[char_normalized]
    
    return char_normalized


def normalize_text(text: str) -> str:
    """
    Normalize entire text by converting characters and removing common obfuscation.
    """
    normalized = ''.join(normalize_char(c) if c.isalnum() else c for c in text)
    # Remove common spacing/separators used to bypass filters
    normalized = re.sub(r'[\s\-_\.]+', '', normalized)
    return normalized.lower()


def calculate_similarity(str1: str, str2: str) -> float:
    """
    Calculate similarity between two strings using SequenceMatcher.
    Returns a value between 0 and 1 (1 = perfect match).
    """
    return SequenceMatcher(None, str1, str2).ratio()


def is_word_match(original_word: str, censor_word: str, min_similarity: float = 0.85) -> bool:
    """
    Check if original_word matches censor_word with fuzzy matching.
    
    Args:
        original_word: The word from the message
        censor_word: The word to censor
        min_similarity: Threshold (0-1). 0.85 = 85% similar counts as match
    
    Returns:
        True if words match closely enough
    """
    norm_original = normalize_text(original_word)
    norm_censor = normalize_text(censor_word)
    
    # Exact match after normalization
    if norm_original == norm_censor:
        return True
    
    # If lengths differ significantly, probably not a match
    if abs(len(norm_original) - len(norm_censor)) > 2:
        return False
    
    # Fuzzy matching: check similarity
    similarity = calculate_similarity(norm_original, norm_censor)
    return similarity >= min_similarity


def censor_message(message: str, censor_list: list[str] = None, min_similarity: float = 0.85) -> str:
    """
    Intelligently censors profanity using normalization and fuzzy matching.
    
    Args:
        message: The message to censor
        censor_list: List of words to censor
        min_similarity: Fuzzy matching threshold (0-1)
    
    Returns:
        Tuple of (censored_message, list_of_caught_words)
    
    Examples:
        "fuck" → "f**k" ✓
        "FUCK" → "F**k" ✓
        "f u c k" → "f***k" ✓
        "fuсk" (Cyrillic 'с') → "f**k" ✓
        "f1ck" (leetspeak) → "f**k" ✓
        "BlTCH" (mixed case) → "B***h" ✓
        "b!tch" → "b**h" ✓
    """
    if censor_list is None:
        censor_list = CENSOR_WORDS
    
    caught_words = []
    words = re.findall(r'\b\w+\b', message, re.UNICODE)
    
    for censor_word in censor_list:
        for original_word in words:
            # Check if word matches (with normalization & fuzzy matching)
            if is_word_match(original_word, censor_word, min_similarity):
                caught_words.append(original_word)
                
                # Replace word with censored version
                # Use regex with word boundary to replace all variations
                pattern = re.escape(original_word)
                
                def replace_with_censors(match):
                    word = match.group(0)
                    if len(word) <= 2:
                        return CENSOR_CHAR * len(word)
                    # Preserve case pattern of original word
                    censored = ''
                    for i, char in enumerate(word):
                        if i == 0 or i == len(word) - 1:
                            censored += char
                        else:
                            censored += CENSOR_CHAR
                    return censored
                
                message = re.sub(pattern, replace_with_censors, message, flags=re.IGNORECASE)
    
    return message

# def censor_message(message: str, censor_list: list[str] = None, min_similarity: float = 0.85) -> str:
#     """
#     Intelligently censors profanity using normalization and fuzzy matching.
    
#     Args:
#         message: The message to censor
#         censor_list: List of words to censor
#         min_similarity: Fuzzy matching threshold (0-1)
    
#     Returns:
#         The censored message
    
#     Examples:
#         "fuck" → "f**k"
#         "FUCK" → "F**k"
#         "f u c k" → "f***k"
#         "fuсk" (Cyrillic 'с') → "f**k"
#         "f1ck" (leetspeak) → "f**k"
#         "BlTCH" (mixed case) → "B***h"
#         "b!tch" → "b**h"
#     """
#     if censor_list is None:
#         censor_list = CENSOR_WORDS
    
#     words = re.findall(r'\b\w+\b', message, re.UNICODE)
    
#     for censor_word in censor_list:
#         for original_word in words:
#             # Check if word matches (with normalization & fuzzy matching)
#             if is_word_match(original_word, censor_word, min_similarity):
#                 # Replace word with censored version
#                 pattern = re.escape(original_word)
                
#                 def replace_with_censors(match):
#                     word = match.group(0)
#                     if len(word) <= 2:
#                         return '*' * len(word)
#                     # Preserve case pattern of original word
#                     censored = ''
#                     for i, char in enumerate(word):
#                         if i == 0 or i == len(word) - 1:
#                             censored += char
#                         else:
#                             censored += '*'
#                     return censored
                
#                 message = re.sub(pattern, replace_with_censors, message, flags=re.IGNORECASE)
    
#     return message