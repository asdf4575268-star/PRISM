import streamlit as st
import sqlite3
import requests
import pandas as pd
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
    
    /* 디자인 가이드 반영 */
    .title-text { font-family: 'Jolly Lodger', cursive; font-size: 90px; line-height: 1.1; color: #111; }
    .date-text { font-family: 'Kirang Haerang', cursive; font-size: 30px; color: #555; }
    .num-text { font-family: 'Lacquer', sans-serif; font-size: 60px; color: #FF4B4B; vertical-align: middle; }
    
    /* 그리드 및 이미지 레이아웃 */
    div[data-testid="column"] { display: flex; flex-direction: column; align-items: center; text-align: center !important; }
    .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.3; overflow: hidden; border-radius: 12px; margin-bottom: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); border: 1px solid #eee; background: #fff; }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }
    .cal-img-box img:hover { transform: scale(1.05); }
    .badge { position: absolute; top: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 3px 8px; border-radius: 6px; font-size: 11px; z-index: 10; font-weight: bold; }
    .badge-left { left: 8px; } 
    .badge-right { right: 8px; background: #FF4B4B; } 
    </style>
""", unsafe_allow_html=True)

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# --- [2. 사이드바: 복구 및 설정] ---
with st.sidebar:
    st.header("🛠️ SYSTEM MENU")
    with st.expander("데이터 복구 및 동기화", expanded=False):
        recovery_url = st.text_input("구글 시트 CSV 링크")
        if st.button("🔄 전체 데이터 강제 복구", use_container_width=True):
            try:
                # 11개 열 순서: 타임스탬프, category, title, creator, 공개일, summary, brief, highlights, note, img_url, 감상일
                df_backup = pd.read_csv(recovery_url, dtype=str).fillna("")
                expected_cols = ['save_date', 'category', 'title', 'creator', 'rel_date', 'summary', 'brief', 'highlights', 'note', 'img_url', 'view_date']
                df_backup.columns = expected_cols[:len(df_backup.columns)]
                
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive")
                    df_backup.to_sql('archive', conn, if_exists='append', index=False)
                st.success("✅ 복구 완료!")
                st.rerun()
            except Exception as e: st.error(f"오류: {e}")

# --- [3. 상세 팝업 함수] ---
@st.dialog("📋 ARCHIVE DETAIL", width="large")
def show_details(item):
    # 활동명(제목) 90px
    st.markdown(f'<div class="title-text">{str(item.get("title") or "NO TITLE")}</div>', unsafe_allow_html=True)
    
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        else: st.info("이미지가 없습니다.")
    
    with col_r:
        # 감상일 30px
        v_date = item.get('view_date') or item.get('save_date')
        st.markdown(f'<p class="date-text">🍿 WATCHED ON: {v_date}</p>', unsafe_allow_html=True)
        st.caption(f"**CREATOR:** {item.get('creator')} | **RELEASE:** {item.get('rel_date')}")
        st.divider()
        
        # 감상평 km/bpm 소문자 변환 및 숫자 60px
        raw_note = str(item.get('note') or "")
        processed_note = raw_note.replace("KM", "km").replace("BPM", "bpm")
        # 숫자 + km/bpm 패턴 찾아서 숫자만 60px 적용
        highlighted_note = re.sub(r'(\d+)\s*(km|bpm)', r'<span class="num-text">\1</span> \2', processed_note)
        
        if item.get('brief'): st.success(item['brief'])
        st.markdown(highlighted_note, unsafe_allow_html=True)
        
        if item.get('highlights'): 
            with st.expander("✨ Highlights"): st.write(item['highlights'])

# --- [4. 메인 화면 구성] ---
st.title("🌈 PRISM")

tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    cat = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    
    with st.form("write_form"):
        w_c1, w_c2 = st.columns([0.4, 0.6])
        with w_c1:
            w_title = st.text_input("제목")
            w_creator = st.text_input("창작자")
            w_img = st.text_input("이미지 URL")
            if w_img: st.image(w_img, width=200)
        with w_c2:
            w_view_date = st.date_input("감상일", date.today())
            w_brief = st.text_input("한 줄 요약")
            w_note = st.text_area("감상 (km, bpm은 소문자로 기록됩니다)", height=200)
            w_summary = st.text_area("정보/줄거리", height=100)
        
        if st.form_submit_button("💾 기록 저장 및 백업"):
            final_note = w_note.replace("KM", "km").replace("BPM", "bpm")
            # 로컬 저장
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("""INSERT INTO archive (category, title, creator, summary, brief, note, img_url, save_date, view_date) 
                             VALUES (?,?,?,?,?,?,?,?,?)""",
                             (cat, w_title, w_creator, w_summary, w_brief, final_note, w_img, str(date.today()), str(w_view_date)))
            
            # 구글 백업 (선택사항: 필요시 활성화)
            BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
            try: requests.post(BACKUP_URL, data={"entry.574529989": cat, "entry.898076783": w_title, "entry.891180756": final_note})
            except: pass
            
            st.success("✅ 저장 완료!")
            st.rerun()

with tab2:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)
    
    if not all_df.empty:
        # 정렬 로직
        all_df['temp_date'] = pd.to_datetime(all_df['view_date'].replace("", None), errors='coerce').fillna(
                              pd.to_datetime(all_df['save_date'].replace("", None), errors='coerce'))
        all_df = all_df.sort_values(by='temp_date', ascending=False)
        
        # 필터링 및 연도별 구성
        all_df['year'] = all_df['temp_date'].dt.year.fillna("기타")
        all_df['month'] = all_df['temp_date'].dt.month.fillna(0)
        
        years = sorted([y for y in all_df['year'].unique() if y != "기타"], reverse=True)
        sel_y = st.selectbox("연도 선택", years if years else ["기타"])
        
        y_data = all_df[all_df['year'] == sel_y]
        for m in range(12, 0, -1):
            m_data = y_data[y_data['month'] == m]
            if not m_data.empty:
                st.subheader(f"🗓️ {int(m)}월")
                items = m_data.to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i + j < len(items):
                            row = items[i+j]
                            with cols[j]:
                                # 뱃지용 일자 추출
                                try: d_val = f"{pd.to_datetime(row['view_date']).day}일"
                                except: d_val = "!"
                                
                                img_src = row.get('img_url') if row.get('img_url') else "https://via.placeholder.com/300x400"
                                st.markdown(f'''
                                    <div class="cal-img-box">
                                        <div class="badge badge-left">{row.get('category')}</div>
                                        <div class="badge badge-right">{d_val}</div>
                                        <img src="{img_src}">
                                    </div>''', unsafe_allow_html=True)
                                
                                # 버튼 (제목 짤림 방지)
                                b_title = str(row.get('title') or "제목없음")
                                if st.button(f"{b_title[:7]}..", key=f"btn_{row['id']}"):
                                    show_details(row)
                st.divider()
    else:
        st.info("기록된 데이터가 없습니다. WRITE 탭에서 첫 기록을 시작하거나 사이드바에서 복구하세요!")
