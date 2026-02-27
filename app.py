import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
import re 
import xml.etree.ElementTree as ET
from supabase import create_client, Client

# --- [1. 설정 및 API] ---
st.set_page_config(
    layout="wide", 
    page_title="PRISM",
    page_icon="🌈",
    initial_sidebar_state="collapsed"
)

TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- [2. DB 함수 및 동기화 로직] ---
st.title("🌈PRISM ARCHIVE ")
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                         img_url TEXT, img_url2 TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def migrate_to_supabase():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            local_data = conn.execute("SELECT * FROM archive").fetchall()
        
        if not local_data:
            st.session_state.sync_msg = ("warning", "로컬 데이터가 없습니다.")
            return

        upload_list = [dict(row) for row in local_data]
        for d in upload_list:
            if 'id' in d: del d['id']
            
        supabase.table("archive").upsert(upload_list).execute() 
        st.session_state.sync_msg = ("success", f"✅ {len(upload_list)}개 데이터 클라우드 백업 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        
        if not cloud_data:
            st.session_state.sync_msg = ("warning", "클라우드가 비어있습니다.")
            return

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            added_count = 0
            for row in cloud_data:
                # 제목과 감상일 기준으로 중복 체크
                exists = cursor.execute("SELECT id FROM archive WHERE title=? AND view_date=?", 
                                     (row['title'], row['view_date'])).fetchone()
                if not exists:
                    cursor.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row['category'], row['title'], row['creator'], row['rel_date'], 
                         row['venue'], row['summary'], row['brief'], row['highlights'], 
                         row['note'], row['img_url'], row['save_date'], row['view_date']))
                    added_count += 1
            
            # [핵심] 변경사항을 확정(Commit)해야 로컬 DB에 물리적으로 저장됩니다.
            conn.commit()
            
        st.session_state.sync_msg = ("success", f"✅ {added_count}개의 새로운 데이터를 복구했습니다!")
        # 콜백 내 rerun()은 필요 없으므로 제거
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")


# --- [3. 로그인 시스템 & 사이드바] ---

# 작업 중일 때 True로 두면 비번 없이도 관리자 메뉴가 보입니다. 
# 배포 시에는 False로 바꾸세요.
DEV_MODE = False 

# 세션 초기화 (user_password를 저장하는 것이 핵심)
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_password" not in st.session_state:
    st.session_state.user_password = ""
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

# [핵심] 세션에 저장된 비번이 맞다면 자동으로 로그인 상태 유지
if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

# 최종 관리자 권한 여부
is_admin = st.session_state.is_logged_in or DEV_MODE

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    
    # 로그인하지 않은 상태일 때만 로그인 UI 표시
    if not is_admin:
        input_password = st.text_input("Password", type="password", key="sidebar_pw")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.user_password = input_password  # 세션에 비번 저장
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.error("Incorrect Password")
    
    # 로그인 성공 후 표시되는 메뉴
    if st.session_state.is_logged_in:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.session_state.user_password = "" # 로그아웃 시 비번 삭제
            st.rerun()
            
        st.divider()
        st.markdown("### 🔄 Data Sync")
        if 'sync_msg' in st.session_state:
            m_type, m_txt = st.session_state.sync_msg
            if m_type == "success": st.success(m_txt)
            elif m_type == "warning": st.warning(m_txt)
            else: st.error(m_txt)
            del st.session_state.sync_msg
        
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)

    st.divider()
    st.markdown("### 📱 화면 모드")
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True, label_visibility="collapsed")

# 최종 변수 설정
is_mobile = st.session_state.view_mode == "Mobile"


# --- [API 검색 함수들] --- (기존과 동일하므로 생략하지 않고 유지)
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
            title = m.get('collectionName' if is_album else 'trackName', 'Unknown')
            formatted_res.append({'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}", 'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName', '')})
        return formatted_res
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    is_movie = "MOVIES" in category
    type_path = "movie" if is_movie else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    
    try:
        res = requests.get(url).json()
        crew_list = res.get('credits', {}).get('crew', [])
        cast_list = res.get('credits', {}).get('cast', [])
        
        # 1. 창작자(감독/작가) 정보 추출
        if is_movie:
            director = next((m['name'] for m in crew_list if m.get('job') == 'Director'), "정보 없음")
            creator_label = f"[감독] {director}"
            
            companies = res.get('production_companies', [])
            venue_info = companies[0].get('name', '') if companies else ""
        else:
            # 시리즈물 (TV)
            creators = res.get('created_by', [])
            if creators:
                creator_names = ", ".join([c['name'] for c in creators])
            else:
                creator_names = next((m['name'] for m in crew_list if m.get('job') in ['Writer', 'Executive Producer']), "정보 없음")
            
            creator_label = f"[작가/제작] {creator_names}"
            
            networks = res.get('networks', [])
            venue_info = networks[0].get('name', '') if networks else ""

        # 2. 출연진 정보 추출 (최대 3명)
        cast_names = ", ".join([c['name'] for c in cast_list[:3]])
        cast_label = f"[출연] {cast_names}" if cast_names else ""

        # 3. 최종 결합 (역할별로 구분자 / 를 넣어 나중에 split하기 좋게 만듦)
        full_creator = f"{creator_label} / {cast_label}".strip(" / ")
        
        return {"creator": full_creator, "venue": venue_info}
    
    except Exception as e:
        return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    year_match = re.search(r'\d{4}', query)
    search_year = year_match.group() if year_match else None
    clean_query = re.sub(r'\d{4}', '', query).strip()
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={clean_query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        items = root.findall('db')
        results = []
        for d in items:
            title = d.findtext('prfnm')
            date_from = d.findtext('prfpdfrom')
            if search_year and search_year not in date_from: continue
            results.append({
                'title': title, 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 
                'date': date_from, 'venue': d.findtext('fcltynm')
            })
        return results
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        d = root.find('db')
        if d is not None:
            # 1. 제작진(연출, 작가 등) 정보 추출
            crew = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""
            # 2. 출연진 정보 추출
            cast = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
            
            info_parts = []
            if crew:
                # '연출: 홍길동' 식으로 올 수도 있고 이름만 올 수도 있으므로 태그 부여
                info_parts.append(f"[제작] {crew}")
            if cast:
                # 출연진 정보 추가
                info_parts.append(f"[출연] {cast}")
            
            if not info_parts:
                return "정보 없음"
                
            # 최종 형태: [제작] 연출진 / [출연] 배우들
            return " / ".join(info_parts)
            
    except Exception as e:
        return "상세정보 로드 실패"
    return "정보 없음"


# --- [4. 팝업 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    edit_mode = False
    if is_admin:
        t_col1, t_col2, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                try: supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                except: pass
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    if is_mobile:
        col_img = st.container()
        col_txt = st.container()
    else:
        col_img, col_txt = st.columns([0.3, 0.7])

    # --- 수정 모드 (Admin 전용) ---
    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')), key=f"img2_in_{item['id']}")
            if n_img: st.image(n_img, use_container_width=True)

        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                cat = item.get('category')
                labels = {"BOOKS": "📖 출판사", "MUSIC": "💿 레이블", "MOVIES": "🎬 제작사", "SERIES": "📺 플랫폼", "STAGE": "📍 장소"}
                v_label = labels.get(cat, "📍 장소")

                c1, c2 = st.columns(2)
                n_rel = c1.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = c2.text_input(v_label, value=str(item.get('venue', '')))
                
                try: curr_view = pd.to_datetime(item.get('view_date')).date()
                except: curr_view = date.today()
                
                n_view_date = st.date_input("🍿 감상일 수정", value=curr_view)
                n_sum = st.text_area("📖 작품소개", value=str(item.get('summary', '')), height=150)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=100)

                if st.form_submit_button("💾 저장"):
                    try:
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("""UPDATE archive SET 
                                            title=?, creator=?, rel_date=?, venue=?, 
                                            summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? 
                                            WHERE id=?""", 
                                         (n_title, n_creator, n_rel, n_venue, 
                                          n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, n_img2, item['id']))
                        
                        supabase.table("archive").update({
                            "title": n_title, "creator": n_creator, "rel_date": n_rel, "venue": n_venue,
                            "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note,
                            "view_date": str(n_view_date), "img_url": n_img, "img_url2": n_img2
                        }).eq("title", item['title']).eq("view_date", item['view_date']).execute()

                        st.success("✅ 수정 완료!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")

    # --- 조회 모드 (이 else 문이 위 if와 줄이 맞아야 합니다) ---
    else: 
        with col_img:
            img_url = item.get('img_url')
            if img_url: st.image(img_url, use_container_width=True)
    
        # 이미지 2가 있다면 추가 출력
            img_url2 = item.get('img_url2')
            if img_url2: st.image(img_url2, use_container_width=True)
            
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"#### **[{item.get('category')}]**")
            st.write(f"**{item.get('creator')}**")
            st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.markdown(f'<p style="color: #E2E2E2; font-weight: bold; font-size: 1.1em;">🍿감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()

            # 섹션 설정 (배지 스타일)
            sections = [
                ("📖 작품소개", "summary", "#444"),
                ("📝 요약", "brief", "#0E6245"),
                ("✨ 인상 깊은 부분", "highlights", "#7D5600"),
                ("🌈 PRISM", "note", "#1E425E")
            ]

            for label, key, color in sections:
                content = item.get(key)
                if content:
                    # 제목을 작은 배지 형태로 출력
                    st.markdown(f"""
                        <div style="display: inline-block; background-color: {color}; color: white; 
                        padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px;">
                            {label}
                        </div>""", unsafe_allow_html=True)
                    
                    # 본문 출력 (스페이스 2개로 줄바꿈 유지 & 자동 줄바꿈 보장)
                    st.markdown(content.replace('\n', '  \n'))
                    
                    # 섹션 구분을 위한 얇은 선
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)


# --- [5. 메인 화면] ---
if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tabs = st.tabs(["📂 ARCHIVE"])
    tab_a = tabs[0]
    tab_w = None

# WRITE 로직 (생략 - 기존과 동일)
if is_admin and tab_w:
    with tab_w:
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
                        st.session_state.api_data = {'title': b['title'], 'creator': ", ".join(b['authors']), 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'venue': b.get('publisher', ''), 'summary': b.get('contents', '')}
                        st.rerun()
            elif category == "MUSIC":
                res = search_apple_music(search_query)
                if res:
                    opts = {m['display_name']: m for m in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        m = opts[sel]
                        st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m.get('url', '')}\n\n"}
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
            else: 
                res = search_tmdb(search_query, category)
                if res:
                    t_key = 'title' if category == 'MOVIES' else 'name'
                    d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                    opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]
                        details = get_tmdb_details(s['id'], category)
                        st.session_state.api_data = {'title': s.get(t_key), 'creator': details['creator'], 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'venue': details['venue'], 'summary': s.get('overview', '')}
                        st.rerun()

        st.divider()
        data = st.session_state.get('api_data', {})
        if is_mobile:
            cl, cr = st.container(), st.container()
        else:
            cl, cr = st.columns([0.4, 0.6])
            
        with cl:
            img_url_val = st.text_input("🖼️ 이미지", value=data.get('img', ''))
            if img_url_val: st.image(img_url_val, use_container_width=True)
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자 정보", value=data.get('creator', ''))
            rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
            venue = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
        with cr:
            summary = st.text_area("📖 작품소개", value=data.get('summary', ''), height=100)
            brief = st.text_input("📝 요약 (한 줄 평)")
            highlights = st.text_area("✨ 인상 깊은 부분", height=100)
            note = st.text_area("🌈 PRISM", height=100)
            view_date = st.date_input("🍿 감상일", value=date.today())
            
            if st.button("✅ 기록 저장", use_container_width=True):
                new_record = {"category": str(category), "title": str(title).strip(), "creator": str(creator).strip(), "rel_date": str(rel_date), "venue": str(venue).strip(), "summary": str(summary).strip(), "brief": str(brief).strip(), "highlights": str(highlights).strip(), "note": str(note).strip(), "img_url": str(img_url_val).strip(), "save_date": str(date.today()), "view_date": str(view_date)}
                try:
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (new_record["category"], new_record["title"], new_record["creator"], new_record["rel_date"], new_record["venue"], new_record["summary"], new_record["brief"], new_record["highlights"], new_record["note"], new_record["img_url"], new_record["save_date"], new_record["view_date"]))
                    supabase.table("archive").upsert(new_record).execute()
                    st.success("✅ 저장 완료!")
                    st.session_state.api_data = {}
                    time.sleep(0.8)
                    st.rerun()
                except Exception as e: st.error(f"❌ 오류: {e}")

# --- [ARCHIVE 탭] ---
with tab_a:
    # 1. CSS 수정: 모바일(600px 미만)일 때는 한 줄에 하나씩 쌓이도록 변경
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-top: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); background: #1e1e1e; display: flex; align-items: center; justify-content: center; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0, 0, 0, 0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        
        /* PC에서만 6열 유지, 모바일에서는 기본 stack 동작 */
        @media (min-width: 600px) { 
            [data-testid="stHorizontalBlock"] { display: flex !important; flex-wrap: nowrap !important; gap: 10px !important; } 
            [data-testid="column"] { flex: 1 1 0% !important; min-width: 0 !important; } 
        }
    </style>""", unsafe_allow_html=True)

    # 2. 데이터 불러오기 및 그리드 출력
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        cat_emojis = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭"}
        tab_titles = [f"📅 ALL ({len(all_df)})"] + [f"{cat_emojis[c]}{c} ({len(all_df[all_df['category'] == c])})" for c in cat_order]
        sub_tabs = st.tabs(tab_titles)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        cat_emojis = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭"}
        tab_titles = [f"📅 ALL ({len(all_df)})"] + [f"{cat_emojis[c]}{c} ({len(all_df[all_df['category'] == c])})" for c in cat_order]
        sub_tabs = st.tabs(tab_titles)

        grid_cols = 2 if is_mobile else 6 

        # --- [ALL 탭] ---
        with sub_tabs[0]:
            years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            year_options = {y: f"{y}({len(all_df[all_df['v_dt'].dt.year == y])})" for y in years}
            sel_y = st.selectbox("📅 연도 선택", options=list(year_options.keys()), format_func=lambda x: year_options[x], key="archive_year_sel")
            y_df = all_df[all_df['v_dt'].dt.year == sel_y]
            
            for m in range(12, 0, -1):
                m_data = y_df[y_df['v_dt'].dt.month == m]
                if not m_data.empty:
                    st.subheader(f"🗓️ {m}월")
                    items = m_data.to_dict('records')
                    for i in range(0, len(items), grid_cols):
                        cols = st.columns(grid_cols)
                        for j in range(grid_cols):
                            if i+j < len(items):
                                row = items[i+j]
                                img_style = 'style="height: auto; aspect-ratio: 1/1;"' if row["category"] == "MUSIC" else ""
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box"><div class="badge-cat">{row["category"]}</div><div class="badge-date">{pd.to_datetime(row["view_date"]).day}일</div><img src="{row["img_url"]}" {img_style}></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:10], key=f"all_btn_{row['id']}", use_container_width=True): show_details(row)

        # --- [카테고리 탭] ---
        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx + 1]:
                c_data = all_df[all_df['category'] == c_name]
                if c_data.empty: st.info(f"{c_name} 데이터 없음")
                else:
                    items = c_data.to_dict('records')
                    tab_cls = "music-tab-style" if c_name == "MUSIC" else ""
                    for i in range(0, len(items), grid_cols):
                        cols = st.columns(grid_cols)
                        for j in range(grid_cols):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box {tab_cls}"><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:10], key=f"cat_btn_{c_name}_{row['id']}", use_container_width=True): show_details(row)















