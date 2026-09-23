# -*- coding: utf-8 -*-
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from sqlalchemy import text
from app.database import engine
lines=[]
with engine.begin() as conn:
    for t in ["assessment_definitions","assessment_sessions","assessment_results","assessment_answers","assessment_comments","student_memories","report_snapshots","evaluation_archives"]:
        try:
            n=conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            lines.append(f"{t}={n}")
        except Exception as e:
            lines.append(f"{t}=ERR {type(e).__name__}")
out=ROOT/"scripts"/"_probe2_out.txt"
out.write_text("\n".join(lines)+"\n", encoding="utf-8")
print("done")
