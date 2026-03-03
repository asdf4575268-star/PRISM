import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
import re
import xml.etree.ElementTree as ET
from supabase import create_client, Client
from bs4 import BeautifulSoup

# -----------------------------
# 1. 기본 설정
# -----------------------------
st.set_page_config(
    layout="wide",
    page_title="PRISM",
    page_icon="🌈",
    initial_sidebar_state="collapsed"
)

TMDB_API_KEY = "YOUR_TMDB_KEY"
KOPIS_KEY = "YOUR_KOPIS_KEY"
DB_NAME = "archive_prism_total_v5.db"

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# 2. DB 초기화
# -----------------------------
@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT, title TEXT, creator TEXT,
        rel_date TEXT, venue TEXT,
        summary TEXT, brief TEXT,
        highlights TEXT, note TEXT,
        img_url TEXT, img_url2 TEXT,
        save_date TEXT, view_date TEXT
    )''')
    conn.commit()

init_db()

@st.cache_data(ttl=600)
def get_all_data():
    conn = get_connection()
    return pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

# -----------------------------
# 3. 로그인 시스템
# -----------------------------
DEV_MODE = False

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_password" not in st.session_state:
    st.session_state.user_password = ""
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

is_admin = st.session_state.is_logged_in or DEV_MODE

with st.sidebar:
    st.markdown("### 🔐 Admin Access")

    if not is_admin:
        pw = st.text_input("Password", type="password")
        if pw:
            if pw == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.user_password = pw
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.error("Incorrect Password")

    if is_admin:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout"):
            st.session_state.is_logged_in = False
            st.session_state.user_password = ""
            st.rerun()

    st.divider()
    st.markdown("### 📱 화면 모드")
    st.session_state.view_mode = st.radio(
        "보기 옵션",
        ["PC", "Mobile"],
        horizontal=True,
        label_visibility="collapsed"
    )

is_mobile = st.session_state.view_mode == "Mobile"

# -----------------------------
# 4. SCRAP URL 크롤링
# -----------------------------
def crawl_url_metadata(url):
    try:
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")

        title = soup.find("meta", property="og:title")
        image = soup.find("meta", property="og:image")
        desc = soup.find("meta", property="og:description")
        site = soup.find("meta", property="og:site_name")

        return {
            "title": title["content"] if title else "",
            "img": image["content"] if image else "",
            "summary": desc["content"] if desc else "",
            "creator": site["content"] if site else ""
        }
    except:
        return None

# -----------------------------
# 5. SCRAP 해시태그 추출
# -----------------------------
def extract_hashtags(text):
    if not text:
        return []
    return re.findall(r"#\w+", text)

# -----------------------------
# 6. 데이터 로드
# -----------------------------
df = get_all_data()

# SCRAP 완전 격리
display_df = df[df["category"] != "SCRAP"]

# -----------------------------
# 7. 탭 구성
# -----------------------------
cat_order = ["ALL"] + sorted(display_df["category"].dropna().unique().tolist())

if is_admin:
    cat_order.append("SCRAP")

tabs = st.tabs(cat_order)

# -----------------------------
# 8. ALL 탭
# -----------------------------
with tabs[0]:
    st.markdown("## 📚 Archive")

    if display_df.empty:
        st.info("데이터가 없습니다.")
    else:
        for _, row in display_df.iterrows():
            with st.expander(f"{row['title']} ({row['category']})"):
                if row["img_url"]:
                    st.image(row["img_url"], width=200)
                st.write(row["summary"])
                st.caption(row["view_date"])

                # SCRAP 단방향 참조
                scrap_df = df[df["category"] == "SCRAP"]
                related = scrap_df[
                    scrap_df["note"].str.contains(f"#{row['title']}", na=False)
                ]

                if not related.empty:
                    if st.button("🔗 관련 SCRAP 보기", key=row["id"]):
                        st.write(related[["title", "note"]])

# -----------------------------
# 9. SCRAP 관리자 탭
# -----------------------------
if is_admin and "SCRAP" in cat_order:
    scrap_tab = tabs[cat_order.index("SCRAP")]

    with scrap_tab:
        st.markdown("## 📰 SCRAP Dashboard")

        scrap_df = df[df["category"] == "SCRAP"]

        if scrap_df.empty:
            st.info("스크랩 데이터가 없습니다.")
        else:
            # 해시태그 클라우드
            all_tags = []
            for n in scrap_df["note"]:
                all_tags.extend(extract_hashtags(n))

            unique_tags = sorted(set(all_tags))

            if unique_tags:
                st.markdown("### 🏷️ Hashtag Cloud")
                st.write(" ".join(unique_tags))

            # 주간 그룹화
            scrap_df["view_date"] = pd.to_datetime(scrap_df["view_date"])
            weekly = scrap_df.groupby(
                pd.Grouper(key="view_date", freq="W-MON")
            )

            for week, group in weekly:
                st.markdown(f"### 📅 {week.date()} 주간")
                for _, row in group.iterrows():
                    with st.expander(row["title"]):
                        if row["img_url"]:
                            st.image(row["img_url"], width=200)
                        st.write(row["summary"])
                        st.write(row["note"])

        st.divider()
        st.markdown("## ➕ 새 SCRAP 추가")

        url_input = st.text_input("기사 URL 입력")

        if st.button("🔍 자동 입력"):
            data = crawl_url_metadata(url_input)
            if data:
                st.session_state.scrap_title = data["title"]
                st.session_state.scrap_creator = data["creator"]
                st.session_state.scrap_summary = data["summary"]
                st.session_state.scrap_img = data["img"]
                st.success("자동 입력 완료")
            else:
                st.error("크롤링 실패")

        title = st.text_input("제목", key="scrap_title")
        creator = st.text_input("매체", key="scrap_creator")
        summary = st.text_area("요약", key="scrap_summary")
        note = st.text_area("노트 (#태그 포함)")
        img_url = st.text_input("썸네일", key="scrap_img")

        if st.button("💾 저장"):
            conn = get_connection()
            conn.execute("""
                INSERT INTO archive
                (category, title, creator, rel_date, venue,
                 summary, brief, highlights, note,
                 img_url, img_url2, save_date, view_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "SCRAP",
                title, creator, "",
                "", summary, "", "",
                note, img_url, "",
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d")
            ))
            conn.commit()
            st.cache_data.clear()
            st.success("저장 완료")
            st.rerun()

# --- [4. 팝업 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    edit_mode = False
    if is_admin:
        t_col1, t_col2, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                conn = get_connection()
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                conn.commit()
                try: supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                except: pass
                st.cache_data.clear() # 삭제 후 리스트 갱신
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    if is_mobile:
        col_img = st.container()
        col_txt = st.container()
    else:
        col_img, col_txt = st.columns([0.3, 0.7])

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')), key=f"img2_in_{item['id']}")
            if n_img and n_img.strip() and n_img != "None": st.image(n_img, use_container_width=True)

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
                        conn = get_connection()
                        conn.execute("""UPDATE archive SET 
                                        title=?, creator=?, rel_date=?, venue=?, 
                                        summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? 
                                        WHERE id=?""", 
                                     (n_title, n_creator, n_rel, n_venue, 
                                      n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, n_img2, item['id']))
                        conn.commit()
                        supabase.table("archive").update({
                            "title": n_title, "creator": n_creator, "rel_date": n_rel, "venue": n_venue,
                            "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note,
                            "view_date": str(n_view_date), "img_url": n_img, "img_url2": n_img2
                        }).eq("title", item['title']).eq("view_date", item['view_date']).execute()
                        st.cache_data.clear() # 업데이트 후 리스트 갱신
                        st.success("✅ 수정 완료!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e: st.error(f"❌ 오류: {e}")
    else: 
        with col_img:
            img_url = item.get('img_url')
            if isinstance(img_url, str) and img_url.strip() and img_url != "None":
                try: st.image(img_url, use_container_width=True)
                except: st.warning("이미지 1 로드 실패")
            
            img_url2 = item.get('img_url2')
            if isinstance(img_url2, str) and img_url2.strip() and img_url2 != "None":
                try: st.image(img_url2, use_container_width=True)
                except: st.warning("이미지 2 로드 실패")
            
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{item.get('creator')}**")
            st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.markdown(f'<p style="color: #E2E2E2; font-weight: bold; font-size: 1.1em;">🍿감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            sections = [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]
            for label, key, color in sections:
                content = item.get(key)
                if content:
                    st.markdown(f"""<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px;">{label}</div>""", unsafe_allow_html=True)
                    st.markdown(content.replace('\n', '  \n'))
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)


# --- [5. 메인 화면] ---
st.title("🌈PRISM ARCHIVE ")
if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tabs = st.tabs(["📂 ARCHIVE"])
    tab_a = tabs[0]
    tab_w = None

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
        cl, cr = st.columns([0.4, 0.6]) if not is_mobile else (st.container(), st.container())
        with cl:
            img_url_val = st.text_input("🖼️ 이미지", value=data.get('img', ''))
            if img_url_val and img_url_val.strip() and img_url_val != "None": st.image(img_url_val, use_container_width=True)
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
                new_record = {"category": str(category), "title": str(title).strip(), "creator": str(creator).strip(), "rel_date": str(rel_date), "venue": str(venue).strip(), "summary": str(summary).strip(), "brief": str(brief).strip(), "highlights": str(highlights).strip(), "note": str(note).strip(), "img_url": str(img_url_val).strip(), "img_url2": "", "save_date": str(date.today()), "view_date": str(view_date)}
                try:
                    conn = get_connection()
                    conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (new_record["category"], new_record["title"], new_record["creator"], new_record["rel_date"], new_record["venue"], new_record["summary"], new_record["brief"], new_record["highlights"], new_record["note"], new_record["img_url"], new_record["img_url2"], new_record["save_date"], new_record["view_date"]))
                    conn.commit()
                    supabase.table("archive").upsert(new_record).execute()
                    st.cache_data.clear() # 기록 후 리스트 갱신
                    st.success("✅ 저장 완료!")
                    st.session_state.api_data = {}
                    time.sleep(0.8)
                    st.rerun()
                except Exception as e: st.error(f"❌ 오류: {e}")

# --- [ARCHIVE 탭] ---
with tab_a:
    st.markdown("""<style>
        /* 기본 틀: 포스터 비율 (1:1.4) */
        .cal-img-box { 
            position: relative; 
            width: 100%; 
            aspect-ratio: 1/1.4; 
            overflow: hidden; 
            border-radius: 8px; 
            margin-top: 5px; 
            box-shadow: 0 4px 8px rgba(0,0,0,0.2); 
            background: #1e1e1e;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        
        /* 음악 카테고리 전용 스타일 */
        .music-tab-style {
            aspect-ratio: 1/1 !important;
        }
         
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0, 0, 0, 0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }

        /* [핵심] 가로 모드 및 넓은 화면 대응 CSS */
        @media (min-width: 600px) {
            [data-testid="stHorizontalBlock"] {
                display: flex !important;
                flex-wrap: nowrap !important;
                gap: 10px !important;
            }
            [data-testid="column"] {
                flex: 1 1 0% !important;
                min-width: 0 !important;
            }
        }
    </style>""", unsafe_allow_html=True)

    # 이 부분이 캐싱되어 탭을 전환하거나 다시 그릴 때마다 DB에서 데이터를 끌어오지 않게 됩니다.
    all_df = get_all_data()

    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        cat_emojis = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭"}
        tab_titles = [f"📅 ALL ({len(all_df)})"] + [f"{cat_emojis[c]}{c} ({len(all_df[all_df['category'] == c])})" for c in cat_order]
        sub_tabs = st.tabs(tab_titles)
        grid_cols = 2 if is_mobile else 6

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
                                    
                                    short_title = row['title'][:10] + "..." if len(row['title']) > 10 else row['title']
                                    if st.button(short_title, key=f"all_btn_{row['id']}", use_container_width=True): show_details(row)

        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx + 1]:
                c_data = all_df[all_df['category'] == c_name]
                if c_data.empty: st.info(f"{c_name} 데이터 없음")
                else:
                    items = c_data.to_dict('records')
                    music_cls = "music-tab-style" if c_name == "MUSIC" else ""
                    for i in range(0, len(items), grid_cols):
                        cols = st.columns(grid_cols)
                        for j in range(grid_cols):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    img_u = row["img_url"] if row["img_url"] and str(row["img_url"]) != "None" else ""
                                    st.markdown(f'<div class="cal-img-box {music_cls}"><div class="badge-date">{row["view_date"]}</div><img src="{img_u}"></div>', unsafe_allow_html=True)
                                    
                                    short_title = row['title'][:10] + "..." if len(row['title']) > 10 else row['title']
                                    if st.button(short_title, key=f"cat_btn_{c_name}_{row['id']}", use_container_width=True): show_details(row)


