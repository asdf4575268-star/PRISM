import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM", page_icon="🌈")

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    .act-name {{ font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }}
    .date-text {{ font-size: 30px; color: #666; margin: 0; }}
    .num-text {{ font-size: 50px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; line-height: 1; }}
    
    .cal-day-active {{
        border: 1px solid #eee;
        border-radius: 12px;
        padding: 10px;
        min-height: 160px;
        background-color: #ffffff;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }}
    
    .cal-day-empty {{
        padding: 10px;
        min-height: 160px;
        background-color: transparent;
        border: 1px solid transparent;
        margin-bottom: 10px;
    }}

    .cal-img-box {{ 
        width: 100%; 
        aspect-ratio: 1/1; 
        overflow: hidden; 
        border-radius: 8px; 
        margin: 8px 0; 
    }}
    .cal-img-box img {{ width: 100%; height: 100%; object-fit: cover; }}
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                         img_url TEXT, save_date TEXT, view_date TEXT)''')
        try: conn.execute("ALTER TABLE archive ADD COLUMN view_date TEXT")
        except: pass

init_db()

# 데이터 로드 함수 (캐시 없이 실시간 반영을 위해 분리)
def load_data():
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM archive", conn)
    if not df.empty:
        df['v_dt'] = pd.to_datetime(df['view_date'].fillna(df['save_date']))
        df = df.sort_values('v_dt', ascending=False)
    return df

# --- [2. 상세 정보 다이얼로그] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    edit_mode = st.toggle("✏️ 수정 모드 켜기", key=f"tog_{item['id']}")
    if edit_mode:
        with st.form(key=f"edit_form_{item['id']}"):
            col_img, col_txt = st.columns([0.4, 0.6])
            with col_img:
                if item['img_url']: st.image(item['img_url'], use_container_width=True)
            with col_txt:
                new_title = st.text_input("📌 제목", value=item['title'])
                new_creator = st.text_input("👤 창작자", value=item['creator'])
                new_rel_date = st.text_input("📅 작품 날짜", value=item['rel_date'])
                cur_v = datetime.strptime(item['view_date'], '%Y-%m-%d') if item.get('view_date') else date.today()
                new_view_date = st.date_input("🍿 실제 관람일", value=cur_v)
                new_brief = st.text_input("📝 요약", value=item['brief'])
                new_summary = st.text_area("📖 줄거리", value=item['summary'], height=120)
                new_highlights = st.text_area("✨ 인상 깊은 부분", value=item['highlights'], height=100)
                new_note = st.text_area("💬 감상", value=item['note'], height=100)
                if st.form_submit_button("💾 저장"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, brief=?, highlights=?, note=?, view_date=? WHERE id=?",
                                     (new_title, new_creator, new_rel_date, new_summary, new_brief, new_highlights, new_note, str(new_view_date), item['id']))
                    st.rerun()
    else:
        col_img, col_txt = st.columns([0.4, 0.6])
        with col_img:
            if item['img_url']: st.image(item['img_url'], use_container_width=True)
        with col_txt:
            st.markdown(f'<p class="act-name">{item["title"]}</p>', unsafe_allow_html=True)
            st.write(f"**정보:** {item['creator']} | **작품날짜:** {item['rel_date']}")
            v_date = item.get('view_date') if item.get('view_date') else item['save_date']
            st.markdown(f'<p class="date-text">🍿 관람일: {v_date}</p>', unsafe_allow_html=True)
            st.divider()
            if item['brief']: st.success(f"**📝 요약:** {item['brief']}")
            st.info(f"**📖 줄거리:**\n\n{item['summary']}")
            st.warning(f"**✨ 인상 깊은 부분:**\n\n{item['highlights']}")
            st.write(f"**💬 감상:**\n\n{item['note']}")
            if st.button("🗑️ 삭제"):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                st.rerun()

# --- [3. 세션 및 함수] ---
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month

@st.cache_data(ttl=3600)
def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

@st.cache_data(ttl=3600)
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

@st.cache_data(ttl=3600)
def search_tmdb(query, category):
    t = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{t}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    return requests.get(url).json().get("results", [])

# --- [4. 메인 화면] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    if search_query:
        if category == "BOOKS":
            res = search_books(search_query)
            if res:
                sel = st.selectbox("검색 결과", [f"📚 {b['title']}" for b in res])
                if st.button("✨ 가져오기"):
                    b = next(x for x in res if f"📚 {x['title']}" == sel)
                    st.session_state.api_data = {'title': b['title'], 'creator': f"저자: {', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b['thumbnail'], 'summary': b['contents']}
                    st.rerun()
        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                sel = st.selectbox("검색 결과", [f"🎭 {r['title']} ({r['venue']})" for r in res])
                if st.button("✨ 가져오기"):
                    s = next(x for x in res if f"🎭 {x['title']} ({x['venue']})" == sel)
                    st.session_state.api_data = {'title': s['title'], 'creator': f"공연장: {s['venue']}", 'date': s['date'], 'img': s['img'], 'summary': ''}
                    st.rerun()
        else:
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                sel = st.selectbox("검색 결과", [f"🎬 {r[t_key]}" for r in res])
                if st.button("✨ 가져오기"):
                    r = next(x for x in res if f"🎬 {x[t_key]}" == sel)
                    st.session_state.api_data = {'title': r[t_key], 'date': r.get('release_date', r.get('first_air_date')), 'img': f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}", 'summary': r.get('overview', '')}
                    st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url = data.get('img', '')
        if img_url: st.image(img_url, width=300)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자/공연장", value=data.get('creator', ''))
        col1, col2 = st.columns(2)
        rel_date = col1.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        view_date = col2.date_input("🍿 실제 관람일", value=date.today())
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        if st.button("✅ 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url, str(date.today()), str(view_date)))
            st.session_state.api_data = {}
            st.success("저장 완료!")
            st.rerun() # 저장 즉시 리런하여 데이터 새로고침 유도

좋은 아이디어네요! YEARLY (달력) 모드는 아무래도 날짜 중심이다 보니 연도 선택이 필수적이지만, 나머지 카테고리 탭은 내가 기록한 전체 데이터를 훑어보는 게 더 편할 수 있죠.

요청하신 대로 연도 선택 박스를 YEARLY 탭 안으로 이동시키고, 나머지 BOOKS, MOVIES 등의 탭에서는 연도 제한 없이 전체 기록이 나오도록 로직을 수정했습니다.

with tab2:
    # 실시간 데이터 로드
    all_df = load_data()
    
    if not all_df.empty:
        # 아카이브 내 서브 탭 구성
        sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])
        
        # --- [1. YEARLY 탭: 연도별 달력 보기] ---
        with sub_tabs[0]:
            # 연도 선택 필터를 달력 탭 안으로 이동
            years = sorted(all_df['v_dt'].dt.year.unique(), reverse=True)
            sel_year = st.selectbox("📅 연도 선택", years, index=0, key="year_filter")
            
            # 선택된 연도의 데이터만 필터링
            year_df = all_df[all_df['v_dt'].dt.year == sel_year]

            # 월 이동 컨트롤
            c1, c2, c3 = st.columns([1, 2, 1])
            if c1.button("◀", key="prev_btn"):
                st.session_state.cal_month -= 1
                if st.session_state.cal_month == 0: 
                    st.session_state.cal_month = 12; st.session_state.cal_year -= 1
                st.rerun()
            
            # 현재 달력 표시 (연도 선택과 세션 연도 동기화는 하지 않음 - 자유로운 탐색 위해)
            c2.markdown(f"<div class='num-text' style='text-align:center;'>{st.session_state.cal_year} . {st.session_state.cal_month}</div>", unsafe_allow_html=True)
            
            if c3.button("▶", key="next_btn"):
                st.session_state.cal_month += 1
                if st.session_state.cal_month == 13: 
                    st.session_state.cal_month = 1; st.session_state.cal_year += 1
                st.rerun()

            # 요일 헤더 및 달력 로직 (기존과 동일)
            h_cols = st.columns(7)
            for i, d in enumerate(["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]):
                color = "#FF4B4B" if i == 6 else "#2E5BFF" if i == 5 else "#333"
                h_cols[i].markdown(f"<p style='text-align:center; font-weight:bold; color:{color};'>{d}</p>", unsafe_allow_html=True)

            cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
            m_df = all_df[(all_df['v_dt'].dt.year == st.session_state.cal_year) & (all_df['v_dt'].dt.month == st.session_state.cal_month)]
            
            for week in cal:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day != 0:
                        with cols[i]:
                            d_items = m_df[m_df['v_dt'].dt.day == day]
                            box_class = "cal-day-active" if not d_items.empty else "cal-day-empty"
                            day_color = "#FF4B4B" if i == 6 else "#2E5BFF" if i == 5 else "#000"
                            
                            st.markdown(f"<div class='{box_class}'>", unsafe_allow_html=True)
                            st.markdown(f"<p class='num-text' style='font-size:25px; color:{day_color};'>{day}</p>", unsafe_allow_html=True)
                            if not d_items.empty:
                                if d_items.iloc[0]['img_url']: 
                                    st.markdown(f"<div class='cal-img-box'><img src='{d_items.iloc[0]['img_url']}'></div>", unsafe_allow_html=True)
                                for _, r in d_items.iterrows():
                                    if st.button(f"{r['title'][:5]}..", key=f"cal_{r['id']}", use_container_width=True): 
                                        show_details(r)
                            st.markdown(f"</div>", unsafe_allow_html=True)

        # --- [2. 카테고리 탭: 전체 기록 보기] ---
        cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        for idx, cn in enumerate(cats):
            with sub_tabs[idx+1]:
                # year_df가 아닌 all_df에서 카테고리만 필터링 (전체 데이터)
                c_df = all_df[all_df['category'] == cn]
                
                if not c_df.empty:
                    # 한 줄에 4개씩 포스터 배치
                    cols = st.columns(4)
                    for i, (record_idx, row) in enumerate(c_df.iterrows()):
                        with cols[i % 4]:
                            if row['img_url']: 
                                st.image(row['img_url'], use_container_width=True)
                            st.markdown(f"<p style='text-align:center; font-size:14px; color:#888;'>🍿 {row['view_date']}</p>", unsafe_allow_html=True)
                            if st.button(row['title'], key=f"list_{row['id']}", use_container_width=True): 
                                show_details(row)
                else:
                    st.info(f"{cn} 카테고리에 아직 기록이 없습니다.")
    else:
        st.info("기록이 없습니다. 첫 기록을 남겨보세요!")


