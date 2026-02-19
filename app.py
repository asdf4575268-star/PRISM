import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; line-height: 1; }
    
    /* 정사각형 이미지 박스 공통 스타일 */
    .square-img-box { 
        width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:10px; 
        background-color: #f0f0f0; margin-bottom: 8px;
    }
    .square-img-box img { width:100%; height:100%; object-fit:cover; }

    .cal-img-box { 
        width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:4px; 
        margin-bottom:4px; border: 1px solid #eee; 
    }
    .cal-img-box img { width:100%; height:100%; object-fit:cover; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db'
TTB_KEY = "ttbckwntmd2101001"
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                        rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
        try: conn.execute("ALTER TABLE archive ADD COLUMN view_date TEXT")
        except: pass

init_db()

# --- [2. 상세 정보 및 수정 팝업] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    edit_mode = st.toggle("✏️ 수정 모드 켜기", key=f"tog_{item['id']}")

    if edit_mode:
        with st.form(key=f"edit_form_{item['id']}", clear_on_submit=False):
            col_img, col_txt = st.columns([0.3, 0.7]) # 이미지 영역 비율 살짝 축소
            with col_img:
                if item['img_url']:
                    # 수정 폼 내 이미지도 정사각형 정렬
                    st.markdown(f'<div class="square-img-box"><img src="{item["img_url"]}"></div>', unsafe_allow_html=True)
                # 요청사항: 이미지 URL 입력란 제거
                new_img = item['img_url'] 
            with col_txt:
                new_title = st.text_input("📌 제목", value=item['title'])
                new_creator = st.text_input("👤 창작자", value=item['creator'])
                new_rel_date = st.text_input("📅 작품 날짜", value=item['rel_date'])
                
                cur_v = datetime.strptime(item.get('view_date') or item['save_date'], '%Y-%m-%d').date() if item.get('view_date') or item.get('save_date') else date.today()
                new_view_date = st.date_input("🍿 감상일 수정", value=cur_v)
                
                new_brief = st.text_input("📝 요약", value=item['brief'])
                new_summary = st.text_area("📖 작품 소개", value=item['summary'], height=120)
                new_highlights = st.text_area("✨ 인상 깊은 부분", value=item['highlights'], height=100)
                new_note = st.text_area("💬 감상", value=item['note'], height=100)
                
                if st.form_submit_button("💾 변경사항 저장", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, 
                                        brief=?, highlights=?, note=?, img_url=?, view_date=? WHERE id=?""",
                                     (new_title, new_creator, new_rel_date, new_summary, 
                                      new_brief, new_highlights, new_note, new_img, str(new_view_date), int(item['id'])))
                    st.rerun()
    else:
        col_img, col_txt = st.columns([0.4, 0.6])
        with col_img:
            if item['img_url']: st.image(item['img_url'], use_container_width=True)
        with col_txt:
            st.markdown(f'<p class="act-name">{item["title"]}</p>', unsafe_allow_html=True)
            st.write(f"**정보:** {item['creator']} | **작품날짜:** {item['rel_date']}")
            v_date = item.get('view_date') if item.get('view_date') else item['save_date']
            st.markdown(f'<p class="date-text">🍿 감상일: {v_date}</p>', unsafe_allow_html=True)
            st.divider()
            if item['brief']: st.success(f"**📝 요약:** {item['brief']}")
            st.info(f"**📖 작품 소개:**\n\n{item['summary']}")
            st.warning(f"**✨ 인상 깊은 부분:**\n\n{item['highlights']}")
            st.write(f"**💬 감상:**\n\n{item['note']}")
            
            if st.button("🗑️ 기록 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
                st.rerun()

# --- [API 함수 수정] ---
def search_books(query, category="BOOKS"):
    target = "Book"
    if category == "MUSIC": target = "Music"
    elif category in ["MOVIES", "SERIES", "STAGE"]: target = "DVD"
    
    url = "http://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
    params = {
        'ttbkey': TTB_KEY, 'Query': query, 'QueryType': 'Title',
        'MaxResults': 10, 'start': 1, 'SearchTarget': target, 'output': 'js', 'Version': '20131101'
    }
    try:
        res = requests.get(url, params=params)
        return res.json().get("item", []) if res.status_code == 200 else []
    except: return []

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        if category == "BOOKS":
            res = search_books(search_query, "BOOKS")
            if res:
                opts = {f"📚 {b['title']}": b for b in res}
                sel = st.selectbox("검색 결과", list(opts.keys()), key="book_sel")
                if st.button("✨ 가져오기", key="book_btn"):
                    b = opts[sel]
                    
                    # --- [선명도 업그레이드 치트키] ---
                    # 아주 작은 'coversum'을 중간 크기인 'cover200'으로 교체합니다.
                    raw_img = b.get('cover', '')
                    better_img = raw_img.replace('/coversum/', '/cover200/')
                    
                    st.session_state.api_data = {
                        'title': b.get('title', ''),
                        'creator': b.get('author', ''), 
                        'date': b.get('pubDate', '')[:10], 
                        'img': better_img, # 더 선명한 이미지 적용!
                        'summary': b.get('description', '')
                    }
                    st.rerun()
        # ... (MUSIC, STAGE, TMDB 로직 생략 - 필요시 위와 같은 get() 패턴 적용)
        elif category == "MUSIC":
            res = search_books(search_query, "MUSIC") # 알라딘 뮤직 검색 사용
            if res:
                opts = {f"🎵 {b['title']}": b for b in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': b.get('author',''), 'date': b.get('pubDate','')[:10], 'img': b.get('cover',''), 'summary': ''}
                    st.rerun()
        # ... (나머지 카테고리 로직 동일하게 적용)

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("이미지 URL", value=data.get('img', ''))
        if img_url_val:
            # 미리보기 이미지도 정사각형
            st.markdown(f'<div class="square-img-box"><img src="{img_url_val}"></div>', unsafe_allow_html=True)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 정보", value=data.get('creator', ''))
        
        col1, col2 = st.columns(2)
        rel_date = col1.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        view_date = col2.date_input("🍿 감상일", value=date.today())
        
    with cr:
        summary = st.text_area("📖 작품 소개", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        if st.button("✅ 저장", key="final_save", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
            st.success("저장 완료!")
            st.session_state.api_data = {}
            st.rerun()

# --- TAB 2: ARCHIVE ---
with tab2:
    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])
    
    # ... (YEARLY 달력 로직은 기존 코드 유지)
    with sub_tabs[0]:
        with sqlite3.connect(DB_NAME) as conn:
            all_df = pd.read_sql_query("SELECT * FROM archive", conn)
        if not all_df.empty:
            all_df['view_date_filled'] = all_df['view_date'].fillna(all_df['save_date'])
            all_df['v_dt'] = pd.to_datetime(all_df['view_date_filled'])
            all_df['year_int'] = all_df['v_dt'].dt.year
            
            year_counts = all_df['year_int'].value_counts().to_dict()
            unique_years = sorted(list(set([datetime.now().year] + list(year_counts.keys()))), reverse=True)
            year_labels = [f"{y} ({year_counts.get(y, 0)})" for y in unique_years]
            label_to_year = {label: y for label, y in zip(year_labels, unique_years)}
            default_idx = unique_years.index(st.session_state.cal_year) if st.session_state.cal_year in unique_years else 0
            
            c_yr, c_nav = st.columns([1.5, 3])
            with c_yr:
                selected_label = st.selectbox("연도 선택", year_labels, index=default_idx)
                selected_year = label_to_year[selected_label]
                if selected_year != st.session_state.cal_year:
                    st.session_state.cal_year = selected_year
                    st.rerun()

            _, n1, n2, n3, _ = st.columns([1.5, 1, 2, 1, 1.5])
            with n1:
                st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)
                if st.button("◀ 이전달", use_container_width=True): shift_month(-1); st.rerun()
            with n2:
                st.markdown(f"<div style='text-align:center;' class='num-text'>{st.session_state.cal_year} / {st.session_state.cal_month}</div>", unsafe_allow_html=True)
            with n3:
                st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)
                if st.button("다음달 ▶", use_container_width=True): shift_month(1); st.rerun()

            days = ["월", "화", "수", "목", "금", "토", "일"]
            h_cols = st.columns(7)
            for i, d in enumerate(days):
                color = "#2E5BFF" if i == 5 else "#FF4B4B" if i == 6 else "#888"
                h_cols[i].markdown(f"<p style='text-align:center; font-weight:bold; color:{color};'>{d}</p>", unsafe_allow_html=True)

            cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
            month_df = all_df[(all_df['v_dt'].dt.year == st.session_state.cal_year) & (all_df['v_dt'].dt.month == st.session_state.cal_month)]

            for week in cal:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day == 0: continue
                    with cols[i]:
                        st.markdown(f"<p class='num-text' style='font-size:30px; margin:0;'>{day}</p>", unsafe_allow_html=True)
                        day_items = month_df[month_df['v_dt'].dt.day == day]
                        if not day_items.empty:
                            first_item = day_items.iloc[0]
                            if first_item['img_url']:
                                st.markdown(f'<div class="cal-img-box"><img src="{first_item["img_url"]}"></div>', unsafe_allow_html=True)
                            for _, r in day_items.iterrows():
                                if st.button(f"• {r['title'][:5]}", key=f"cal_{r['id']}", use_container_width=True):
                                    show_details(r)
                        else: st.markdown("<div style='height:80px;'></div>", unsafe_allow_html=True)

    # --- [카테고리별 탭 이미지 정사각형 수정] ---
    cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
    for idx, c_name in enumerate(cats):
        with sub_tabs[idx+1]:
            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{c_name}' ORDER BY id DESC", conn)
            if not df.empty:
                cols = st.columns(4) 
                for i, row in df.iterrows():
                    with cols[i % 4]:
                        if row['img_url']:
                            # 통합 스타일 square-img-box 적용
                            st.markdown(f'<div class="square-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                        
                        v_date_display = row.get('view_date') if row.get('view_date') else row.get('save_date', '')
                        st.markdown(f'<p class="date-text" style="font-size:15px; text-align:center;">🍿 {v_date_display}</p>', unsafe_allow_html=True)
                        
                        if st.button(row['title'], key=f"list_{row['id']}", use_container_width=True):
                            show_details(row)









