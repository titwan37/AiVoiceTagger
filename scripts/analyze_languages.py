import sqlite3
import re

FRENCH_WORDS = {
    'le', 'la', 'les', 'un', 'une', 'des', 'et', 'est', 'elle', 'il', 'ils', 'elles', 
    'je', 'tu', 'nous', 'vous', 'pour', 'dans', 'sur', 'avec', 'plus', 'pas', 'ne', 
    'que', 'qui', 'quand', 'ou', 'comment', 'pourquoi', 'oui', 'non', 'mon', 'ma', 
    'mes', 'ce', 'ces', 'ses', 'son', 'sa', 'du', 'au', 'aux', 'se', 'y', 'en', 'mais'
}

ENGLISH_WORDS = {
    'the', 'and', 'you', 'that', 'was', 'for', 'on', 'are', 'with', 'as', 'this', 
    'they', 'but', 'have', 'not', 'what', 'where', 'when', 'who', 'why', 'how', 
    'yes', 'no', 'is', 'am', 'my', 'it', 'to', 'in', 'of', 'we', 'he', 'she', 'they', 
    'your', 'me', 'i', 'do', 'go', 'can', 'will', 'up', 'down', 'out', 'about', 'get'
}

def detect_language(text):
    if not text:
        return 'unknown'
    words = [w.lower().strip(".,!?\"'()*-") for w in text.split()]
    fr_score = sum(1 for w in words if w in FRENCH_WORDS)
    en_score = sum(1 for w in words if w in ENGLISH_WORDS)
    
    if fr_score > en_score:
        return 'fr'
    elif en_score > fr_score:
        return 'en'
    return 'neutral'

def analyze():
    conn = sqlite3.connect("aivoicetagger_state.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT speaker_tag, script, COUNT(*) 
        FROM speeches 
        WHERE speaker_tag IN ('Dinda', 'Dinda_AMBIGUOUS')
        GROUP BY id
    """)
    rows = cursor.fetchall()
    
    fr_cnt = 0
    en_cnt = 0
    neutral_cnt = 0
    
    for tag, script, _ in rows:
        lang = detect_language(script)
        if lang == 'fr':
            fr_cnt += 1
        elif lang == 'en':
            en_cnt += 1
        else:
            neutral_cnt += 1
            
    print(f"Dinda matching language analysis:")
    print(f"  - French transcripts: {fr_cnt}")
    print(f"  - English transcripts: {en_cnt}")
    print(f"  - Neutral/Unknown transcripts: {neutral_cnt}")
    
    conn.close()

if __name__ == "__main__":
    analyze()
