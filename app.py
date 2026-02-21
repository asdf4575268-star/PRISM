import streamlit as st
import sqlite3
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time
import os

# --- [0. DB 및 환경 설정] ---
os.makedirs('data', exist_ok=True)
DB_NAME = 'data/archive_prism_total_v4.db'

st.set_page_config(layout="wide", page_title="PRISM")

# [디자인 가이드] 폰트 및 크기 설정
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Jolly+Lodger&family=Kirang+Haerang&family=Lacquer&display=swap');
    .title-text { font-family: 'Jolly Lodger', cursive; font-size: 90px; line-height: 1.1; }
    .date-text { font-family: 'Kirang Haerang', cursive; font-size: 30px; }
    .num-text { font-family: 'Lacquer', sans-serif; font-size: 60px; color: #E74C3C; }
    div[data-testid="column"] { display: flex; flex-direction: column; align-items: center; text-align: center !important; }
    .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1; overflow: hidden; border-radius: 10px; margin-bottom: 5px; border: 1px solid #eee; background-color: #f9f9f9; }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
    .badge { position: absolute; top: 5px; background: rgba(0, 0, 0, 0.6); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; z-index: 10; }
    .badge-left { left: 5px; } 
    .badge-right { right: 5px; background: #E74C3C; } 
    </style>
""", unsafe_allow_html=True)

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# --- [1. API 검색 및 백업 로직] ---
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key=6e7c55b6259b7731655033f783f3fc5b&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

# --- [2. 사이드바: 복구] ---
with st.sidebar:
    st.header("🛠️ SYSTEM")
    recovery_url = st.text_input("구글 시트 CSV 링크")
    if st.button("🔄 데이터 강제 복구", use_container_width=True):
        try:
            df_backup = pd.read_csv(recovery_url, dtype=str).fillna("")
            expected_cols = ['save_date', 'category', 'title', 'creator', 'rel_date', 'summary', 'brief', 'highlights', 'note', 'img_url', 'view_date']
            df_backup.columns = expected_cols[:len(df_backup.columns)]
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive")
                df_backup.to_sql('archive', conn, if_exists='append', index=False)
            st.success("복구 완료!")
            st.rerun()
        except Exception as e: st.error(f"오류: {e}")

# --- [3. 상세 팝업] ---
@st.dialog("📋 상세 정보", width="large")
def show_details(item):
    st.markdown(f'<div class="title-text">{str(item.get("title") or "제목 없음")}</div>', unsafe_allow_html=True)
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
    with col_r:
        st.markdown(f'<p class="date-text">🍿 감상일: {item.get("view_date") or item.get("save_date")}</p>', unsafe_allow_html=True)
        st.write(f"**Creator:** {item.get('creator')} | **공개일:** {item.get('rel_date')}")
        st.divider()
        note_text = str(item.get('note') or "").replace("KM", "km").replace("BPM", "bpm")
        note_text = re.sub(r'(\d+)\s*(km|bpm)', r'<span class="num-text">\1</span> \2', note_text)
        if item.get('brief'): st.success(item['brief'])
        st.markdown(note_text, unsafe_allow_html=True)

# --- [4. 메인 화면] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

# --- [WRITE PART] ---
with tab1:
    category = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_q = st.text_input(f"🔍 {category} 검색")
    
    # 검색 결과 처리 (예시: BOOKS)
    if search_q and category == "BOOKS":
        books = search_books(search_q)
        if books:
            sel_b = st.selectbox("책 선택", books, format_func=lambda x: x['title'])
            if st.button("가져오기"):
                st.session_state.temp_data = {'title': sel_b['title'], 'creator': ",".join(sel_b['authors']), 'img': sel_b['thumbnail'], 'summary': sel_b['contents']}
    
    temp = st.session_state.get('temp_data', {})
    
    with st.form("main_form"):
        c1, c2 = st.columns([0.4, 0.6])
        with c1:
            f_title = st.text_input("제목", value=temp.get('title', ''))
            f_creator = st.text_input("창작자", value=temp.get('creator', ''))
            f_img = st.text_input("이미지 URL", value=temp.get('img', ''))
            if f_img: st.image(f_img, width=150)
        with c2:
            f_view_date = st.date_input("감상일", date.today())
            f_brief = st.text_input("요약")
            f_note = st.text_area("감상 (km, bpm 자동변환)")
            f_summary = st.text_area("줄거리/정보", value=temp.get('summary', ''))
        
        if st.form_submit_button("✅ 저장 및 백업"):
            processed_note = f_note.replace("KM", "km").replace("BPM", "bpm")
            # 로컬 DB 저장
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("""INSERT INTO archive 
                    (category, title, creator, rel_date, summary, brief, note, img_url, save_date, view_date) 
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (category, f_title, f_creator, "", f_summary, f_brief, processed_note, f_img, str(date.today()), str(f_view_date)))
            
            # 구글 설문지 백업 (기존 URL 사용)
            BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
            payload = {"entry.574529989": category, "entry.898076783": f_title, "entry.345368346": f_creator, "entry.891180756": processed_note}
            try: requests.post(BACKUP_URL, data=payload)
            except: pass
            
            st.success("저장되었습니다!")
            st.rerun()

# --- [ARCHIVE PART] ---
with tab2:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    if not all_df.empty:
        all_df['temp_date'] = pd.to_datetime(all_df['view_date'].replace("", None), errors='coerce').fillna(
                              pd.to_datetime(all_df['save_date'].replace("", None), errors='coerce'))
        all_df = all_df.sort_values(by='temp_date', ascending=False)

        # 연도별 보기 (디자인 가이드 반영)
        all_df['year'] = all_df['temp_date'].dt.year.fillna("기타")
        all_df['month'] = all_df['temp_date'].dt.month.fillna(0)
        
        years = sorted([y for y in all_df['year'].unique() if y != "기타"], reverse=True)
        sel_y = st.selectbox("연도 선택", years)
        
        y_data = all_df[all_df['year'] == sel_y]
        for m in range(12, 0, -1):
            m_data = y_data[y_data['month'] == m]
            if not m_data.empty:
                st.subheader(f"🗓️ {m}월")
                items = m_data.to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i + j < len(items):
                            row = items[i + j]
                            with cols[j]:
                                img_url = row.get('img_url') or "https://via.placeholder.com/300"
                                st.markdown(f'''<div class="cal-img-box">
                                    <div class="badge badge-left">{row.get('category')}</div>
                                    <img src="{img_url}"></div>''', unsafe_allow_html=True)
                                if st.button(f"{str(row.get('title'))[:7]}", key=f"btn_{row['id']}"):
                                    show_details(row)
    else: st.info("데이터가 없습니다.")
