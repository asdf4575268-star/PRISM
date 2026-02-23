import sqlite3
from supabase import create_client, Client
import sys

# ===========================
# 🔐 Supabase 설정
# ===========================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# ===========================
# ⚙️ 옵션
# ===========================

SQLITE_DB_NAME = "archive_prism_total_v5.db"
TABLE_NAME = "archive"

CLEAR_SUPABASE_FIRST = False  # True로 바꾸면 Supabase 테이블 비우고 시작

# ===========================
# 🚀 시작
# ===========================

print("=== PRISM SQLite → Supabase Migration ===")

# 1️⃣ Supabase 연결
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase 연결 성공")
except Exception as e:
    print("❌ Supabase 연결 실패:", e)
    sys.exit()

# 2️⃣ SQLite 연결
try:
    conn = sqlite3.connect(SQLITE_DB_NAME)
    cursor = conn.cursor()
    print("✅ SQLite 연결 성공")
except Exception as e:
    print("❌ SQLite 연결 실패:", e)
    sys.exit()

# 3️⃣ 데이터 읽기
cursor.execute(f"SELECT * FROM {TABLE_NAME}")
rows = cursor.fetchall()

columns = [description[0] for description in cursor.description]

print(f"📦 SQLite 데이터 수: {len(rows)}개")

if len(rows) == 0:
    print("⚠️ SQLite에 데이터가 없습니다.")
    sys.exit()

# 4️⃣ Supabase 초기화 옵션
if CLEAR_SUPABASE_FIRST:
    print("🧹 Supabase 기존 데이터 삭제 중...")
    try:
        supabase.table(TABLE_NAME).delete().neq("id", 0).execute()
        print("✅ Supabase 초기화 완료")
    except Exception as e:
        print("❌ Supabase 초기화 실패:", e)
        sys.exit()

# 5️⃣ 마이그레이션
success_count = 0
fail_count = 0

for row in rows:
    record = dict(zip(columns, row))

    # SQLite id 제거 (Supabase는 자동 생성)
    record.pop("id", None)

    try:
        supabase.table(TABLE_NAME).insert(record).execute()
        success_count += 1
        print(f"⬆️ 업로드 성공 ({success_count}) : {record.get('title')}")
    except Exception as e:
        fail_count += 1
        print(f"❌ 실패 : {record.get('title')} → {e}")

# 6️⃣ 종료
conn.close()

print("\n============================")
print("🎉 마이그레이션 완료")
print(f"✅ 성공: {success_count}")
print(f"❌ 실패: {fail_count}")
print("============================")

