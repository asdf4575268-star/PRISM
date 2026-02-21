import streamlit as st
import sqlite3
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time
import os

# --- [0. DB 설정] ---
os.makedirs('data', exist_ok=True)
DB_NAME = 'data/archive_prism_total_v4.db'

# --- [1. 스타일 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Jolly+Lodger&family=Kirang+Haerang&family=Lacquer&display=swap');
    .title-text { font-family: 'Jolly Lodger', cursive; font-size: 90px; line-height: 1.1; }
    .date-text { font-family: 'Kirang Haerang', cursive; font-size: 30px; }
    .num-text { font-family: 'Lacquer', sans-serif; font-size: 60px; color: #E74C3C; }
    div[data-testid="column"] { display: flex; flex-direction: column; align-items: center; text-align: center !important; }
    .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1; overflow: hidden; border-radius: 10px; margin-bottom: 5px; border: 1px solid #eee; }
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

# --- [비상 복구 시스템] ---
with st.sidebar:
    st.header("🛠️ 데이터 복구 센터")
    recovery_url = st.text_input("구글 시트 CSV 링크")
    
    if st.button("🔄 전체 데이터 강제 복구", use_container_width=True):
        try:
            # CSV 읽기 (모든 데이터를 일단 문자열로 읽어 유실 방지)
            df_backup = pd.read_csv(recovery_url, dtype=str).fillna("")
            
            # 사용자 요청 순서에 따른 열 이름 매핑
            # 1.타임스탬프 2.category 3.title 4.creator 5.공개일 6.summary 7.brief 8.highlights 9.note 10.img_url 11.감상일
            df_backup.columns = ['save_date', 'category', 'title', 'creator', 'rel_date', 'summary', 'brief', 'highlights', 'note', 'img_url', 'view_date']
            
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive")
                df_backup.to_sql('archive', conn, if_exists='append', index=False)
            
            st.success(f"✅ {len(df_backup)}개의 데이터를 성공적으로 불러왔습니다!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"복구 에러: {e}")

# --- [상세 팝업] ---
@st.dialog("📋 기록 보기", width="large")
def show_details(item):
    st.markdown(f'<div class="title-text">{item["title"]}</div>', unsafe_allow_html=True)
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if item['img_url']: st.image(item['img_url'], use_container_width=True)
    with col_r:
        st.markdown(f'<p class="date-text">🍿 감상일: {item["view_date"]}</p>', unsafe_allow_html=True)
        st.write(f"**Creator:** {item['creator']} | **공개일:** {item['rel_date']}")
        st.divider()
        if item['brief']: st.info(item['brief'])
        
        # 숫자 및 km/bpm 변환 적용
        note_display = item['note'].replace("KM", "km").replace("BPM", "bpm")
        note_display = re.sub(r'(\d+)\s*(km|bpm)', r'<span class="num-text">\1</span> \2', note_display)
        st.markdown(note_display, unsafe_allow_html=True)

# --- [메인 아카이브] ---
st.title("🌈 PRISM ARCHIVE")

with sqlite3.connect(DB_NAME) as conn:
    all_df = pd.read_sql_query("SELECT * FROM archive", conn)

if not all_df.empty:
    # 날짜 정렬용 임시 열 생성 (감상일이 없으면 저장일로 보완)
    all_df['temp_date'] = pd.to_datetime(all_df['view_date'].replace("", None), errors='coerce').fillna(
                          pd.to_datetime(all_df['save_date'].replace("", None), errors='coerce'))
    # 정렬 (최신순)
    all_df = all_df.sort_values(by='temp_date', ascending=False)

    tab_yr, tab_cat = st.tabs(["📅 연도별 보기", "📂 카테고리별"])

    with tab_yr:
        all_df['year'] = all_df['temp_date'].dt.year.fillna("Unknown")
        all_df['month'] = all_df['temp_date'].dt.month.fillna(0)
        
        years = [y for y in sorted(all_df['year'].unique(), reverse=True) if y != "Unknown"]
        if years:
            sel_y = st.selectbox("연도 선택", years)
            y_data = all_df[all_df['year'] == sel_y]
            
            for m in range(12, 0, -1):
                m_data = y_data[y_data['month'] == m]
                if not m_data.empty:
                    st.subheader(f"🗓️ {m}월")
                    cols = st.columns(6)
                    for idx, row in enumerate(m_data.to_dict('records')):
                        with cols[idx % 6]:
                            # 날짜 숫자만 추출
                            try: d_val = pd.to_datetime(row['view_date']).day
                            except: d_val = "!"
                            
                            img_url = row['img_url'] if row['img_url'] else "https://via.placeholder.com/150"
                            st.markdown(f'''
                                <div class="cal-img-box">
                                    <div class="badge badge-left">{row['category']}</div>
                                    <div class="badge badge-right">{d_val}일</div>
                                    <img src="{img_url}">
                                </div>''', unsafe_allow_html=True)
                            if st.button(f"{row['title'][:8]}", key=f"btn_{row['id']}"):
                                show_details(row)
        else:
            st.warning("날짜 정보가 있는 데이터가 없습니다.")

    with tab_cat:
        cat_list = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sel_c = st.segmented_control("카테고리", cat_list)
        if sel_c:
            c_data = all_df[all_df['category'] == sel_c]
            if not c_data.empty:
                cols = st.columns(6)
                for idx, row in enumerate(c_data.to_dict('records')):
                    with cols[idx % 6]:
                        st.image(row['img_url'] if row['img_url'] else "https://via.placeholder.com/150")
                        if st.button(f"{row['title'][:8]}", key=f"cat_{row['id']}"):
                            show_details(row)
            else: st.info("데이터가 없습니다.")

else:
    st.info("데이터가 없습니다. 사이드바에서 복구를 진행해 주세요.")
