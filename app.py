import streamlit as st
import sqlite3
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time
import os

# --- [0. 기본 설정 및 DB 초기화] ---
os.makedirs('data', exist_ok=True)
DB_NAME = 'data/archive_prism_total_v5.db' # 버전 업그레이드

st.set_page_config(layout="wide", page_title="PRISM")

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# 세션 상태 초기화
if 'api_data' not in st.session_state: st.session_state.api_data = {}

# --- [1. 디자인 가이드 및 CSS] ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Jolly+Lodger&family=Kirang+Haerang&family=Lacquer&display=swap');
    
    /* 활동명 90px */
    .title-text { font-family: 'Jolly Lodger', cursive; font-size: 90px; line-height: 1.1; color: #111; word-break: keep-all; }
    /* 날짜 30px */
    .date-text { font-family: 'Kirang Haerang', cursive; font-size: 30px; color: #666; }
    /* 숫자 60px */
    .num-text { font-family: 'Lacquer', sans-serif; font-size: 60px; color: #E74C3C; vertical-align: middle; }
    
    div[data-testid="column"] { display: flex; flex-direction: column; align-items: center; text-align: center !important; }
    .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1; overflow: hidden; border-radius: 10px; border: 1px solid #eee; background: #f9f9f9; }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
    .badge { position: absolute; top: 5px; background: rgba(0, 0, 0, 0.6); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; z-index: 10; }
    .badge-left { left: 5px; background: rgba(50, 50, 50, 0.8); } 
    .badge-right { right: 5px; background: #E74C3C; } 
    </style>
""", unsafe_allow_html=True)

# --- [2. 유틸리티 함수 (API & 데이터 처리)] ---
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
        return [{
            'display_name': f"{'📀' if m.get('wrapperType')=='collection' else '🎵'} {m.get('collectionName' if m.get('wrapperType')=='collection' else 'trackName')} - {m.get('artistName')}",
            'title': m.get('collectionName' if m.get('wrapperType')=='collection' else 'trackName'),
            'creator': m.get('artistName'), 'date': m.get('releaseDate', '')[:10],
            'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'url': m.get('collectionViewUrl', '')
        } for m in res]
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key=6e7c55b6259b7731655033f783f3fc5b&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service=7a919bc272204f06bbca10e2af376dea&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

def format_note(text):
    """KM, BPM 소문자 변환 및 숫자 강조 처리"""
    if not text: return ""
    text = text.replace("KM", "km").replace("BPM", "bpm")
    return re.sub(r'(\d+)\s*(km|bpm)', r'<span class="num-text">\1</span> \2', text)

# --- [3. 사이드바: 복구 센터] ---
with st.sidebar:
    st.header("⚙️ SYSTEM")
    with st.expander("데이터 복구 (Google Sheets)", expanded=False):
        recovery_url = st.text_input("CSV 링크 입력")
        if st.button("🔄 강제 복구 실행"):
            try:
                df_backup = pd.read_csv(recovery_url, dtype=str).fillna("")
                df_backup.columns = ['save_date', 'category', 'title', 'creator', 'rel_date', 'summary', 'brief', 'highlights', 'note', 'img_url', 'view_date']
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive")
                    df_backup.to_sql('archive', conn, if_exists='append', index=False)
                st.success("데이터가 복구되었습니다!")
                st.rerun()
            except Exception as e: st.error(f"오류: {e}")

# --- [4. 상세 보기 및 수정 팝업] ---
@st.dialog("📋 MEMORY DETAIL", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    t_col1, t_col2 = st.columns([0.8, 0.2])
    with t_col2:
        edit_mode = st.toggle("✏️ 수정", key=f"edit_tog_{item['id']}")
        if st.button("🗑️ 삭제", key=f"del_{item['id']}"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()

    if edit_mode:
        with st.form(f"edit_form_{item['id']}"):
            n_title = st.text_input("제목", value=item['title'])
            n_creator = st.text_input("창작자", value=item['creator'])
            n_note = st.text_area("감상", value=item['note'])
            if st.form_submit_button("💾 수정사항 저장"):
                final_note = n_note.replace("KM", "km").replace("BPM", "bpm")
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("UPDATE archive SET title=?, creator=?, note=? WHERE id=?", (n_title, n_creator, final_note, item['id']))
                st.rerun()
    else:
        # 디자인 가이드 반영 조회 화면
        st.markdown(f'<div class="title-text">{item["title"]}</div>', unsafe_allow_html=True)
        col_img, col_txt = st.columns([0.4, 0.6])
        with col_img:
            st.image(item['img_url'] or "https://via.placeholder.com/400", use_container_width=True)
        with col_txt:
            v_date = item['view_date'] or item['save_date']
            st.markdown(f'<p class="date-text">🍿 WATCHED: {v_date}</p>', unsafe_allow_html=True)
            st.write(f"**Creator:** {item['creator']} | **Released:** {item['rel_date']}")
            st.divider()
            if item['brief']: st.success(item['brief'])
            st.markdown(format_note(item['note']), unsafe_allow_html=True)

# --- [5. 메인 탭 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

# --- WRITE TAB ---
with tab1:
    category = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    q = st.text_input(f"🔍 {category} 검색")
    
    if q:
        res = []
        if category == "BOOKS": res = search_books(q)
        elif category == "MUSIC": res = search_apple_music(q)
        elif category == "STAGE": res = search_kopis(q)
        else: res = search_tmdb(q, category)
        
        if res:
            if category == "BOOKS":
                opts = {f"📚 {b['title']}": b for b in res}
                sel = st.selectbox("결과", list(opts.keys()))
                if st.button("가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': ",".join(b['authors']), 'img': b['thumbnail'], 'date': b['datetime'][:10], 'summary': b['contents']}
                    st.rerun()
            elif category == "MUSIC":
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과", list(opts.keys()))
                if st.button("가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'img': m['img'], 'date': m['date'], 'summary': m['url']}
                    st.rerun()
            # ... 기타 카테고리 로직 동일 ...

    st.divider()
    data = st.session_state.get('api_data', {})
    with st.form("write_form"):
        c1, c2 = st.columns([0.4, 0.6])
        with c1:
            f_img = st.text_input("이미지 URL", value=data.get('img', ''))
            f_title = st.text_input("제목", value=data.get('title', ''))
            f_creator = st.text_input("창작자", value=data.get('creator', ''))
        with c2:
            f_rel = st.text_input("출시일", value=data.get('date', ''))
            f_view = st.date_input("감상일", value=date.today())
            f_brief = st.text_input("한줄 요약")
            n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights') or ''), height=100)
            f_note = st.text_area("감상")
            
        if st.form_submit_button("✅ 저장 및 백업"):
            processed_note = f_note.replace("KM", "km").replace("BPM", "bpm")
            # 로컬 저장
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("""INSERT INTO archive (category, title, creator, rel_date, note, img_url, save_date, view_date, brief) 
                             VALUES (?,?,?,?,?,?,?,?,?)""",
                             (category, f_title, f_creator, f_rel, processed_note, f_img, str(date.today()), str(f_view), f_brief))
            
            # 구글 백업 전송
            BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
            requests.post(BACKUP_URL, data={"entry.574529989": category, "entry.898076783": f_title, "entry.891180756": processed_note})
            
            st.success("성공적으로 저장되었습니다!")
            st.session_state.api_data = {}
            st.rerun()

# --- ARCHIVE TAB ---
with tab2:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    if not all_df.empty:
        # 날짜 정렬 (엉킴 방지)
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce').fillna(pd.to_datetime(all_df['save_date'], errors='coerce'))
        all_df = all_df.sort_values(by='v_dt', ascending=False)
        
        sub_tab_names = ["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"]
        sub_tabs = st.tabs(sub_tab_names)

        # 1. YEARLY
        with sub_tabs[0]:
            years = sorted(all_df['v_dt'].dt.year.unique(), reverse=True)
            sel_y = st.selectbox("연도", years)
            y_data = all_df[all_df['v_dt'].dt.year == sel_y]
            for m in range(12, 0, -1):
                m_data = y_data[y_data['v_dt'].dt.month == m]
                if not m_data.empty:
                    st.subheader(f"🗓️ {m}월")
                    items = m_data.to_dict('records')
                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'''<div class="cal-img-box">
                                        <div class="badge badge-left">{row['category']}</div>
                                        <div class="badge badge-right">{row['v_dt'].day}일</div>
                                        <img src="{row['img_url'] or "https://via.placeholder.com/300"}">
                                    </div>''', unsafe_allow_html=True)
                                    if st.button(f"{row['title'][:7]}..", key=f"y_{row['id']}", use_container_width=True):
                                        show_details(row)

        # 2~6. CATEGORIES
        cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        for idx, c_name in enumerate(cats):
            with sub_tabs[idx+1]:
                c_data = all_df[all_df['category'] == c_name]
                if not c_data.empty:
                    items = c_data.to_dict('records')
                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'''<div class="cal-img-box">
                                        <div class="badge badge-left">{row['view_date']}</div>
                                        <img src="{row['img_url'] or "https://via.placeholder.com/300"}">
                                    </div>''', unsafe_allow_html=True)
                                    if st.button(f"{row['title'][:7]}..", key=f"c_{idx}_{row['id']}", use_container_width=True):
                                        show_details(row)
                else: st.info("기록이 없습니다.")
    else: st.info("아직 기록이 없습니다.")

