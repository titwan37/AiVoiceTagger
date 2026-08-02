import sys
import json
import logging
from models import RecordInfo
from nlp_worker import NlpPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    pipeline = NlpPipeline()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            raw_data = json.loads(line)
            record = RecordInfo.model_validate(raw_data)

            enriched = pipeline.process_record(record)

            response_json = enriched.model_dump_json()
            sys.stdout.write(response_json + "\n")
            sys.stdout.flush()
        except Exception as e:
            logging.error(f"Error processing sidecar request: {e}")
            sys.stderr.write(f"ERROR: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
