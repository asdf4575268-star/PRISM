import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date
import time
from supabase import create_client, Client

# --- [1. 설정 및 API] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'

# Supabase 연결
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- [로그인 시스템] ---
with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    input_password = st.text_input("Password", type="password")
    is_admin = (input_password == st.secrets["ADMIN_PASSWORD"])
    if is_admin: st.success("Admin Mode Active")
    elif input_password: st.error("Incorrect Password")

if 'api_data' not in st.session_state: st.session_state.api_data = {}

# --- [2. DB 함수 및 동기화] ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def migrate_to_supabase():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        local_data = conn.execute("SELECT * FROM archive").fetchall()
    if not local_data:
        st.session_state.sync_msg = ("warning", "로컬 데이터가 없습니다.")
        return
    upload_list = [dict(row) for row in local_data]
    for d in upload_list:
        if 'id' in d: del d['id']
    try:
        supabase.table("archive").insert(upload_list).execute()
        st.session_state.sync_msg = ("success", "✅ 클라우드 백업 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        # 1. 슈퍼베이스에서 전체 데이터 긁어오기
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        
        if not cloud_data:
            st.session_state.sync_msg = ("warning", "⚠️ 클라우드(Supabase)가 비어있습니다. 백업된 데이터가 없습니다.")
            return

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            
            # 2. 로컬 테이블이 비어있을 수도 있으니 초기화 확인
            cursor.execute('''CREATE TABLE IF NOT EXISTS archive 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                             rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
            
            added_count = 0
            for row in cloud_data:
                # 3. 중복 체크를 '제목'과 '감상일'로 수행 (가장 확실한 기준)
                cursor.execute("SELECT id FROM archive WHERE title=? AND view_date=?", 
                               (row.get('title'), row.get('view_date')))
                if not cursor.fetchone():
                    # 로컬에 없는 데이터만 삽입
                    cursor.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row.get('category'), row.get('title'), row.get('creator'), row.get('rel_date'), 
                         row.get('venue'), row.get('summary'), row.get('brief'), row.get('highlights'), 
                         row.get('note'), row.get('img_url'), row.get('save_date'), row.get('view_date')))
                    added_count += 1
            
            conn.commit()
            
        st.session_state.sync_msg = ("success", f"✅ 복구 완료! 클라우드로부터 {added_count}개의 새로운 데이터를 가져왔습니다.")
        
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 중 오류 발생: {str(e)}")

# --- [3. API 검색 함수들] ---
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url).json().get("results", [])
        formatted_res = []
        for m in res:
            is_album = m.get('wrapperType') == 'collection'
            title = m.get('collectionName' if is_album else 'trackName', 'Unknown')
            formatted_res.append({'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}", 'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName', '')})
        return formatted_res
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}/credits?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        res = requests.get(url).json()
        director = next((m['name'] for m in res.get('crew', []) if m.get('job') == 'Director'), "정보 없음")
        cast = ", ".join([c['name'] for c in res.get('cast', [])[:3]])
        return f"감독: {director} / 출연: {cast}"
    except: return "정보 없음"

# --- [4. 팝업 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    t_col1, t_col2, t_col3 = st.columns([0.2, 0.6, 0.2])
    if is_admin:
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn: conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                st.rerun()
        with t_col3: edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
    else: edit_mode = False

    st.divider()
    col_img, col_txt = st.columns([0.3, 0.7])
    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
    with col_txt:
        if edit_mode and is_admin:
            with st.form(key=f"edit_form_{item['id']}"):
                n_img = st.text_input("🖼️ 이미지 URL", value=item.get('img_url', ''))
                n_title = st.text_input("📌 제목", value=item.get('title', ''))
                n_creator = st.text_input("👤 창작자", value=item.get('creator', ''))
                n_rel = st.text_input("📅 작품 날짜", value=item.get('rel_date', ''))
                n_venue = st.text_input("📍 장소/플랫폼", value=item.get('venue', ''))
                n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item.get('view_date')).date())
                n_brief = st.text_input("📝 요약", value=item.get('brief', ''))
                n_sum = st.text_area("📖 줄거리", value=item.get('summary', ''), height=100)
                n_high = st.text_area("✨ 인상 깊은 부분", value=item.get('highlights', ''), height=100)
                n_note = st.text_area("💬 감상", value=item.get('note', ''), height=100)
                if st.form_submit_button("💾 저장"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=? WHERE id=?""", (n_title, n_creator, n_rel, n_venue, n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, item['id']))
                    st.success("수정 완료!"); st.rerun()
        else:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**[{item.get('category')}]** {item.get('creator')} | 📅 {item.get('rel_date')} | 📍 {item.get('venue')}")
            st.markdown(f'<p style="color: #FF4B4B; font-weight: bold; font-size: 1.2em;">🍿 {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            if item.get('brief'): st.info(f"**요약:** {item.get('brief')}")
            if item.get('summary'): st.write(f"**줄거리:**\n{item.get('summary')}")
            if item.get('highlights'): st.warning(f"**인상 깊은 부분:**\n{item.get('highlights')}")
            if item.get('note'): st.success(f"**나의 감상:**\n{item.get('note')}")

# --- [5. 메인 화면] ---
if is_admin: tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else: 
    tabs = st.tabs(["📂 ARCHIVE"])
    tab_w = None
    tab_a = tabs[0]

# --- [WRITE 탭] ---
if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        search_query = st.text_input(f"🔍 {category} 검색")
        if search_query:
            if category == "BOOKS":
                res = search_books(search_query)
                if res:
                    opts = {f"📚 {b['title']}": b for b in res}; sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        b = opts[sel]; st.session_state.api_data = {'title': b['title'], 'creator': ", ".join(b['authors']), 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'venue': b.get('publisher', ''), 'summary': b.get('contents', '')}
                        st.rerun()
            elif category == "MUSIC":
                res = search_apple_music(search_query)
                if res:
                    opts = {m['display_name']: m for m in res}; sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        m = opts[sel]; st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'venue': m['creator']}
                        st.rerun()
            elif category in ["MOVIES", "SERIES"]:
                res = search_tmdb(search_query, category)
                if res:
                    t_key = 'title' if category == 'MOVIES' else 'name'; d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                    opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}; sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]; st.session_state.api_data = {'title': s.get(t_key), 'creator': get_tmdb_details(s['id'], category), 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
                        st.rerun()

        st.divider(); data = st.session_state.get('api_data', {}); cl, cr = st.columns([0.4, 0.6])
        with cl:
            img_url_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
            if img_url_val: st.image(img_url_val, use_container_width=True)
            title = st.text_input("제목", value=data.get('title', '')); creator = st.text_input("창작자 정보", value=data.get('creator', ''))
            rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today()))); venue = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
        with cr:
            summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=100); brief = st.text_input("📝 요약 (한 줄 평)"); highlights = st.text_area("✨ 인상 깊은 부분", height=100); note = st.text_area("💬 나의 감상", height=100); view_date = st.date_input("🍿 감상일", value=date.today())
            if st.button("✅ 기록 저장", use_container_width=True):
                new_record = {"category": category, "title": title, "creator": creator, "rel_date": rel_date, "venue": venue, "summary": summary, "brief": brief, "highlights": highlights, "note": note, "img_url": img_url_val, "save_date": str(date.today()), "view_date": str(view_date)}
                try:
                    with sqlite3.connect(DB_NAME) as conn: conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
                    supabase.table("archive").insert(new_record).execute(); st.success("✅ 저장 완료!"); st.session_state.api_data = {}; time.sleep(0.5); st.rerun()
                except Exception as e: st.error(f"❌ 오류: {e}")

# --- [ARCHIVE 탭] ---
with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-bottom: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); transition: 0.3s; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
    </style>""", unsafe_allow_html=True)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
        
        # 1. 연도 선택 및 숫자 표시
        year_options = {y: f"{y} ({len(all_df[all_df['v_dt'].dt.year == y])})" for y in years}
        sel_y = st.selectbox("📅 연도 선택", options=list(year_options.keys()), format_func=lambda x: year_options[x])
        y_df = all_df[all_df['v_dt'].dt.year == sel_y]

        # 2. 관리자용 백업/복구 버튼 (들여쓰기 수정됨)
        if is_admin:
            if 'sync_msg' in st.session_state:
                m_type, m_txt = st.session_state.sync_msg
                if m_type == "success": st.success(m_txt)
                elif m_type == "warning": st.warning(m_txt)
                else: st.error(m_txt)
                del st.session_state.sync_msg
            
            c1, c2, _ = st.columns([0.15, 0.15, 0.7])
            with c1: st.button("📤 Backup", on_click=migrate_to_supabase, use_container_width=True)
            with c2: st.button("📥 Restore", on_click=restore_from_supabase, use_container_width=True)

        # 3. 카테고리별 탭 설정
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        tab_titles = [f"📅 ALL ({len(y_df)})"] + [f"📂 {c} ({len(y_df[y_df['category'] == c])})" for c in cat_order]
        sub_tabs = st.tabs(tab_titles)

        # ALL 탭
        with sub_tabs[0]:
            for m in range(12, 0, -1):
                m_data = y_df[y_df['v_dt'].dt.month == m]
                if not m_data.empty:
                    st.subheader(f"🗓️ {m}월")
                    items = m_data.to_dict('records')
                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box"><div class="badge">{pd.to_datetime(row["view_date"]).day}일</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:8], key=f"all_{row['id']}", use_container_width=True): show_details(row)

        # 개별 카테고리 탭
        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx + 1]:
                c_data = y_df[y_df['category'] == c_name]
                if c_data.empty: st.info(f"{c_name} 데이터 없음")
                else:
                    items = c_data.to_dict('records')
                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box"><div class="badge">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:8], key=f"cat_{c_name}_{row['id']}", use_container_width=True): show_details(row)
    else: 
        st.warning("기록이 없습니다.")





