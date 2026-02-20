import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io, os, requests, polyline, math
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib import font_manager
import base64
import streamlit.components.v1 as components


# --- [1. 기본 설정 및 API] ---
API_CONFIGS = {
    "PRIMARY": {"ID": '202274', "SECRET": '63f6a7007ebe6b405763fc3104e17bb53b468ad0'},
    "SECONDARY": {"ID": '202275', "SECRET": '969201cab488e4eaf1398b106de1d4e520dc564c'}
}
CURRENT_CFG = API_CONFIGS["PRIMARY"] 
CLIENT_ID, CLIENT_SECRET = CURRENT_CFG["ID"], CURRENT_CFG["SECRET"]
ACTUAL_URL = "https://titanboy-kgcnje3tg3hbfpfsp6uwzc.streamlit.app"

st.set_page_config(page_title="TITAN BOY", layout="wide")
mpl.use('Agg')

# --- [2. 유틸리티 함수] ---
def logout_and_clear():
    st.cache_data.clear(); st.cache_resource.clear(); st.session_state.clear(); st.query_params.clear(); st.rerun()

def hex_to_rgba(hex_color, alpha):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)

def draw_styled_text(draw, pos, text, font, fill, shadow=True):
    if shadow:
        # 그림자를 3px -> 2px로 줄이고, 검정색을 더 진하게(220) 설정
        # 이렇게 하면 글자 외곽선이 더 선명하게 대비됩니다.
        draw.text((pos[0]+2, pos[1]+2), text, font=font, fill=(0, 0, 0, 220))
    draw.text(pos, text, font=font, fill=fill)
def load_font(name, size):
    fonts = {
        "BlackHanSans": "https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf",
        "KirangHaerang": "https://github.com/google/fonts/raw/main/ofl/kiranghaerang/KirangHaerang-Regular.ttf",
        "Lacquer": "https://github.com/google/fonts/raw/main/ofl/lacquer/Lacquer-Regular.ttf"
    }
    f_path = f"font_{name}.ttf"
    # 파일이 없으면 다운로드 시도
    if not os.path.exists(f_path):
        try:
            r = requests.get(fonts[name])
            with open(f_path, "wb") as f:
                f.write(r.content)
        except:
            return ImageFont.load_default() # 다운로드 실패 시 기본 폰트 반환
    
    try:
        return ImageFont.truetype(f_path, int(size))
    except:
        return ImageFont.load_default()

def get_weekly_stats(activities, target_date_str):
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        start_of_week = target_date - timedelta(days=target_date.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        weekly_dist = [0.0] * 7
        total_dist, total_time, hr_sum, hr_count = 0.0, 0, 0, 0
        for act in activities:
            if act.get('type') == 'Run':
                act_date = datetime.strptime(act['start_date_local'][:10], "%Y-%m-%d")
                if start_of_week <= act_date <= end_of_week:
                    dist = act.get('distance', 0) / 1000
                    weekly_dist[act_date.weekday()] += dist
                    total_dist += dist; total_time += act.get('moving_time', 0)
                    if act.get('average_heartrate'): hr_sum += act.get('average_heartrate'); hr_count += 1
        avg_hr = int(hr_sum / hr_count) if hr_count > 0 else 0
        avg_pace_sec = (total_time / total_dist) if total_dist > 0 else 0
        return {"dists": weekly_dist, "total_dist": f"{total_dist:.2f}", "total_time": f"{total_time//3600:02d}:{(total_time%3600)//60:02d}:{total_time%60:02d}", "avg_pace": f"{int(avg_pace_sec//60)}'{int(avg_pace_sec%60):02d}\"", "avg_hr": str(avg_hr), "range": f"{start_of_week.strftime('%m.%d')} - {end_of_week.strftime('%m.%d')}"}
    except: return None

def get_monthly_stats(activities, target_date_str):
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        first_day = target_date.replace(day=1)
        next_month = first_day.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        num_days = last_day.day
        monthly_dist = [0.0] * num_days
        total_dist, total_time, hr_sum, hr_count = 0.0, 0, 0, 0
        for act in activities:
            if act.get('type') == 'Run':
                act_date = datetime.strptime(act['start_date_local'][:10], "%Y-%m-%d")
                if first_day <= act_date <= last_day:
                    dist = act.get('distance', 0) / 1000
                    monthly_dist[act_date.day - 1] += dist
                    total_dist += dist; total_time += act.get('moving_time', 0)
                    if act.get('average_heartrate'): hr_sum += act.get('average_heartrate'); hr_count += 1
        avg_hr = int(hr_sum / hr_count) if hr_count > 0 else 0
        avg_pace_sec = (total_time / total_dist) if total_dist > 0 else 0
        return {"dists": monthly_dist, "total_dist": f"{total_dist:.2f}", "total_time": f"{total_time//3600:02d}:{(total_time%3600)//60:02d}:{total_time%60:02d}", "avg_pace": f"{int(avg_pace_sec//60)}'{int(avg_pace_sec%60):02d}\"", "avg_hr": str(avg_hr), "range": first_day.strftime('%Y.%m'), "labels": [str(i+1) for i in range(num_days)]}
    except: return None

def create_bar_chart(data, color_hex, mode="WEEKLY", labels=None, font_path=None):
    if mode == "WEEKLY": labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    x_pos = np.arange(len(labels))
    prop = font_manager.FontProperties(fname=font_path) if font_path else None
    fig, ax = plt.subplots(figsize=(10, 5.0), dpi=150)
    fig.patch.set_alpha(0); ax.patch.set_alpha(0)
    bars = ax.bar(x_pos, data, color=color_hex, width=0.6)
    ax.set_xticks(x_pos); ax.set_xticklabels(labels)
    for s in ['top', 'right', 'left']: ax.spines[s].set_visible(False)
    ax.tick_params(axis='x', colors='white')
    if prop:
        for label in ax.get_xticklabels(): label.set_fontproperties(prop); label.set_fontsize(10 if mode=="MONTHLY" else 14)
    ax.tick_params(axis='y', left=False, labelleft=False)
    plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png', transparent=True); buf.seek(0); plt.close(fig)
    return Image.open(buf)

def make_smart_collage(files, target_size):
    tw, th = target_size
    imgs = []
    for f in files:
        try:
            img = Image.open(f)
            img = ImageOps.exif_transpose(img)
            imgs.append(img.convert("RGBA"))
        except:
            continue

    if not imgs: 
        return Image.new("RGBA", (tw, th), (30, 30, 30, 255))
    
    n = len(imgs)
    if n == 1:
        return ImageOps.fit(imgs[0], (tw, th), Image.Resampling.LANCZOS)

    # [핵심] 사진 개수에 따라 행/열을 동적으로 결정
    # 최대한 정사각형에 가깝거나 세로로 긴 매거진 비율 유지
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)

    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    
    for i, img in enumerate(imgs):
        r, c = divmod(i, cols)
        
        # 기본 좌표 계산
        x0 = int(c * tw / cols)
        y0 = int(r * th / rows)
        
        # 마지막 줄 사진들이 비어 보이지 않게 너비를 자동 확장
        # (예: 3장일 때 아래줄에 혼자 있는 사진은 가로로 꽉 채움)
        current_row_count = n % cols if (r == rows - 1 and n % cols != 0) else cols
        if r == rows - 1 and n % cols != 0:
            row_tw = tw / current_row_count
            x0 = int((i % cols) * row_tw)
            x1 = int(((i % cols) + 1) * row_tw)
        else:
            x1 = int((c + 1) * tw / cols)
            
        y1 = int((r + 1) * th / rows)
        
        cell_w = x1 - x0
        cell_h = y1 - y0
        
        resized_img = ImageOps.fit(img, (cell_w, cell_h), Image.Resampling.LANCZOS)
        canvas.paste(resized_img, (x0, y0))

    return canvas

# --- [3. 레이아웃 선언 (최상단 고정)] ---
col_main, col_design = st.columns([1.6, 1], gap="medium")

# --- [4. 인증 및 데이터 연동 - 연동 강화 및 에러 방지 버전] ---

# 1. 세션 상태 초기화 (토큰 및 데이터 저장소)
if 'access_token' not in st.session_state:
    st.session_state['access_token'] = None
if 'cached_acts' not in st.session_state:
    st.session_state['cached_acts'] = []

# 2. URL 파라미터 읽기
q_params = st.query_params

# 시나리오 A: URL에 이미 토큰이 있는 경우 (모바일 리프레시 복구용)
if "token" in q_params:
    st.session_state['access_token'] = q_params["token"]

# 시나리오 B: 스트라바에서 인증 후 돌아온 경우 (code 존재)
if "code" in q_params and not st.session_state['access_token']:
    try:
        # 이 단계에서 딱 한 번만 수행
        res = requests.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": q_params["code"],
                "grant_type": "authorization_code"
            }
        ).json()
        
        if 'access_token' in res:
            new_token = res['access_token']
            st.session_state['access_token'] = new_token
            # [중요] 사용한 code는 URL에서 즉시 제거하고 token을 기록
            st.query_params.clear()
            st.query_params["token"] = new_token
            st.rerun() # 콜백 외부이므로 정상 작동
        else:
            st.error("스트라바로부터 토큰을 받지 못했습니다. API 설정을 확인해주세요.")
    except Exception as e:
        st.error(f"연동 과정 오류: {e}")

# 3. 데이터 로딩 (토큰은 있으나 데이터가 없는 경우만 실행)
if st.session_state['access_token'] and not st.session_state['cached_acts']:
    headers = {'Authorization': f"Bearer {st.session_state['access_token']}"}
    with st.spinner("활동 데이터를 불러오고 있습니다..."):
        r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=50", headers=headers)
        if r.status_code == 200:
            st.session_state['cached_acts'] = r.json()
        elif r.status_code == 401: # 토큰 만료 시
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

acts = st.session_state['cached_acts']

# --- [5. 메인 화면 구성] ---
with col_main:
    st.title("TITAN BOY")
    
    # 1. 변수 초기화 (에러 방지: bg_files를 미리 빈 리스트로 선언)
    bg_files = [] 
    log_file = None
    mode = "DAILY"
    v_act, v_date, v_dist, v_pace, v_time, v_hr = "RUNNING", "2026.02.16", "0.00", "00:00:00", "0'00\"", "0"
    weekly_data, monthly_data, a = None, None, None

    if not st.session_state['access_token']:
        auth_url = (f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}"
                    f"&response_type=code&redirect_uri={ACTUAL_URL}"
                    f"&scope=read,activity:read_all&approval_prompt=force")
        st.link_button("🚀 Strava 연동하기", auth_url, use_container_width=True)
    else:
        if st.button("🔓 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
            
        # 2. 파일 업로더 (여기서 변수가 정의됩니다)
        bg_files = st.file_uploader("📸 배경 사진", type=['jpg','jpeg','png'], accept_multiple_files=True)
        log_file = st.file_uploader("🔘 로고", type=['jpg','jpeg','png'])
        user_graph_file = st.file_uploader("📈 그래프 스크린샷 (선택)", type=['jpg','png','jpeg'], key="user_graph")
                
        mode = st.radio("모드 선택", ["DAILY", "WEEKLY", "MONTHLY"], horizontal=True, key="main_mode_sel")
        
        if acts:
            if mode == "DAILY":
                act_opts = [f"{ac['start_date_local'][:10]} - {ac['name']}" for ac in acts]
                sel_act = st.selectbox("🏃 활동 선택", act_opts)
                a = acts[act_opts.index(sel_act)]
                v_diff_str = ""
                if a:
                    v_act = a['name'].upper()
                    dt_obj = datetime.strptime(a['start_date_local'][:19], "%Y-%m-%dT%H:%M:%S")
                    v_time_str = dt_obj.strftime("%I:%M %p").lower()
                    v_date = f"{a['start_date_local'][:10].replace('-', '.')} {v_time_str}"
                    d_km = a.get('distance', 0)/1000; m_s = a.get('moving_time', 0)
                    v_dist = f"{d_km:.2f}" 
                    v_pace = f"{int((m_s/d_km)//60)}'{int((m_s/d_km)%60):02d}\"" if d_km > 0 else "0'00\""
                    v_time = f"{int(m_s//3600):02d}:{int((m_s%3600)//60):02d}:{int(m_s%60):02d}" if m_s >= 3600 else f"{int(m_s//60):02d}:{int(m_s%60):02d}"
                    v_hr = str(int(a.get('average_heartrate', 0))) if a.get('average_heartrate') else "0"
                
            elif mode == "WEEKLY":
                weeks = sorted(list(set([(datetime.strptime(ac['start_date_local'][:10], "%Y-%m-%d") - timedelta(days=datetime.strptime(ac['start_date_local'][:10], "%Y-%m-%d").weekday())).strftime('%Y-%m-%d') for ac in acts])), reverse=True)
                sel_week = st.selectbox("📅 주차 선택", weeks, format_func=lambda x: f"{x[:4]}-{datetime.strptime(x, '%Y-%m-%d').isocalendar()[1]}주차")              
                weekly_data = get_weekly_stats(acts, sel_week)      
                
                v_diff_str = "" # 초기화
                if weekly_data:
                    v_act = f"{datetime.strptime(sel_week, '%Y-%m-%d').isocalendar()[1]} WEEK"
                    v_date = weekly_data['range']
                    v_dist = weekly_data['total_dist']
                    v_pace = weekly_data['avg_pace']
                    v_time = weekly_data['total_time']
                    v_hr   = weekly_data['avg_hr']
                    
                    # 지난주와 비교
                    prev_week_str = (datetime.strptime(sel_week, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
                    prev_weekly_data = get_weekly_stats(acts, prev_week_str)
                    if prev_weekly_data:
                        diff_val = float(v_dist) - float(prev_weekly_data['total_dist'])
                        v_diff_str = f"({'+' if diff_val >= 0 else ''}{diff_val:.2f} km)"
                
            elif mode == "MONTHLY":
                months = sorted(list(set([ac['start_date_local'][:7] for ac in acts])), reverse=True)
                sel_month = st.selectbox("🗓️ 월 선택", months)
                monthly_data = get_monthly_stats(acts, f"{sel_month}-01")
                
                v_diff_str = "" # 초기화
                if monthly_data:
                    dt_t = datetime.strptime(f"{sel_month}-01", "%Y-%m-%d")
                    v_act = dt_t.strftime("%B").upper()
                    v_date, v_dist, v_time, v_pace, v_hr = monthly_data['range'], monthly_data['total_dist'], monthly_data['total_time'], monthly_data['avg_pace'], monthly_data['avg_hr']
                    
                    # 지난달과 비교
                    curr_date = datetime.strptime(f"{sel_month}-01", "%Y-%m-%d")
                    prev_month_date = (curr_date - timedelta(days=1)).replace(day=1)
                    prev_monthly_data = get_monthly_stats(acts, prev_month_date.strftime("%Y-%m-%d"))
                    if prev_monthly_data:
                        diff_val = float(v_dist) - float(prev_monthly_data['total_dist'])
                        v_diff_str = f"({'+' if diff_val >= 0 else ''}{diff_val:.2f} km)"
# --- [6. 디자인 창 구성] ---
with col_design:
    st.header("🎨 DESIGN")
    with st.expander("✍️ 텍스트 수정"):
        v_act = st.text_input("활동명", v_act); v_date = st.text_input("날짜", v_date)
        v_dist = st.text_input("거리 km", v_dist); v_time = st.text_input("시간", v_time)
        v_pace = st.text_input("페이스", v_pace); v_hr = st.text_input("심박 bpm", v_hr)

    with st.expander("💄 매거진 스타일", expanded=True):
        # --- [추가된 스위치들] ---
        show_vis = st.toggle("지도/그래프 표시", value=True, key="sw_vis")
        show_box = st.toggle("데이터 박스 표시", value=True, key="sw_box")
        use_shadow = st.toggle("글자 그림자 효과", value=True, key="sw_shadow")
        # ----------------------
        border_thick = st.slider("프레임 테두리 두께", 0, 50, 0)
        COLOR_OPTS = {"Black": "#000000", "Yellow": "#FFD700", "White": "#FFFFFF", "Orange": "#FF4500", "Blue": "#00BFFF", "Grey": "#AAAAAA"}
        m_color = COLOR_OPTS[st.selectbox("포인트 컬러", list(COLOR_OPTS.keys()), index=1,  key="m_col_sel")]
        sub_color = COLOR_OPTS[st.selectbox("서브 컬러", list(COLOR_OPTS.keys()), index=2, key="s_col_sel")]

    default_idx = 0 if mode == "DAILY" else 1
    box_orient = st.radio(
    "박스 방향", 
    ["Vertical", "Horizontal"], 
    index=default_idx, 
    horizontal=True,
    key=f"orient_{mode}" )     
    sel_font = st.selectbox("폰트", ["BlackHanSans", "KirangHaerang", "Lacquer"])

    with st.expander("📍 위치/크기 조절"):
        rx, ry = st.number_input("박스 X", 0, 1080, 40 if box_orient=="Horizontal" else 80), st.number_input("박스 Y", 0, 1920, 250 if box_orient=="Horizontal" else 1200)
        rw, rh = st.number_input("박스 너비", 100, 1080, 1000 if box_orient=="Horizontal" else 450), st.number_input("박스 높이", 100, 1920, 350 if box_orient=="Horizontal" else 650)
        box_alpha = st.slider("박스 투명도", 0, 255, 0)
        vis_sz_adj = st.slider("지도/그래프 크기", 50, 1080, 180 if mode=="DAILY" else 1080)
        vis_alpha = st.slider("지도/그래프 투명도", 0, 255, 255)
        
# --- [7. 미리보기 렌더링] ---
with col_main:
    st.subheader("🖼️ PREVIEW")
    data_ready = (mode == "DAILY" and a) or (mode == "WEEKLY" and weekly_data) or (mode == "MONTHLY" and monthly_data)
    
    if data_ready:
        try:
            CW, CH = (1080, 1920) if mode == "DAILY" else (1080, 1350)
            # 90-30-60-23 가이드 적용
            f_t, f_d, f_n, f_l = load_font(sel_font, 70), load_font(sel_font, 30), load_font(sel_font, 50), load_font(sel_font, 25)
            
            canvas = make_smart_collage(bg_files, (CW, CH)) if bg_files else Image.new("RGBA", (CW, CH), (20, 20, 20, 255))
            overlay = Image.new("RGBA", (CW, CH), (0,0,0,0)); draw = ImageDraw.Draw(overlay)
            items = [("distance", f"{v_dist} km", v_diff_str), ("pace", v_pace, ""), ("time", v_time, ""), ("avg bpm", f"{v_hr} bpm", "")]
            if border_thick > 0:
                # 캔버스 외곽선을 따라 테두리를 그립니다. 
                # outline=m_color (포인트 컬러 사용), width=border_thick (슬라이더 값 적용)
                draw.rectangle([(0, 0), (CW-1, CH-1)], outline=m_color, width=border_thick)
            
            # 1. 데이터 박스 (show_box가 True일 때만)
            if show_box:
                draw.rectangle([rx, ry, rx + rw, ry + rh], fill=(0,0,0,box_alpha))
                if box_orient == "Vertical":
                    draw_styled_text(draw, (rx + 40, ry + 30), v_act, f_t, m_color, shadow=use_shadow)
                    draw_styled_text(draw, (rx + 40, ry + 110), v_date, f_d, "#AAAAAA", shadow=use_shadow)
                    y_c = ry + 200
                    for lab, val, diff in items:
                        draw_styled_text(draw, (rx + 40, y_c), lab.lower(), f_l, "#AAAAAA", shadow=use_shadow)
                        draw_styled_text(draw, (rx + 40, y_c + 35), val.lower(), f_n, sub_color, shadow=use_shadow)
                        if diff: # 증감 데이터가 있으면 표시
                            draw_styled_text(draw, (rx + 230, y_c + 35), diff, f_l, m_color, shadow=use_shadow)
                        y_c += 105
                else: # Horizontal
                    title_w = draw.textlength(v_act, f_t)
                    draw_styled_text(draw, (rx + (rw-title_w)//2, ry+35), v_act, f_t, m_color, shadow=use_shadow)
                    draw_styled_text(draw, (rx + (rw-draw.textlength(v_date, f_d))//2, ry+110), v_date, f_d, "#AAAAAA", shadow=use_shadow)
                    sec_w = rw // 4
                    for i, (lab, val, diff) in enumerate(items):
                        cx = rx + (i * sec_w) + (sec_w // 2)
                        draw_styled_text(draw, (cx - draw.textlength(lab.lower(), f_l)//2, ry+160), lab.lower(), f_l, "#AAAAAA", shadow=use_shadow)
                        draw_styled_text(draw, (cx - draw.textlength(val.lower(), f_n)//2, ry+195), val.lower(), f_n, sub_color, shadow=use_shadow)
                        if diff: # 가로 모드에서는 수치 바로 아래(ry+250)에 표시
                            draw_styled_text(draw, (cx - draw.textlength(diff, f_l)//2, ry+250), diff, f_l, m_color, shadow=use_shadow)
            # 2. 지도 및 그래프 (show_vis가 True일 때만)
            if show_vis:
                vis_layer = None
                vis_sz = vis_sz_adj
                
                # [A] 사용자가 그래프 이미지를 직접 올린 경우 최우선 표시
                if user_graph_file:
                    user_img = Image.open(user_graph_file).convert("RGBA")
                    w_h_ratio = user_img.height / user_img.width
                    vis_layer = user_img.resize((vis_sz, int(vis_sz * w_h_ratio)), Image.Resampling.LANCZOS)
                    # 투명도 적용
                    vis_layer.putalpha(vis_layer.getchannel('A').point(lambda x: x * (vis_alpha / 255)))

                # [B] 직접 올린 게 없으면 기존 스트라바 데이터로 생성
                elif mode == "DAILY" and a and a.get('map', {}).get('summary_polyline'):
                    pts = polyline.decode(a['map']['summary_polyline'])
                    lats, lons = zip(*pts)
                    vis_layer = Image.new("RGBA", (vis_sz, vis_sz), (0,0,0,0)); m_draw = ImageDraw.Draw(vis_layer)
                    def tr(la, lo): return 15+(lo-min(lons))/(max(lons)-min(lons)+1e-5)*(vis_sz-30), (vis_sz-15)-(la-min(lats))/(max(lats)-min(lats)+1e-5)*(vis_sz-30)
                    m_draw.line([tr(la, lo) for la, lo in pts], fill=hex_to_rgba(m_color, vis_alpha), width=6)
                    
                elif mode in ["WEEKLY", "MONTHLY"] and (weekly_data or monthly_data):
                    d_obj = weekly_data if mode == "WEEKLY" else monthly_data
                    chart_img = create_bar_chart(d_obj['dists'], m_color, mode=mode, labels=d_obj.get('labels'), font_path=None)
                    target_h = int(CH * 0.7)
                    vis_layer = chart_img.resize((vis_sz, int(chart_img.size[1]*(vis_sz/chart_img.size[0]))), Image.Resampling.LANCZOS)
                    vis_layer.putalpha(vis_layer.getchannel('A').point(lambda x: x * (vis_alpha / 255)))

                # [C] 최종 합성 위치 결정
                if vis_layer:
                    if box_orient == "Vertical": 
                        # 세로 모드: 박스 바로 위
                        m_pos = (rx, max(5, ry - vis_layer.height - 20))
                    else: 
                        m_pos_x = (CW - vis_layer.width) // 2
                        m_pos_y = CH - vis_layer.height - 50                      
                        m_pos = (m_pos_x, m_pos_y)
                    
                    overlay.paste(vis_layer, (int(m_pos[0]), int(m_pos[1])), vis_layer)

            # 3. 로고 (항상 표시 또는 로직 유지)
            if log_file:
                ls, margin = 100, 40
                l_img = ImageOps.fit(Image.open(log_file).convert("RGBA"), (ls, ls))
                mask = Image.new('L', (ls, ls), 0); ImageDraw.Draw(mask).ellipse((0, 0, ls, ls), fill=255); l_img.putalpha(mask)
                overlay.paste(l_img, (CW - ls - margin, margin), l_img)

            # 1. 이미지 결과 출력
            final = Image.alpha_composite(canvas, overlay).convert("RGB")
            st.image(final, width=360)
            
            # 2. 이미지 데이터 준비
            buf = io.BytesIO()
            final.save(buf, format="JPEG", quality=95)
            img_bytes = buf.getvalue()
            img_64 = base64.b64encode(img_bytes).decode()

            # 3. [공유하기] 버튼 (HTML/JS) - 디자인 보강
            share_btn_html = f"""
                <div style="margin-bottom: 10px;">
                    <button onclick="share()" style="
                        width:100%; padding:12px; 
                        background: linear-gradient(45deg, #405de6, #5851db, #833ab4, #c13584, #e1306c, #fd1d1d);
                        color:white; border-radius:8px; border:none; 
                        cursor:pointer; font-weight:bold; font-size:16px;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
                    ">
                        📲 공유
                    </button>
                </div>
                <script>
                async function share() {{
                    try {{
                        const blob = await (await fetch('data:image/jpeg;base64,{img_64}')).blob();
                        const file = new File([blob], 'run_record.jpg', {{type: 'image/jpeg'}});
                        if (navigator.share) {{
                            await navigator.share({{
                                files: [file],
                                title: 'TITAN BOY RUN',
                                text: '오늘의 러닝 기록!'
                            }});
                        }} else {{
                            alert('현재 브라우저가 공유 기능을 지원하지 않습니다. 아래 다운로드 버튼을 이용해주세요.');
                        }}
                    }} catch (e) {{
                        console.log('공유 취소 또는 오류:', e);
                    }}
                }}
                </script>
            """
            components.html(share_btn_html, height=65)
           # 3. [다운로드] 버튼 (공유 버튼과 수직 정렬 맞춤)
            st.download_button(
                label=f"📸 {mode} DOWLOAD", 
                data=img_bytes, 
                file_name=f"{mode.lower()}.jpg", 
                use_container_width=True
            )
            
        except Exception as e:
            st.error(f"렌더링 오류 발생: {e}")
            
        except Exception as e:
            st.error(f"렌더링 오류 발생: {e}")
