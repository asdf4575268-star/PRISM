import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time
import os

# --- [0. 로컬 DB 안전 경로 설정] ---
os.makedirs('data', exist_ok=True)
DB_NAME = 'data/archive_prism_total_v4.db'

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Jolly+Lodger&family=Kirang+Haerang&family=Lacquer&display=swap');
    .title-text { font-family: 'Jolly Lodger', cursive; font-size: 90px; line-height: 1.1; }
    .date-text { font-family: 'Kirang Haerang', cursive; font-size: 30px; }
    .num-text { font-family: 'Lacquer', sans-serif; font-size: 60px; color: #E74C3C; }
    div[data-testid="column"] { display: flex; flex-direction: column; align-items: center; text-align: center !important; }
    .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1; overflow: hidden; border-radius: 6px; margin-bottom: 5px; }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
    .badge { position: absolute; top: 5px; background: rgba(0, 0, 0, 0.6); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; z-index: 10; }
    .badge-left { left: 5px; background: rgba(50, 50, 50, 0.8); } 
    .badge-right { right: 5px; } 
    </style>
""", unsafe_allow_html=True)

st.title("🌈PRISM")

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# --- [비상 복구 시스템 (사이드바)] ---
with st.sidebar:
    st.header("🛠️ 시스템 복구")
    recovery_url = st.text_input("구글 시트 CSV 링크 입력")
    
    if st.button("🔄 구글 시트에서 데이터 복구", use_container_width=True):
        try:
            df_backup = pd.read_csv(recovery_url)
            # 열 개수 확인 및 강제 매핑 (사용자 제공 순서 기준)
            df_backup.columns = ['save_date', 'category', 'title', 'creator', 'rel_date', 'summary', 'brief', 'highlights', 'note', 'img_url', 'view_date']
            
            # [방어 코드] 날짜 형식이 아닌 데이터는 NaT로 만들고 오늘 날짜로 대체
            df_backup['view_date'] = pd.to_datetime(df_backup['view_date'], errors='coerce').dt.strftime('%Y-%m-%d')
            df_backup['save_date'] = pd.to_datetime(df_backup['save_date'], errors='coerce').dt.strftime('%Y-%m-%d')
            df_backup = df_backup.fillna({'view_date': str(date.today()), 'save_date': str(date.today())})

            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive")
                df_backup.to_sql('archive', conn, if_exists='append', index=False)
            
            st.success("✅ 복구 완료! 새로고침합니다.")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"복구 중 오류: {e}")

# --- [2. API 함수] ---
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
        return [{'display_name': f"🎵 {m.get('trackName', 'Unknown')}", 'title': m.get('trackName', 'Unknown'), 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'url': m.get('trackViewUrl', '')} for m in res]
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
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

# --- [3. 팝업 함수] ---
@st.dialog("📋 상세 정보", width="large")
def show_details(item):
    t_col1, _, t_col3 = st.columns([0.2, 0.6, 0.2])
    with t_col1:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()
    with t_col3: edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
    
    st.divider()
    cl, cr = st.columns([0.3, 0.7])
    with cl:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
    with cr:
        if edit_mode:
            with st.form(f"f_{item['id']}"):
                n_t = st.text_input("제목", item['title'])
                n_c = st.text_input("창작자", item['creator'])
                n_v = st.date_input("감상일", pd.to_datetime(item['view_date']))
                n_note = st.text_area("감상", item['note'])
                if st.form_submit_button("저장"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE archive SET title=?, creator=?, view_date=?, note=? WHERE id=?", (n_t, n_c, str(n_v), n_note, item['id']))
                    st.rerun()
        else:
            st.markdown(f'<div class="title-text">{item["title"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<p class="date-text">🍿 {item["view_date"]}</p>', unsafe_allow_html=True)
            st.info(item['note'] or "내용 없음")

# --- [4. 메인 탭] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    q = st.text_input(f"🔍 {category} 검색")
    if q:
        # (검색 로직 중략 - 이전 코드와 동일)
        st.write("검색 결과에서 '가져오기'를 눌러주세요.")
    
    with st.form("write_form"):
        col_l, col_r = st.columns(2)
        with col_l:
            t = st.text_input("제목")
            c = st.text_input("창작자")
            vd = st.date_input("감상일", date.today())
        with col_r:
            nt = st.text_area("💬 감상 (KM, BPM은 소문자 자동변환)")
            img = st.text_input("이미지 URL")
        
        if st.form_submit_button("✅ 기록하기"):
            processed_note = nt.replace("KM", "km").replace("BPM", "bpm")
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?)",
                             (category, t, c, processed_note, img, str(date.today()), str(vd)))
            st.success("저장 완료!")
            st.rerun()

with tab2:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)
    
    if not all_df.empty:
        # [핵심 수정] 날짜 변환 시 에러 방지 (coerce) 및 정렬
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce').fillna(pd.to_datetime(all_df['save_date'], errors='coerce'))
        all_df = all_df.dropna(subset=['v_dt']).sort_values('v_dt', ascending=False)
        
        sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])
        
        with sub_tabs[0]:
            all_df['year'] = all_df['v_dt'].dt.year
            all_df['month'] = all_df['v_dt'].dt.month
            sel_y = st.selectbox("연도", sorted(all_df['year'].unique(), reverse=True))
            
            y_data = all_df[all_df['year'] == sel_y]
            for m in range(12, 0, -1):
                m_data = y_data[y_data['month'] == m]
                if not m_data.empty:
                    st.subheader(f"🗓️ {m}월")
                    cols = st.columns(6)
                    for idx, row in enumerate(m_data.to_dict('records')):
                        with cols[idx % 6]:
                            st.markdown(f'<div class="cal-img-box"><div class="badge badge-left">{row["category"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                            if st.button(f"{row['title'][:10]}", key=f"y_{row['id']}"): show_details(row)
