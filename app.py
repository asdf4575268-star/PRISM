import streamlit as st
import sqlite3
import pandas as pd
import calendar
from datetime import date, datetime

# --- [1. 설정 및 스타일] ---
st.set_page_config(layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    /* 사용자 요청 폰트 설정 */
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; }
    
    /* 달력 이미지 박스 */
    .cal-img-container {
        width: 100%;
        aspect-ratio: 1/1;
        overflow: hidden;
        border-radius: 8px;
        margin-bottom: 5px;
        border: 1px solid #eee;
    }
    .cal-img-container img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db'

# --- [2. 데이터 및 세션 관리] ---
if 'cal_year' not in st.session_state:
    st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state:
    st.session_state.cal_month = datetime.now().month
if 'selected_rec' not in st.session_state:
    st.session_state.selected_rec = None

def shift_month(delta):
    new_month = st.session_state.cal_month + delta
    if new_month > 12:
        st.session_state.cal_month = 1; st.session_state.cal_year += 1
    elif new_month < 1:
        st.session_state.cal_month = 12; st.session_state.cal_year -= 1
    else:
        st.session_state.cal_month = new_month

# --- [3. 메인 달력 화면] ---
st.title("📂 ARCHIVE CALENDAR")

with sqlite3.connect(DB_NAME) as conn:
    df = pd.read_sql_query("SELECT * FROM archive", conn)

if df.empty:
    st.info("저장된 기록이 없습니다.")
else:
    df['save_date'] = pd.to_datetime(df['save_date'], errors='coerce')
    df = df.dropna(subset=['save_date'])

    # 상단 내비게이션
    col_prev, col_title, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("◀ 이전달"): shift_month(-1); st.rerun()
    with col_title:
        st.markdown(f"<h3 style='text-align:center;'>{st.session_state.cal_year}년 {st.session_state.cal_month}월</h3>", unsafe_allow_html=True)
    with col_next:
        if st.button("다음달 ▶"): shift_month(1); st.rerun()

    # 달력 데이터 필터링
    month_df = df[(df['save_date'].dt.year == st.session_state.cal_year) & 
                  (df['save_date'].dt.month == st.session_state.cal_month)].copy()

    # 요일 헤더
    days_ko = ["월", "화", "수", "목", "금", "토", "일"]
    cols = st.columns(7)
    for i, d in enumerate(days_ko):
        color = "#2E5BFF" if i == 5 else "#FF4B4B" if i == 6 else "#888"
        cols[i].markdown(f"<p style='text-align:center; font-weight:bold; color:{color};'>{d}</p>", unsafe_allow_html=True)

    # 달력 날짜 렌더링
    cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
    for week in cal:
        w_cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                w_cols[i].write(""); continue
            
            with w_cols[i]:
                # 오늘 날짜 표시용
                is_today = (st.session_state.cal_year == datetime.now().year and 
                            st.session_state.cal_month == datetime.now().month and day == datetime.now().day)
                d_color = "#FF4B4B" if is_today or i == 6 else "#2E5BFF" if i == 5 else "#333"
                
                st.markdown(f"<p style='margin:0; font-size:14px; color:{d_color};'>{day}</p>", unsafe_allow_html=True)
                
                day_items = month_df[month_df['save_date'].dt.day == day]
                
                if not day_items.empty:
                    # 첫 번째 이미지 표시
                    m_row = day_items.iloc[0]
                    if m_row['img_url']:
                        st.markdown(f'<div class="cal-img-container"><img src="{m_row["img_url"]}"></div>', unsafe_allow_html=True)
                    
                    # 제목 리스트 (클릭 시 관리모드)
                    for _, row in day_items.iterrows():
                        title_cut = row['title'][:5] + ".." if len(row['title']) > 6 else row['title']
                        if st.button(f"• {title_cut}", key=f"btn_{row['id']}", use_container_width=True):
                            st.session_state.selected_rec = row
                            st.rerun()
                else:
                    # 빈 칸 크기 유지
                    st.markdown("<div style='height:100px;'></div>", unsafe_allow_html=True)

# --- [4. 하단 관리 패널] ---
if st.session_state.selected_rec is not None:
    rec = st.session_state.selected_rec
    st.divider()
    
    # 🔍 관리 레이아웃
    c1, c2, c3 = st.columns([0.3, 0.4, 0.3])
    
    with c1:
        if rec['img_url']: st.image(rec['img_url'], width=150)
        st.subheader(rec['title'])
    
    with c2:
        st.markdown("### 📅 날짜 이동")
        new_date = st.date_input("변경할 날짜를 선택하세요", value=rec['save_date'].to_pydatetime().date())
        if st.button("이 날짜로 이동 확정", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("UPDATE archive SET save_date=? WHERE id=?", (new_date.strftime('%Y-%m-%d'), rec['id']))
            st.session_state.selected_rec = None
            st.success("이동되었습니다.")
            st.rerun()

    with c3:
        st.markdown("### ⚠️ 관리")
        if st.button("🗑️ 이 기록 삭제", type="primary", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (rec['id'],))
            st.session_state.selected_rec = None
            st.warning("삭제되었습니다.")
            st.rerun()
        
        if st.button("취소/닫기", use_container_width=True):
            st.session_state.selected_rec = None
            st.rerun()
