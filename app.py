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

# --- [비상 복구 시스템 - 사이드바 정렬] ---
with st.sidebar:
    st.header("🛠️ 시스템 설정")
    recovery_url = st.text_input("구글 시트 CSV 링크 (웹에 게시)")
    
    if st.button("🔄 데이터 강제 동기화", use_container_width=True):
        if recovery_url:
            try:
                # 데이터 유실 방지를 위해 모든 데이터를 일단 문자열로 로드
                df_backup = pd.read_csv(recovery_url, dtype=str).fillna("")
                
                # 사용자가 요청한 11개 열 순서 강제 매핑
                # 타임스탬프(0), category(1), title(2), creator(3), 공개일(4), summary(5), brief(6), highlights(7), note(8), img_url(9), 감상일(10)
                expected_cols = ['save_date', 'category', 'title', 'creator', 'rel_date', 'summary', 'brief', 'highlights', 'note', 'img_url', 'view_date']
                
                # 실제 가져온 데이터의 열 개수에 맞춰 이름 할당
                df_backup.columns = expected_cols[:len(df_backup.columns)]
                
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive")
                    df_backup.to_sql('archive', conn, if_exists='append', index=False)
                
                st.success(f"✅ {len(df_backup)}개의 데이터 복구 완료!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"복구 중 오류 발생: {e}")
        else:
            st.warning("링크를 입력해주세요.")

# --- [상세 보기 팝업] ---
@st.dialog("📋 기록 상세", width="large")
def show_details(item):
    # 제목 90px 적용
    st.markdown(f'<div class="title-text">{str(item.get("title") or "제목 없음")}</div>', unsafe_allow_html=True)
    
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        else: st.info("사진이 없습니다.")
    
    with col_r:
        # 날짜 30px 적용
        st.markdown(f'<p class="date-text">🍿 감상일: {item.get("view_date") or item.get("save_date")}</p>', unsafe_allow_html=True)
        st.write(f"**Creator:** {item.get('creator')} | **공개일:** {item.get('rel_date')}")
        st.divider()
        
        # 감상평 (KM/BPM 소문자 및 숫자 60px 적용)
        note_text = str(item.get('note') or "")
        note_text = note_text.replace("KM", "km").replace("BPM", "bpm")
        # 숫자 뒤에 km/bpm이 붙는 경우 강조
        note_text = re.sub(r'(\d+)\s*(km|bpm)', r'<span class="num-text">\1</span> \2', note_text)
        
        if item.get('brief'): st.success(item['brief'])
        st.markdown(note_text, unsafe_allow_html=True)
        if item.get('summary'): 
            with st.expander("줄거리 보기"): st.write(item['summary'])

# --- [메인 아카이브 화면] ---
st.title("🌈 PRISM")

with sqlite3.connect(DB_NAME) as conn:
    all_df = pd.read_sql_query("SELECT * FROM archive", conn)

if not all_df.empty:
    # 날짜 정렬 처리 (감상일 -> 저장일 순)
    all_df['temp_date'] = pd.to_datetime(all_df['view_date'].replace("", None), errors='coerce').fillna(
                          pd.to_datetime(all_df['save_date'].replace("", None), errors='coerce'))
    all_df = all_df.sort_values(by='temp_date', ascending=False)

    tab_yr, tab_cat = st.tabs(["📅 YEARLY", "📂 CATEGORY"])

    with tab_yr:
        # 연도/월 추출 (날짜가 깨진 경우 "알 수 없음" 처리)
        all_df['year'] = all_df['temp_date'].dt.year.fillna("기타")
        all_df['month'] = all_df['temp_date'].dt.month.fillna(0)
        
        years = sorted([y for y in all_df['year'].unique() if y != "기타"], reverse=True)
        if "기타" in all_df['year'].unique(): years.append("기타")
        
        sel_y = st.selectbox("연도 선택", years)
        y_data = all_df[all_df['year'] == sel_y]
        
        # 월별로 루프
        months = sorted(y_data['month'].unique(), reverse=True)
        for m in months:
            m_title = f"{int(m)}월" if m > 0 else "날짜 미기입"
            st.subheader(f"🗓️ {m_title}")
            m_data = y_data[y_data['month'] == m]
            
            # 6열 그리드로 사진 배치
            items = m_data.to_dict('records')
            for i in range(0, len(items), 6):
                cols = st.columns(6)
                for j in range(6):
                    if i + j < len(items):
                        row = items[i + j]
                        with cols[j]:
                            # 1. 뱃지 날짜 계산
                            try: d_val = f"{pd.to_datetime(row['view_date']).day}일"
                            except: d_val = "확인"
                            
                            # 2. 이미지 출력
                            img_url = row.get('img_url') if row.get('img_url') else "https://via.placeholder.com/300x400?text=No+Image"
                            st.markdown(f'''
                                <div class="cal-img-box">
                                    <div class="badge badge-left">{row.get('category', '기타')}</div>
                                    <div class="badge badge-right">{d_val}</div>
                                    <img src="{img_url}">
                                </div>''', unsafe_allow_html=True)
                            
                            # 3. 버튼 (TypeError 방지용 str 변환 및 슬라이싱)
                            b_title = str(row.get('title') or "제목없음")
                            if st.button(f"{b_title[:7]}..", key=f"btn_{row['id']}"):
                                show_details(row)
            st.divider()

    with tab_cat:
        cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sel_c = st.pills("카테고리 필터", cats) # 2026년 기준 최신 UI 구성요소
        if sel_c:
            c_data = all_df[all_df['category'] == sel_c]
            if not c_data.empty:
                items = c_data.to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i + j < len(items):
                            row = items[i + j]
                            with cols[j]:
                                st.image(row.get('img_url') or "https://via.placeholder.com/150")
                                if st.button(f"{str(row.get('title'))[:7]}", key=f"c_btn_{row['id']}"):
                                    show_details(row)
            else: st.info(f"{sel_c} 데이터가 없습니다.")
else:
    st.info("데이터가 없습니다. 사이드바에서 복구 링크를 입력해 주세요.")
