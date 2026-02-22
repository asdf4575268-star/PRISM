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
import shutil

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month
if 'api_data' not in st.session_state: st.session_state.api_data = {}

DB_NAME = 'archive_prism_total_v5.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=1160662254&single=true&output=csv"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def restore_from_google():
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV).fillna("")
        
        if df.empty:
            st.warning("복원할 데이터가 시트에 없습니다.")
            return

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM archive")
            
            for _, row in df.iterrows():
                vals = row.tolist()
                # 시트의 컬럼 개수가 부족할 경우를 대비해 빈 값 채우기
                while len(vals) < 12:
                    vals.append("")

                # [날짜 처리] 12번째 컬럼(index 11)이 감상일
                raw_v = str(vals[11]).strip()
                if raw_v:
                    try:
                        clean_v = raw_v.replace("오전", "AM").replace("오후", "PM")
                        v_date = pd.to_datetime(clean_v).strftime('%Y-%m-%d')
                    except: v_date = raw_v
                else: v_date = ""

                # [데이터 입력] 시트 인덱스 번호와 DB 컬럼 매칭
                conn.execute("""
                    INSERT INTO archive 
                    (category, title, creator, rel_date, venue, 
                     summary, brief, highlights, note, 
                     img_url, save_date, view_date) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(vals[1]),  # 카테고리 (2번째)
                    str(vals[2]),  # 제목 (3번째)
                    str(vals[3]),  # 창작자 정보 (4번째)
                    str(vals[4]),  # 작품 날짜 (5번째)
                    str(vals[5]),  # 📍 장소 (6번째) - 이제 정확히 들어갑니다!
                    str(vals[6]),  # 줄거리 (7번째)
                    str(vals[7]),  # 요약 (8번째)
                    str(vals[8]),  # 인상 깊은 부분 (9번째)
                    str(vals[9]),  # 감상 (10번째)
                    str(vals[10]), # 이미지 (11번째)
                    str(vals[0]),  # 타임스탬프 (1번째)
                    v_date         # 감상일 (변환됨)
                ))
        st.success("✅ 시트 순서에 맞춰 복원이 완료되었습니다!")
    except Exception as e:
        st.error(f"❌ 복원 실패: {e}")

# --- [API 함수들 생략 - 사용자 원본과 동일] ---
# 1. 책: 한 번에 보여주는 결과 수만 늘리기 (size=50)
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    # size=50으로 설정해 관련 서적들을 페이지 넘김 없이 쭉 보여줍니다.
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", 
                           headers=headers, params={"query": query, "size": 50})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

# 2. 영화/시리즈: 제목에 숫자가 섞여도 잘 찾도록 include_adult만 추가
def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    # 한국어 결과가 없으면 영어 DB까지 뒤지는 로직이 포함되어 고전 검색에 강합니다.
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR&include_adult=true"
    try:
        r = requests.get(url).json().get("results", [])
        if not r: # 한국어 검색결과 없을 때 영어로 재시도
            url_en = url.replace("language=ko-KR", "language=en-US")
            r = requests.get(url_en).json().get("results", [])
        return r
    except: return []
def get_tmdb_details(item_id, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}/credits?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        res = requests.get(url).json()
        # 감독 찾기
        director = next((m['name'] for m in res.get('crew', []) if m.get('job') == 'Director'), "정보 없음")
        # 주요 출연진 3명
        cast = ", ".join([c['name'] for c in res.get('cast', [])[:3]])
        return f"감독: {director} / 출연: {cast}"
    except: 
        return "정보 없음"

# 3. 공연: 시작 날짜만 1900년으로 변경 (stdate=19000101)
def search_kopis(query):
    # 검색어에서 숫자를 빼고 순수 제목으로만 검색 (더 많은 결과를 보려고)
    clean_query = re.sub(r'\d{4}', '', query).strip()
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={clean_query}&stdate=19000101&eddate=20261231&rows=100&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        items = root.findall('db')
        results = []
        for d in items:
            results.append({
                'title': d.findtext('prfnm'), 
                'id': d.findtext('mt20id'), 
                'img': d.findtext('poster'), 
                'date': d.findtext('prfpdfrom'), 
                'venue': d.findtext('fcltynm')
            })
        return results
    except: return []

# --- [3. 팝업 함수 수정본] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    t_col1, t_col2, t_col3 = st.columns([0.2, 0.6, 0.2])
    with t_col1:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()
    with t_col3:
        edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")

    st.divider()
    col_img, col_txt = st.columns([0.3, 0.7])

    with col_img:
        img_url = item.get('img_url')
        if img_url: st.image(img_url, use_container_width=True)

    with col_txt:
        if edit_mode:
            with st.form(key=f"edit_form_{item['id']}"):
                # [추가] 이미지 URL 수정창 (미리보기는 폼 외부나 상단에 위치)
                n_img = st.text_input("🖼️ 이미지 URL", value=str(item.get('img_url', '')))
                
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                
                cat = item.get('category')
                labels = {"BOOKS": "📖 출판사", "MUSIC": "💿 레이블", "MOVIES": "🎬 제작사", "SERIES": "📺 플랫폼", "STAGE": "📍 장소"}
                v_label = labels.get(cat, "📍 장소")

                c1, c2 = st.columns(2)
                n_rel = c1.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = c2.text_input(v_label, value=str(item.get('venue', '')))
                
                try:
                    curr_view = pd.to_datetime(item.get('view_date')).date()
                except:
                    curr_view = date.today()
                n_view_date = st.date_input("🍿 감상일 수정", value=curr_view)
                
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_sum = st.text_area("📖 줄거리", value=str(item.get('summary', '')), height=150)
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=100)

                if st.form_submit_button("💾 저장"):
                    try:
                        # 1. 구글 시트 백업 (이미지 URL 포함)
                        r_dt = pd.to_datetime(n_rel) if n_rel else date.today()
                        v_dt = pd.to_datetime(n_view_date)
                        
                        BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
                        payload = {
                            "entry.574529989": cat, "entry.898076783": n_title, "entry.345368346": n_creator,
                            "entry.543246487": n_sum, "entry.1816924330": n_brief, "entry.270693677": n_high,
                            "entry.891180756": n_note, "entry.2056153041": n_img, # 새로 입력한 이미지 URL
                            "entry.780422311_year": str(r_dt.year), "entry.780422311_month": f"{r_dt.month:02d}", "entry.780422311_day": f"{r_dt.day:02d}",
                            "entry.1446643193_year": str(v_dt.year), "entry.1446643193_month": f"{v_dt.month:02d}", "entry.1446643193_day": f"{v_dt.day:02d}",
                            "entry.250402237": n_venue
                        }
                        requests.post(BACKUP_URL, data=payload, timeout=5)

                        # 2. 로컬 SQLite 업데이트 (img_url 필드 추가)
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("""UPDATE archive SET 
                                            title=?, creator=?, rel_date=?, venue=?, 
                                            summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=? 
                                            WHERE id=?""", 
                                         (n_title, n_creator, n_rel, n_venue, 
                                          n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, item['id']))
                        
                        st.success("✅ 이미지와 정보가 모두 수정되었습니다!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 저장 실패: {e}")
        else:
            # --- [조회 모드: 요청하신 레이아웃 적용] ---
            st.markdown(f'# {item.get("title")}')
            st.write(f"**[{item.get('category')}]** {item.get('creator')}")
            
            # 1. 공개일 | 장소 표시
            rel_v = item.get('rel_date') or "정보 없음"
            venue_v = item.get('venue') or ""
            venue_display = f" | 📍 {venue_v}" if venue_v else ""
            st.write(f"📅 {rel_v}{venue_display}")
            
            # 2. 감상일 (강조 및 분리)
            view_v = item.get('view_date') or "날짜 미상"
            st.markdown(f'<p style="color: #FF4B4B; font-weight: bold; font-size: 1.1em; margin-top: -10px;">🍿 {view_v}</p>', unsafe_allow_html=True)
            
            st.divider()
            if item.get('brief'): st.info(f"**요약:** {item.get('brief')}")
            if item.get('summary'): st.write(f"**줄거리:**\n{item.get('summary')}")
            if item.get('highlights'): st.warning(f"**인상 깊은 부분:**\n{item.get('highlights')}")
            if item.get('note'): st.success(f"**나의 감상:**\n{item.get('note')}")

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
                    st.session_state.api_data = {'title': b['title'], 'creator': f"{', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'venue': b.get('publisher', ''), 'summary': f"{b['url']}\n\n{b.get('contents', '')}"}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m['url']}\n\n"}
                    st.rerun()
        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {s['title']} [{s['date']}~] ({s['venue']})": s for s in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    combined_creator = get_kopis_detail(s['id'])
                    st.session_state.api_data = {'title': s['title'], 'creator': combined_creator, 'date': s['date'], 'venue': s['venue'], 'img': s['img'], 'summary': f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}"}
                    st.rerun()
        else: # MOVIES, SERIES
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                
                # 결과 리스트 생성
                opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key, ''))[:4]})": r for r in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                
                if st.button("✨ 가져오기", key=f"btn_{category}"):
                    s = opts[sel]
                    # [수정된 부분] 안전하게 데이터를 가져와서 세션에 저장
                    st.session_state.api_data = {
                        'title': s.get(t_key, '제목 없음'),
                        'creator': get_tmdb_details(s.get('id'), category),
                        'date': s.get(d_key, str(date.today())),
                        'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}" if s.get('poster_path') else "",
                        'venue': '', # 영화는 장소 비움
                        'summary': s.get('overview', '')
                    }
                    st.success(f"'{s.get(t_key)}' 정보를 가져왔습니다!")
                    time.sleep(0.5)
                    st.rerun()
    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("🖼️ ", value=data.get('img', ''))
        if img_url_val: st.image(img_url_val, use_container_width=True)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 정보", value=data.get('creator', ''))
        c_rel, c_ven = st.columns(2)
        rel_date = c_rel.text_input("📅 ", value=data.get('date', str(date.today())))
        venue = c_ven.text_input("📍", value=data.get('venue', ''))
        
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        view_date = st.date_input("🍿 감상일", value=date.today())
        
        if st.button("✅ 저장", use_container_width=True):
            try:
                r_dt = pd.to_datetime(rel_date)
                ry, rm, rd = str(r_dt.year), f"{r_dt.month:02d}", f"{r_dt.day:02d}"
                v_dt = pd.to_datetime(view_date)
                vy, vm, vd = str(v_dt.year), f"{v_dt.month:02d}", f"{v_dt.day:02d}"

                BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
                payload = {
                    "entry.574529989": category, "entry.898076783": title, "entry.345368346": creator,
                    "entry.543246487": summary, "entry.1816924330": brief, "entry.270693677": highlights,
                    "entry.891180756": note, "entry.2056153041": img_url_val,
                    "entry.780422311_year": ry, "entry.780422311_month": rm, "entry.780422311_day": rd,
                    "entry.1446643193_year": vy, "entry.1446643193_month": vm, "entry.1446643193_day": vd,
                    "entry.250402237": venue
                }

                res = requests.post(BACKUP_URL, data=payload, timeout=10)
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (category, title, creator, str(rel_date), venue, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
                
                st.success("✅ 저장 성공!")
                st.session_state.api_data = {}
                time.sleep(0.5)
                st.rerun()
            except Exception as e: st.error(f"❌ 오류 발생: {e}")

# --- TAB 2: ARCHIVE ---
# --- TAB 2: ARCHIVE ---
with tab2:
    if st.button("🔄"):
        restore_from_google()
        st.rerun()

    # [디자인] 버튼 텍스트 가운데 정렬 및 스타일
    st.markdown("""
        <style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1; overflow: hidden; border-radius: 6px; margin-bottom: 5px; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge { position: absolute; top: 5px; left: 5px; background: rgba(0, 0, 0, 0.6); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
        
        /* 버튼 내부 텍스트 무조건 가운데 정렬 */
        button[data-testid="stBaseButton-secondary"] p {
            display: flex !important;
            justify-content: center !important;
            text-align: center !important;
            width: 100% !important;
            margin: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    if not all_df.empty:
        cat_list = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        total_count = len(all_df)
        
        tab_names = [f"📅 ALL ({total_count})"]
        for c in cat_list:
            count = len(all_df[all_df['category'] == c])
            tab_names.append(f"{c} ({count})")
            
        sub_tabs = st.tabs(tab_names)

        # --- [탭 0: YEARLY] ---
        with sub_tabs[0]:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
            # 1. 전체 데이터를 날짜 최신순으로 정렬
            all_df = all_df.sort_values('v_dt', ascending=False)
            
            years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            if years:
                sel_y = st.selectbox("연도 선택", years, key="year_sel")
                # 선택한 연도 데이터 필터링 (이미 위에서 정렬됨)
                y_data = all_df[all_df['v_dt'].dt.year == sel_y]
                
                for m in range(12, 0, -1):
                    m_data = y_data[y_data['v_dt'].dt.month == m]
                    if not m_data.empty:
                        st.subheader(f"🗓️ {m}월 ({len(m_data)})")
                        items = m_data.to_dict('records')
                        
                        for i in range(0, len(items), 6):
                            cols = st.columns(6)
                            for j in range(6):
                                if i+j < len(items):
                                    row = items[i+j]
                                    with cols[j]:
                                        # --- 뱃지 날짜 처리 (nn일 또는 yy.mm.dd) ---
                                        raw_v = str(row.get('view_date') or "").strip()
                                        if raw_v and raw_v.lower() != "nan":
                                            try:
                                                temp_dt = pd.to_datetime(raw_v)
                                                # 월별로 묶여있으니 '일'을 강조 (예: 21일)
                                                badge_text = temp_dt.strftime('%d일') 
                                            except:
                                                badge_text = "미상"
                                        else:
                                            badge_text = "미상"
                                        
                                        # 이미지와 뱃지 출력
                                        st.markdown(f'''
                                            <div class="cal-img-box">
                                                <div class="badge">{badge_text}</div>
                                                <img src="{row["img_url"]}">
                                            </div>
                                        ''', unsafe_allow_html=True)
                                        
                                        # 제목 버튼 (7자 제한 유지)
                                        orig_title = str(row['title'])
                                        display_title = orig_title[:7] + ".." if len(orig_title) > 7 else orig_title
                                        
                                        if st.button(display_title, key=f"btn_yr_{row['id']}", use_container_width=True): 
                                            show_details(row)

        # --- [탭 1~5: 카테고리별 탭] ---
        for idx, c_name in enumerate(cat_list):
            with sub_tabs[idx + 1]:
                cat_df = all_df[all_df['category'] == c_name].copy()
                if not cat_df.empty:
                    cat_df['sort_dt'] = pd.to_datetime(cat_df['view_date'], errors='coerce')
                    cat_df = cat_df.sort_values(by='sort_dt', ascending=False, na_position='last')
                    items = cat_df.to_dict('records')

                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i + j < len(items):
                                row = items[i + j]
                                with cols[j]:
                                    raw_v = str(row.get('view_date') or "").strip()
                                    badge_d = ""
                                    if raw_v.lower() not in ["nan", "none", ""]:
                                        try:
                                            temp_dt = pd.to_datetime(raw_v.split(' ')[0])
                                            badge_d = temp_dt.strftime('%y.%m.%d')
                                        except:
                                            badge_d = raw_v[:10]
                                    
                                    st.markdown(f'<div class="cal-img-box"><div class="badge">{badge_d}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    
                                    # [수정] 7자 넘을 때만 '..' 붙이기
                                    orig_title = str(row['title'])
                                    display_title = orig_title[:10] + ".." if len(orig_title) > 7 else orig_title
                                    
                                    btn_key = f"btn_cat_{c_name}_{row['id']}"
                                    if st.button(display_title, key=btn_key, use_container_width=True): 
                                        show_details(row)







