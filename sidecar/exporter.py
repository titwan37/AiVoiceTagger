import os
import json
import tempfile
from typing import List
import polars as pl
from models import RecordInfo


def export_to_parquet(records: List[RecordInfo], output_path: str):
    if not records:
        return

    data = []
    for r in records:
        data.append({
            "record_id": r.record_id,
            "name": r.name,
            "directory": r.directory,
            "date_record_day": r.date_record_day.isoformat() if r.date_record_day else None,
            "date_last_write": r.date_last_write.isoformat(),
            "length_bytes": r.length_bytes,
            "duration_seconds": r.duration_seconds,
            "speech_count": r.speech_count,
            "count_lethal": r.stats_verbatim.count_lethal,
            "count_legal": r.stats_verbatim.count_legal,
            "count_menaces": r.stats_verbatim.count_menaces,
            "count_insultes": r.stats_verbatim.count_insultes,
            "is_remarkable": r.stats_verbatim.is_remarkable(),
            "is_degraded": r.is_degraded,
            "state": r.state,
        })

    df = pl.DataFrame(data)
    
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with tempfile.NamedTempFile(dir=dir_name, delete=False, suffix=".parquet") as tmp:
        tmp_path = tmp.name

    df.write_parquet(tmp_path)
    os.replace(tmp_path, output_path)
