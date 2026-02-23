import sqlite3
from supabase import create_client, Client

SUPABASE_URL = "여기에_URL"
SUPABASE_KEY = "여기에_service_role_key"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DB_NAME = "archive_prism_total_v5.db"
TABLE_NAME = "archive"

print("=== FAST MIGRATION START ===")

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

cursor.execute(f"SELECT * FROM {TABLE_NAME}")
rows = cursor.fetchall()
columns = [desc[0] for desc in cursor.description]

print(f"총 {len(rows)}개 발견")

records = []

for row in rows:
    record = dict(zip(columns, row))
    record.pop("id", None)
    records.append(record)

# 🔥 100개씩 나눠서 업로드 (안정 + 속도)
batch_size = 100

for i in range(0, len(records), batch_size):
    batch = records[i:i+batch_size]
    supabase.table(TABLE_NAME).insert(batch).execute()
    print(f"⬆️ {i+len(batch)}개 업로드 완료")

print("🎉 마이그레이션 완료")
conn.close()
