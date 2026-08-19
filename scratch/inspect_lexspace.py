import os

input_path = r"\\SyNAS\CloudSpace\LexSpace\structure.txt"
output_path = r"C:\Dev\AiVoiceTagger\scratch\structure_utf8.txt"

try:
    with open(input_path, "r", encoding="utf-16le") as f:
        text = f.read()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print("Successfully converted structure.txt to UTF-8 in scratch directory.")
except Exception as e:
    print(f"Error reading UTF-16LE: {e}")
    try:
        with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        print("Successfully copied structure.txt using UTF-8 fallback.")
    except Exception as e2:
        print(f"Error fallback: {e2}")
