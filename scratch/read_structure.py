import os

path = r"\\SyNAS\CloudSpace\LexSpace\structure.txt"
try:
    with open(path, "r", encoding="utf-16le") as f:
        content = f.read()
    print("--- CONTENT OF structure.txt ---")
    print(content[:4000])
except Exception as e:
    print(f"Error reading UTF-16LE: {e}")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            print("--- UTF-8 FALLBACK ---")
            print(f.read()[:4000])
    except Exception as e2:
        print(f"Error fallback: {e2}")
