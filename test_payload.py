import sys
sys.path.insert(0, 'c:/Dev/AiVoiceTagger/sidecar')
import server
import json

try:
    payload = server.build_telemetry_payload()
    with open('c:/Dev/AiVoiceTagger/payload_out.txt', 'w') as f:
        json.dump(payload, f, indent=2)
except Exception as e:
    import traceback
    with open('c:/Dev/AiVoiceTagger/payload_out.txt', 'w') as f:
        traceback.print_exc(file=f)
