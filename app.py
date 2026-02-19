import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM", page_icon="🌈")

# 사용자 지정 폰트 및 스타일 적용
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    .act-name {{ font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }}
    .date-text {{ font-size: 30px; color: #666; margin: 0; }}
    /* 숫자 및 단위 소문자 고정 */
    .num-text {{ font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; line-height: 1; }}
    
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

def load_data():
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM archive", conn)
    if not df.empty:
        # 관람일이 없으면 저장일로 대체하여 정렬 기준 생성
        df['v_dt'] = pd.to_datetime(df['view_date'].fillna(df['save_date']))
        df = df.sort_values('v_dt', ascending=False)
    return df

# --- [API 연동 함수들] ---
@st.cache_data(ttl=3600)
def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

@st.cache_data(ttl=3600)
def get_tmdb_details(item_id, category):
    t_type = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{t_type}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    try:
        r = requests.get(url).json()
        director = ""
        if t_type == "movie":
            directors = [m['name'] for m in r.get('credits', {}).get('crew', []) if m['job'] == 'Director']
            director = f"감독: {', '.join(directors)}" if directors else ""
        else:
            creators = [c['name'] for c in r.get('created_by', [])]
            director = f"제작: {', '.join(creators)}" if creators else ""
        cast = [c['name'] for c in r.get('credits', {}).get('cast', [])[:3]]
        cast_str = f" / 출연: {', '.join(cast)}" if cast else ""
        return f"{director}{cast_str}".strip(" /")
    except: return ""

# --- [상세 정보 및 수정 다이얼로그] ---
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
                new_creator = st.text_input("👤 창작자/공연장", value=item['creator'])
                new_rel_date = st.text_input("📅 작품 날짜", value=item['rel_date'])
                
                # 관람일 수정 기능 (핵심)
                cur_v = datetime.strptime(item['view_date'], '%Y-%m-%d').date() if item.get('view_date') else date.today()
                new_view_date = st.date_input("🍿 실제 관람일 수정", value=cur_v)
                
                new_brief = st.text_input("📝 요약", value=item['brief'])
                new_summary = st.text_area("📖 줄거리", value=item['summary'], height=120)
                new_highlights = st.text_area("✨ 인상 깊은 부분", value=item['highlights'], height=100)
                new_note = st.text_area("💬 감상", value=item['note'], height=100)
                
                if st.form_submit_button("💾 변경사항 저장"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET 
                                        title=?, creator=?, rel_date=?, summary=?, brief=?, 
                                        highlights=?, note=?, view_date=? WHERE id=?""",
                                     (new_title, new_creator, new_rel_date, new_summary, new_brief, 
                                      new_highlights, new_note, str(new_view_date), item['id']))
                    st.success("수정되었습니다!")
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

# --- [메인 화면] ---
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month

tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        if category == "STAGE": # 무대극 연동
            res = search_kopis(search_query)
            if res:
                sel = st.selectbox("검색 결과", [f"🎭 {r['title']} ({r['venue']})" for r in res])
                if st.button("✨ 데이터 가져오기"):
                    s = next(x for x in res if f"🎭 {x['title']} ({x['venue']})" == sel)
                    st.session_state.api_data = {'title': s['title'], 'creator': s['venue'], 'date': s['date'], 'img': s['img'], 'summary': ''}
                    st.rerun()
        # ... (기타 카테고리 검색 로직 동일)

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url = st.text_input("이미지 URL", value=data.get('img', ''))
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
        if st.button("✅ 아카이브 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url, str(date.today()), str(view_date)))
            st.session_state.api_data = {}
            st.success("저장 완료!"); st.rerun()

with tab2:
    all_df = load_data()
    if not all_df.empty:
        sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])
        
        with sub_tabs[0]: # 달력 보기
            c1, c2, c3 = st.columns([1, 2, 1])
            if c1.button("◀"):
                st.session_state.cal_month -= 1
                if st.session_state.cal_month == 0: st.session_state.cal_month = 12; st.session_state.cal_year -= 1
                st.rerun()
            c2.markdown(f"<div class='num-text' style='text-align:center;'>{st.session_state.cal_year} . {st.session_state.cal_month}</div>", unsafe_allow_html=True)
            if c3.button("▶"):
                st.session_state.cal_month += 1
                if st.session_state.cal_month == 13: st.session_state.cal_month = 1; st.session_state.cal_year += 1
                st.rerun()

            cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
            m_df = all_df[(all_df['v_dt'].dt.year == st.session_state.cal_year) & (all_df['v_dt'].dt.month == st.session_state.cal_month)]
            
            for week in cal:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day != 0:
                        with cols[i]:
                            d_items = m_df[m_df['v_dt'].dt.day == day]
                            is_active = not d_items.empty
                            box_class = "cal-day-active" if is_active else "cal-day-empty"
                            st.markdown(f"<div class='{box_class}'><p class='num-text' style='font-size:25px;'>{day}</p>", unsafe_allow_html=True)
                            if is_active:
                                img_str = d_items.iloc[0]['img_url']
                                if img_str: st.image(img_str, use_container_width=True)
                                for _, r in d_items.iterrows():
                                    if st.button(f"{r['title'][:5]}..", key=f"cal_{r['id']}", use_container_width=True): 
                                        show_details(r)
                            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("아직 기록된 데이터가 없습니다.")
