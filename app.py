import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# --- [1. 스타일 및 DB 설정] ---
st.set_page_config(layout="wide", page_title="My Archive")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    </style>
    """, unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect('archive_final.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                     rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')
    conn.commit()
    return conn

# --- [2. API 연동 함수] ---
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

def search_apple_music(query):
    # iTunes Search API (애플뮤직 데이터 소스)
    url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=10&country=kr"
    try:
        res = requests.get(url)
        return res.json().get("results", [])
    except: return []

init_db()

# --- [3. 메인 화면: 탭 구성] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 전체 목록 및 상세"])

with tab1:
    category = st.radio("📂 카테고리 선택", ["도서", "음악"], horizontal=True)
    
    # 검색 및 연동부
    search_query = st.text_input(f"🔍 {category} 검색", placeholder=f"연동할 {category} 제목/아티스트를 입력하세요")
    
    if search_query:
        if category == "도서":
            results = search_books(search_query)
            if results:
                options = {f"📚 {b['title']} ({b['authors'][0]})": b for b in results if b['authors']}
                sel = st.selectbox("검색 결과 선택", list(options.keys()))
                if st.button("✨ 데이터 연동"):
                    b = options[sel]
                    st.session_state.api_data = {
                        'title': b['title'], 
                        'creator': b['authors'][0], 
                        'date': b['datetime'][:10], 
                        'img': b['thumbnail'], 
                        'note': b['contents']
                    }
                    st.rerun()
        else: # 애플뮤직 연동
            results = search_apple_music(search_query)
            if results:
                options = {f"🍎 {m['trackName']} - {m['artistName']} ({m.get('collectionName', 'Single')})": m for m in results}
                sel = st.selectbox("검색 결과 선택", list(options.keys()))
                if st.button("✨ 애플뮤직 데이터 연동"):
                    m = options[sel]
                    # 고화질 이미지를 위해 URL 수정 (100x100 -> 600x600)
                    artwork_url = m.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
                    st.session_state.api_data = {
                        'title': m['trackName'], 
                        'creator': m['artistName'], 
                        'date': m['releaseDate'][:10], 
                        'img': artwork_url, 
                        'note': ''
                    }
                    st.rerun()

    data = st.session_state.get('api_data', {})
    st.divider()

    col_l, col_r = st.columns([0.4, 0.6])
    
    with col_l:
        img_url = st.text_input("이미지 주소", value=data.get('img', ''))
        if img_url:
            st.image(img_url, use_container_width=False, caption="애플뮤직 앨범 아트")
        
        title_label = "곡명/앨범명" if category == "음악" else "활동명 (제목)"
        creator_label = "아티스트" if category == "음악" else "창작자 (작가)"
        
        title = st.text_input(title_label, value=data.get('title', ''))
        creator = st.text_input(creator_label, value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
        
    with col_r:
        summary_label = "📖 요약/한줄평" if category == "음악" else "📖 요약"
        high_label = "✨ 추천 트랙/킬링 파트" if category == "음악" else "✨ 인상 깊은 부분 (쪽수 포함)"
        
        summary = st.text_area(summary_label, height=80)
        highlights = st.text_area(high_label, height=150)
        note = st.text_area("💬 감상", value=data.get('note', ''), height=150)
        
        # 하단 폰트 시각화 (가이드 준수: 90/30/60)
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 아카이브 최종 저장", use_container_width=True):
            conn = sqlite3.connect('archive_final.db')
            conn.execute("""INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) 
                            VALUES (?,?,?,?,?,?,?,?,?)""",
                         (category, title, creator, rel_date, summary, highlights, note, img_url, str(date.today())))
            conn.commit()
            st.success(f"{category} 기록이 성공적으로 저장되었습니다!")
            st.rerun()

with tab2:
    st.subheader("🗂️ 전체 아카이빙 상세 보기")
    conn = sqlite3.connect('archive_final.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    conn.close()

    if not df.empty:
        selected_title = st.selectbox("기록을 선택하세요", df['title'].tolist())
        item = df[df['title'] == selected_title].iloc[0]
        
        st.divider()
        det_l, det_r = st.columns([0.3, 0.7])
        with det_l:
            st.caption(f"카테고리: {item.get('category')}")
            if item['img_url']: st.image(item['img_url'], use_container_width=False)
            st.write(f"**정보:** {item['creator']}")
            st.write(f"**날짜:** {item['rel_date']}")
        
        with det_r:
            st.info(f"**📖 요약**\n\n{item['summary']}")
            st.warning(f"**✨ 인상 깊은 구절/트랙**\n\n{item['highlights']}")
            st.write(f"**💬 감상**\n\n{item['note']}")
            
            if st.button("🗑️ 삭제"):
                conn = sqlite3.connect('archive_final.db')
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
                conn.commit()
                st.rerun()
    else:
        st.info("아직 저장된 기록이 없습니다.")
