#!/usr/bin/env python3
from __future__ import annotations
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"runtime"
FILES=[
 "blacklist_numbers.json","bot_state.pkl","calendario_turnos.csv","calendar_events.db",
 "client_memory.json","conversation_log.jsonl","conversation_states.json","human_cases.json",
 "operations_metrics.jsonl","proactive_state.json","reservas_contactos.csv","selector_adaptation_cache.json",
 "selector_health_history.json","turnos_terminados.csv","waitlist.json","used_payment_receipts.json",
 "canonical_agent_state.sqlite3","wpsetter_logs.txt",
]
RUNTIME.mkdir(parents=True,exist_ok=True)
for name in FILES:
    src=ROOT/name
    if src.exists():
        dst=RUNTIME/name
        if dst.exists():
            print(f"skip {name}: destination exists")
        else:
            shutil.move(str(src),str(dst)); print(f"moved {name}")
old=ROOT/"agent_learning"
new=RUNTIME/"agent_learning"
if old.exists() and not new.exists():
    shutil.move(str(old),str(new)); print("moved agent_learning/")
print("Migration complete.")
