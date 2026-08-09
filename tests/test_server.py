import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sidecar import server
try:
    print(server.build_telemetry_payload())
except Exception as e:
    import traceback
    traceback.print_exc()
