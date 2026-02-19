import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month
if 'api_data' not in st.session_state: st.session_state.api_data = {}

# 월 이동 함수 추가
def shift_month(delta):
    new_month = st.session_state.cal_month + delta
    if new_month == 0:
        st.session_state.cal_year -= 1
        st.session_state.cal_month = 12
    elif new_month == 13:
        st.session_state.cal_year += 1
        st.session_state.cal_month = 1
    else:
        st.session_state.cal_month = new_month

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; line-height: 1; }
    .cal-img-box { width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:10px; margin-bottom:4px; border: 1px solid #eee; background-color: #f0f0f0; }
    .cal-img-box img { width:100%; height:100%; object-fit:cover; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# --- [2. API 함수 정의 구역] ---

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
        formatted_res = []
        for m in res:
            is_album = m.get('wrapperType') == 'collection'
            if is_album:
                title = m.get('collectionName', 'Unknown Album')
                info_url = m.get('collectionViewUrl', '')
                prefix = "📀 [ALBUM]"
            else:
                title = m.get('trackName', 'Unknown Song')
                info_url = m.get('trackViewUrl', '')
                prefix = "🎵 [SINGLE]"
            
            formatted_res.append({
                'display_name': f"{prefix} {title} - {m.get('artistName', '')}",
                'title': title,
                'creator': m.get('artistName', ''),
                'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'),
                'url': info_url
            })
        return formatted_res
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try:
        return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}/credits?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        res = requests.get(url).json()
        director = next((m['name'] for m in res.get('crew', []) if m.get('job') == 'Director'), "정보 없음")
        cast = ", ".join([c['name'] for c in res.get('cast', [])[:3]])
        return f"감독: {director} / 출연: {cast}"
    except: return "정보 없음"

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

# --- [3. 팝업 함수] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    # Pandas Series(행) 데이터를 딕셔너리로 확실히 변환
    if hasattr(item, 'to_dict'):
        item = item.to_dict()
    
    # 수정/조회 모드 전환
    edit_mode = st.toggle("✏️ 수정 모드", key=f"tog_v2_{item['id']}")
    
    col_img, col_txt = st.columns([0.4, 0.6])

    with col_img:
        # 이미지가 있으면 표시, 없으면 안내
        if item.get('img_url'):
            st.image(item['img_url'], use_container_width=True)
        else:
            st.info("등록된 이미지가 없습니다.")

    with col_txt:
        if edit_mode:
            # --- [수정 모드] ---
            with st.form(key=f"edit_v2_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                
                # 감상일 날짜 객체 변환
                try:
                    raw_v = str(item.get('view_date') or item.get('save_date'))[:10]
                    v_dt = datetime.strptime(raw_v, '%Y-%m-%d').date()
                except:
                    v_dt = date.today()
                n_view = st.date_input("🍿 감상일", v_dt)

                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '') if item.get('brief') else ''))
                n_sum = st.text_area("📖 줄거리(첫줄 URL)", value=str(item.get('summary', '') if item.get('summary') else ''), height=150)
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '') if item.get('highlights') else ''), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '') if item.get('note') else ''), height=100)

                if st.form_submit_button("💾 저장", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""
                            UPDATE archive 
                            SET title=?, creator=?, rel_date=?, summary=?, brief=?, highlights=?, note=?, view_date=? 
                            WHERE id=?
                        """, (n_title, n_creator, n_rel, n_sum, n_brief, n_high, n_note, str(n_view), item['id']))
                    st.rerun()
        else:
            # --- [조회 모드] ---
            # 1. 활동명 (90px)
           st.markdown(f'<p class="act-name">{item.get("title")}</p>', unsafe_allow_html=True)
            
            # 2. URL 버튼 (summary 첫 줄에 URL이 있는 경우)
            content = str(item.get('summary', ''))
            urls = re.findall(r'(https?://[^\s]+)', content)
            if urls:
                st.link_button("🌐 공식 정보 확인", urls[0], use_container_width=True)
            
            # 3. 기본 정보
            st.write(f"**창작자:** {item.get('creator')} | **작품날짜:** {item.get('rel_date')}")
            
            # 4. 감상일 (30px)
            v_date = item.get('view_date') or item.get('save_date', '')
            st.markdown(f'<p class="date-text">🍿 감상일: {v_date}</p>', unsafe_allow_html=True)
            
            st.divider()

            # 5. 상세 내용 (데이터가 비어있지 않으면 출력)
            def show_box(label, val, type="write"):
                if val and str(val).strip() not in ["None", "nan", ""]:
                    st.markdown(f"**{label}**")
                    if type == "success": st.success(val)
                    elif type == "info": st.info(val)
                    elif type == "warning": st.warning(val)
                    else: st.write(val)

            show_box("📝 요약", item.get('brief'), "success")
            show_box("📖 줄거리 / 상세", item.get('summary'), "info")
            show_box("✨ 인상 깊은 부분", item.get('highlights'), "warning")
            show_box("💬 감상", item.get('note'), "write")

            st.divider()
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                st.rerun()
# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        if category == "BOOKS":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']}": b for b in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': f"{', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'summary': f"{b['url']}\n\n{b.get('contents', '')}"}
                    st.rerun()

        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택 (SINGLE/ALBUM)", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m['url']}\n\n"}
                    st.rerun()

        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {s['title']} ({s['venue']})": s for s in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s['title'], 'creator': f"공연장: {s['venue']}", 'date': s['date'], 'img': s['img'], 'summary': ''}
                    st.rerun()

        else: # MOVIES, SERIES
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                opts = {f"🎬 {r.get(t_key)}": r for r in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s.get(t_key), 'creator': get_tmdb_details(s['id'], category), 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
                    st.rerun()

    st.divider()
    # 입력 폼 생략 (사용자 코드와 동일하게 유지)
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("🖼️", value=data.get('img', ''))
        if img_url_val: 
            st.image(img_url_val, use_container_width=True)
        else:
            st.info("검색을 통해 이미지를 불러와주세요.")
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 정보", value=data.get('creator', ''))
        col1, col2 = st.columns(2)
        rel_date = col1.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        view_date = col2.date_input("🍿 감상일", value=date.today())
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        if st.button("✅ 저장"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
            st.session_state.api_data = {}
            st.rerun()

# --- TAB 2: ARCHIVE ---
with tab2:
    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])
    
    with sub_tabs[0]:
        with sqlite3.connect(DB_NAME) as conn:
            all_df = pd.read_sql_query("SELECT * FROM archive", conn)
        
        if not all_df.empty:
            # 감상일이 없으면 기록일로 대체하여 v_dt(달력 기준일) 생성
            if 'view_date' not in all_df.columns:
                all_df['view_date'] = all_df['save_date']
            all_df['view_date_filled'] = all_df['view_date'].fillna(all_df['save_date'])
            all_df['v_dt'] = pd.to_datetime(all_df['view_date_filled'])
            all_df['year_int'] = all_df['v_dt'].dt.year
            
            # 연도 선택 + 통계
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

            # 이전달/다음달 버튼을 월 텍스트 양옆으로 촘촘히 중앙 배치
            _, n1, n2, n3, _ = st.columns([1.5, 1, 2, 1, 1.5])
            with n1:
                st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)
                if st.button("◀ 이전달", use_container_width=True): shift_month(-1); st.rerun()
            with n2:
                st.markdown(f"<div style='text-align:center;' class='num-text'>{st.session_state.cal_year} / {st.session_state.cal_month}</div>", unsafe_allow_html=True)
            with n3:
                st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)
                if st.button("다음달 ▶", use_container_width=True): shift_month(1); st.rerun()

            # 요일 헤더
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
                            # 이미지 박스
                            first_item = day_items.iloc[0]
                            if first_item['img_url']:
                                st.markdown(f'<div class="cal-img-box"><img src="{first_item["img_url"]}"></div>', unsafe_allow_html=True)
                            
                            for _, r in day_items.iterrows():
                                if st.button(f"• {r['title'][:5]}", key=f"cal_{r['id']}", use_container_width=True):
                                    show_details(r)
                        else:
                            st.markdown("<div style='height:80px;'></div>", unsafe_allow_html=True)
        else:
            st.info("기록이 없습니다.")

# 카테고리별 탭
    cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
    for idx, c_name in enumerate(cats):
        with sub_tabs[idx+1]:
            with sqlite3.connect(DB_NAME) as conn:
                # view_date가 있으면 사용하고, 없으면 save_date를 사용하여 정렬 (최신순)
                query = f"""
                    SELECT *, COALESCE(NULLIF(view_date, ''), save_date) as sort_date 
                    FROM archive 
                    WHERE category='{c_name}' 
                    ORDER BY sort_date DESC
                """
                df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                # 한 줄에 4개씩 배치
                cols = st.columns(4) 
                for i, row in df.iterrows():
                    with cols[i % 4]:
                        if row['img_url']:
                            # --- [이미지 정사각형 정렬 섹션] ---
                            st.markdown(f"""
                                <div style="
                                    width: 100%;
                                    aspect-ratio: 1 / 1;
                                    overflow: hidden;
                                    border-radius: 10px;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    background-color: #f0f0f0;
                                    margin-bottom: 5px;
                                ">
                                    <img src="{row['img_url']}" style="
                                        width: 100%;
                                        height: 100%;
                                        object-fit: cover;
                                    ">
                                </div>
                            """, unsafe_allow_html=True)
                        
                        # 날짜 표시 (감상일 우선 표시)
                        v_date_display = row.get('view_date') if row.get('view_date') else row.get('save_date', '')
                        st.markdown(f'<p class="date-text" style="font-size:15px; text-align:center;">🍿 {v_date_display}</p>', unsafe_allow_html=True)
                        
                        # 제목 버튼 (Key 중복 방지를 위해 idx 추가)
                        if st.button(row['title'], key=f"list_{idx}_{row['id']}", use_container_width=True):
                            show_details(row)
            else:
                st.info(f"{c_name} 카테고리에 아직 기록이 없습니다.")






