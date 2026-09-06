import streamlit as st
import datetime
import pandas as pd
import re
import json
import gspread
import calendar
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

# 🚨 Streamlit 화면 설정
st.set_page_config(page_title="공판집 - 공무원 시험 판례 모음집", page_icon="⚖️", layout="wide")

# --- 🔒 비밀번호 잠금 시스템 ---
def check_password():
    CORRECT_PASSWORD = st.secrets.get("password", "7777")
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 공판집 - 공무원 시험 판례 모음집")
        st.markdown("안전한 접속을 위해 비밀번호를 입력해주세요.")
        
        pwd_input = st.text_input("비밀번호", type="password")
        
        if st.button("접속하기", type="primary"):
            if pwd_input == CORRECT_PASSWORD:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ 비밀번호가 틀렸습니다.")
        return False
    return True

if not check_password():
    st.stop()


# --- ☁️ 구글 스프레드시트 연동 시스템 ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_gspread_client():
    creds_dict = json.loads(st.secrets["google_json"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def get_worksheet(sheet_name):
    client = get_gspread_client()
    url = st.secrets["sheet_url"]
    doc = client.open_by_url(url)
    return doc.worksheet(sheet_name)

# 📌 판례 데이터
@st.cache_data(ttl=60)
def load_precedents_df():
    try:
        ws = get_worksheet("precedents")
        records = ws.get_all_records()
    except WorksheetNotFound:
        return pd.DataFrame()
    cols = ["id", "main_cat", "mid_cat", "sub_cat", "p_number", "p_title", "p_content", "p_tags", "reg_date", "p_desc", "p_grade", "p_location", "p_related", "p_result", "read_count", "p_exams"]
    if not records: return pd.DataFrame(columns=cols)
    df = pd.DataFrame(records)
    if 'id' in df.columns: df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
    if 'read_count' in df.columns: df['read_count'] = pd.to_numeric(df['read_count'], errors='coerce').fillna(0).astype(int)
    return df

def save_precedents_df(df):
    ws = get_worksheet("precedents")
    ws.clear()
    out_df = df.copy().fillna("")
    for col in out_df.columns:
        out_df[col] = out_df[col].apply(lambda x: int(x) if isinstance(x, float) and x.is_integer() else str(x))
    data = [out_df.columns.values.tolist()] + out_df.values.tolist()
    ws.update(values=data, range_name="A1")
    load_precedents_df.clear()

# 📌 지문 데이터
@st.cache_data(ttl=60)
def load_passages_df():
    try:
        ws = get_worksheet("passages")
        records = ws.get_all_records()
    except WorksheetNotFound:
        return pd.DataFrame(columns=["id", "subject", "passage_text", "source", "related_p_number", "is_true", "explanation", "reg_date"])
    cols = ["id", "subject", "passage_text", "source", "related_p_number", "is_true", "explanation", "reg_date"]
    if not records: return pd.DataFrame(columns=cols)
    df = pd.DataFrame(records)
    if 'id' in df.columns: df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
    return df

def save_passages_df(df):
    ws = get_worksheet("passages")
    ws.clear()
    out_df = df.copy().fillna("")
    for col in out_df.columns:
        out_df[col] = out_df[col].apply(lambda x: int(x) if isinstance(x, float) and x.is_integer() else str(x))
    data = [out_df.columns.values.tolist()] + out_df.values.tolist()
    ws.update(values=data, range_name="A1")
    load_passages_df.clear()

# 📌 일일 학습 통계 데이터 (reg_count 추가)
@st.cache_data(ttl=60)
def load_activity_log():
    try:
        ws = get_worksheet("activity_log")
        records = ws.get_all_records()
    except WorksheetNotFound:
        return pd.DataFrame(columns=["date", "read_count", "ox_count", "reg_count"])
    cols = ["date", "read_count", "ox_count", "reg_count"]
    if not records: return pd.DataFrame(columns=cols)
    df = pd.DataFrame(records)
    if 'reg_count' not in df.columns: df['reg_count'] = 0
    return df

def save_activity_log(df):
    ws = get_worksheet("activity_log")
    ws.clear()
    out_df = df.copy().fillna(0)
    data = [out_df.columns.values.tolist()] + out_df.values.tolist()
    ws.update(values=data, range_name="A1")
    load_activity_log.clear()

def log_activity(activity_type):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    df = load_activity_log()
    if df.empty or today not in df['date'].values:
        new_row = pd.DataFrame([{"date": today, "read_count": 0, "ox_count": 0, "reg_count": 0}])
        df = pd.concat([df, new_row], ignore_index=True)
    idx = df[df['date'] == today].index[0]
    if activity_type == 'read': df.loc[idx, "read_count"] = int(df.loc[idx, "read_count"]) + 1
    elif activity_type == 'ox': df.loc[idx, "ox_count"] = int(df.loc[idx, "ox_count"]) + 1
    elif activity_type == 'reg': df.loc[idx, "reg_count"] = int(df.loc[idx, "reg_count"]) + 1
    save_activity_log(df)

# 📌 카테고리 데이터
@st.cache_data(ttl=60)
def load_categories():
    try:
        ws = get_worksheet("categories")
        records = ws.get_all_records()
    except WorksheetNotFound:
        return {"헌법": {}, "행정법": {}}
    cats = {"헌법": {}, "행정법": {}}
    for row in records:
        main, mid, sub = row.get("main_cat"), row.get("mid_cat"), row.get("sub_cat")
        if main and mid:
            if mid not in cats[main]: cats[main][mid] = []
            if sub and sub not in cats[main][mid]: cats[main][mid].append(sub)
    return cats

def add_category(main_cat, mid_cat, sub_cat=""):
    ws = get_worksheet("categories")
    records = ws.get_all_records()
    new_id = 1 if not records else max([int(r.get("id", 0)) for r in records]) + 1
    for r in records:
        if r.get("main_cat") == main_cat and r.get("mid_cat") == mid_cat and r.get("sub_cat") == sub_cat: return False
    ws.append_row([new_id, main_cat, mid_cat, sub_cat])
    load_categories.clear()
    return True

def delete_category(main_cat, mid_cat, sub_cat=None):
    ws = get_worksheet("categories")
    records = ws.get_all_records()
    if not records: return
    df = pd.DataFrame(records)
    if sub_cat is None:
        df = df[~((df['main_cat'] == main_cat) & (df['mid_cat'] == mid_cat))]
    else:
        df = df[~((df['main_cat'] == main_cat) & (df['mid_cat'] == mid_cat) & (df['sub_cat'] == sub_cat))]
    ws.clear()
    out_df = df.fillna("").astype(str)
    data = [out_df.columns.values.tolist()] + out_df.values.tolist()
    ws.update(values=data, range_name="A1")
    load_categories.clear()

def sort_exams_desc(exam_text):
    if not exam_text: return ""
    lines = [line.strip() for line in str(exam_text).split('\n') if line.strip()]
    def get_year(s):
        match = re.search(r'\d{4}', s)
        return int(match.group()) if match else 0
    return "\n".join(sorted(lines, key=get_year, reverse=True))

def change_menu(target_menu):
    st.session_state['menu_choice'] = target_menu

categories = load_categories()
df_all_precedents = load_precedents_df()

# --- 커스텀 CSS ---
st.markdown("""
    <style>
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    hr.thin-line { border: 0; border-top: 1px solid #e0e0e0; margin: 5px 0 5px 0; }
    .tag-badge { background-color: #e9ecef; color: #495057; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: 500; margin-right: 5px; display: inline-block; }
    .tag-badge-s { background-color: #ffe3e3; color: #c92a2a; padding: 4px 10px; border-radius: 15px; font-size: 13px; font-weight: 500; margin-right: 5px; display: inline-block; }
    /* 다홍색 캘린더 버튼을 위한 스타일 (Primary button) */
    div.stButton > button[kind="primary"] { background-color: #FF7F50; border-color: #FF7F50; color: white; }
    div.stButton > button[kind="primary"]:hover { background-color: #FF6347; border-color: #FF6347; }
    </style>
""", unsafe_allow_html=True)


# --- 사이드바 네비게이션 ---
if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "📊 홈 (대시보드)"

with st.sidebar:
    st.title("⚖️ 공판집")
    
    menu_options = [
        "📊 홈 (대시보드)", 
        "🏛️ 헌법 판례집", 
        "⚖️ 행정법 판례집",
        "🏷️ 태그 모아보기",
        "🎲 헌법 랜덤 복습", 
        "🎲 행정법 랜덤 복습", 
        "📝 헌법 지문 복습", 
        "📝 행정법 지문 복습", 
        "✅ O/X 문제풀기",
        "📁 카테고리 관리", 
        "✍️ 판례 등록", 
        "✍️ 지문 등록"
    ]
    
    menu = st.radio("메뉴", menu_options, key="menu_choice", label_visibility="collapsed")
    st.write("---")
    st.caption("☁️ 공판집 클라우드 연동됨")


# --- 1. 홈 (대시보드) ---
if menu == "📊 홈 (대시보드)":
    st.title("⚖️ 공판집 - 공무원 시험 판례 모음집")
    
    # 📌 연속 학습일 계산 (잔디 심기)
    df_log = load_activity_log()
    streak = 0
    today_date = datetime.datetime.now().date()
    yesterday_date = today_date - datetime.timedelta(days=1)
    
    if not df_log.empty:
        df_log['date_obj'] = pd.to_datetime(df_log['date']).dt.date
        
        # 학습 활동이 하나라도 있는 날짜만 추출
        active_days = df_log[(df_log['read_count'] > 0) | (df_log['ox_count'] > 0) | (df_log['reg_count'] > 0)]
        dates_sorted = sorted(active_days['date_obj'].unique(), reverse=True)
        
        if dates_sorted and (dates_sorted[0] == today_date or dates_sorted[0] == yesterday_date):
            current = dates_sorted[0]
            streak = 1
            for d in dates_sorted[1:]:
                if d == current - datetime.timedelta(days=1):
                    streak += 1
                    current = d
                else:
                    break
                    
    # 동기부여 문구
    if streak > 0:
        st.markdown(f"<h2 style='text-align: center; color: #FF7F50;'>🔥 {streak}일 연속 학습 완료! 🔥</h2>", unsafe_allow_html=True)
    else:
        st.markdown(f"<h2 style='text-align: center; color: #777;'>🌱 오늘부터 다시 학습을 시작해보세요!</h2>", unsafe_allow_html=True)
    
    st.write("---")
    
    # 📌 통계 메트릭
    if not df_all_precedents.empty:
        total = len(df_all_precedents)
        high_grade = len(df_all_precedents[df_all_precedents['p_grade'].isin(['S', 'A+'])])
        const_total = len(df_all_precedents[df_all_precedents['main_cat'] == '헌법'])
        admin_total = len(df_all_precedents[df_all_precedents['main_cat'] == '행정법'])
    else:
        total = high_grade = const_total = admin_total = 0
        
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("총 등록 판례", f"{total} 개")
    with col2: st.metric("S 및 A+ 판례 (핵심)", f"{high_grade} 개")
    with col3:
        st.metric("🏛️ 헌법 판례", f"{const_total} 개")
        st.button("헌법 판례집 ➡️", key="go_const", on_click=change_menu, args=("🏛️ 헌법 판례집",), use_container_width=True)
    with col4:
        st.metric("⚖️ 행정법 판례", f"{admin_total} 개")
        st.button("행정법 판례집 ➡️", key="go_admin", on_click=change_menu, args=("⚖️ 행정법 판례집",), use_container_width=True)
    
    st.write("---")
    
    # 📌 다홍색 잔디 달력 (Calendar)
    st.subheader("📅 나의 학습 달력 (잔디 심기)")
    
    if 'cal_year' not in st.session_state: st.session_state.cal_year = today_date.year
    if 'cal_month' not in st.session_state: st.session_state.cal_month = today_date.month
    if 'sel_date' not in st.session_state: st.session_state.sel_date = today_date

    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    with col_nav1:
        if st.button("◀ 이전 달", use_container_width=True):
            if st.session_state.cal_month == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            else:
                st.session_state.cal_month -= 1
            st.rerun()
    with col_nav2:
        st.markdown(f"<h3 style='text-align: center; margin-top: 0;'>{st.session_state.cal_year}년 {st.session_state.cal_month}월</h3>", unsafe_allow_html=True)
    with col_nav3:
        if st.button("다음 달 ▶", use_container_width=True):
            if st.session_state.cal_month == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            else:
                st.session_state.cal_month += 1
            st.rerun()

    # 달력 그리기 (일요일 시작)
    cal = calendar.Calendar(firstweekday=6)
    month_cal = cal.monthdayscalendar(st.session_state.cal_year, st.session_state.cal_month)
    weekdays = ["일", "월", "화", "수", "목", "금", "토"]
    
    cols = st.columns(7)
    for i, w in enumerate(weekdays):
        cols[i].markdown(f"<div style='text-align:center; font-weight:bold; padding-bottom: 10px;'>{w}</div>", unsafe_allow_html=True)
        
    for week in month_cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
            else:
                curr_date_str = f"{st.session_state.cal_year}-{st.session_state.cal_month:02d}-{day:02d}"
                has_activity = False
                
                if not df_log.empty and curr_date_str in df_log['date'].values:
                    log_row = df_log[df_log['date'] == curr_date_str].iloc[0]
                    if int(log_row.get('read_count', 0)) > 0 or int(log_row.get('ox_count', 0)) > 0 or int(log_row.get('reg_count', 0)) > 0:
                        has_activity = True
                
                # 활동이 있으면 다홍색(primary), 없으면 회색(secondary)
                btn_type = "primary" if has_activity else "secondary"
                
                if cols[i].button(str(day), key=f"cal_{curr_date_str}", type=btn_type, use_container_width=True):
                    st.session_state.sel_date = datetime.date(st.session_state.cal_year, st.session_state.cal_month, day)
                    st.rerun()

    # 📌 선택한 날짜 상세 기록
    st.write("")
    sel_date_str = st.session_state.sel_date.strftime("%Y-%m-%d")
    st.markdown(f"#### 🔍 {st.session_state.sel_date.strftime('%Y년 %m월 %d일')} 상세 기록")
    
    sel_read, sel_ox, sel_reg = 0, 0, 0
    if not df_log.empty and sel_date_str in df_log['date'].values:
        log_row = df_log[df_log['date'] == sel_date_str].iloc[0]
        sel_read = int(log_row.get('read_count', 0))
        sel_ox = int(log_row.get('ox_count', 0))
        sel_reg = int(log_row.get('reg_count', 0))
    
    col_d1, col_d2, col_d3 = st.columns(3)
    col_d1.metric("✍️ 등록한 데이터(판례/지문)", f"{sel_reg} 개")
    col_d2.metric("📖 판례 회독 수", f"{sel_read} 번")
    col_d3.metric("✅ O/X 문제 풀이", f"{sel_ox} 개")

    st.write("---")
    
    # 📌 최근 등록 판례 (복구 완료)
    st.subheader("📚 최근 등록 판례 검색")
    search_query = st.text_input("🔍 Search", placeholder="판례 번호, 제목, 내용 등 통합 검색", label_visibility="collapsed")
    
    if not df_all_precedents.empty:
        display_df = df_all_precedents.copy()
        if search_query:
            mask = display_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False, na=False)).any(axis=1)
            display_df = display_df[mask]
        
        display_df = display_df.sort_values(by='id', ascending=False)
        display_df = display_df.rename(columns={"main_cat": "과목", "p_number": "판례번호", "p_title": "제목", "p_grade": "중요도", "read_count": "회독수"})
        display_df = display_df[["과목", "판례번호", "제목", "중요도", "회독수", "p_tags"]]
        
        if not search_query: 
            display_df = display_df.head(20)
            st.caption("최근 등록된 판례 최대 20개를 보여줍니다. 전체 판례는 판례집 메뉴를 이용하세요.")
            
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("등록된 판례가 없습니다.")


# --- 🏷️ 태그 모아보기 ---
elif menu == "🏷️ 태그 모아보기":
    st.title("🏷️ 태그 모아보기")
    st.markdown("등록된 태그를 기반으로 헌법과 행정법 판례를 가리지 않고 한눈에 모아볼 수 있습니다.")
    st.write("---")
    
    if df_all_precedents.empty:
        st.info("아직 등록된 판례가 없습니다.")
    else:
        all_tags = []
        for tags_str in df_all_precedents['p_tags'].dropna():
            if str(tags_str).strip():
                tags = [t.strip() for t in str(tags_str).split(',') if t.strip()]
                all_tags.extend(tags)
                
        if not all_tags:
            st.info("아직 판례에 등록된 태그가 없습니다. 판례 등록 시 태그를 달아보세요!")
        else:
            tag_counts = pd.Series(all_tags).value_counts()
            
            st.markdown("##### 🔥 자주 사용하는 인기 태그")
            top_tags = tag_counts.head(10)
            tag_html = ""
            for tag, count in top_tags.items():
                tag_html += f"<span class='tag-badge-s'>#{tag} ({count})</span>"
            st.markdown(tag_html, unsafe_allow_html=True)
            st.write("")
            
            st.markdown("##### 🔍 태그로 판례 찾기")
            selected_tags = st.multiselect("원하는 태그를 선택하세요", list(tag_counts.index), placeholder="여기를 눌러 태그 선택")
            
            if selected_tags:
                st.write("---")
                st.markdown(f"**선택한 태그:** {', '.join(selected_tags)}")
                
                def check_tags(x):
                    p_tags = [t.strip() for t in str(x).split(',') if str(x).strip()]
                    return all(tag in p_tags for tag in selected_tags)
                    
                mask = df_all_precedents['p_tags'].apply(check_tags)
                filtered_df = df_all_precedents[mask].sort_values(by='p_grade', ascending=True)
                
                if filtered_df.empty:
                    st.warning("해당 태그들이 모두 포함된 판례가 없습니다.")
                else:
                    st.success(f"총 {len(filtered_df)}개의 판례가 검색되었습니다.")
                    for p in filtered_df.to_dict('records'):
                        grade_mark = f"⭐ {p.get('p_grade', 'C')}"
                        subject_mark = f"[{p.get('main_cat')}]"
                        with st.expander(f"{subject_mark} {grade_mark} {p.get('p_number', '')} {p.get('p_title', '')}"):
                            tags_badge = "".join([f"<span class='tag-badge'>#{t.strip()}</span>" for t in str(p.get('p_tags', '')).split(',') if t.strip()])
                            st.markdown(tags_badge, unsafe_allow_html=True)
                            st.write("")
                            st.markdown(f"**카테고리:** {p['main_cat']} > {p['mid_cat']} > {p['sub_cat']}")
                            if p.get('p_related'): st.markdown(f"**🔗 연관 조문:** {p['p_related']}")
                            st.write("---")
                            st.info(p.get('p_desc', '설명이 없습니다.'))
                            st.caption(f"📝 요지: {str(p.get('p_content', ''))[:100]}...")


# --- 2. 과목별 판례집 ---
elif menu in ["🏛️ 헌법 판례집", "⚖️ 행정법 판례집"]:
    subject = "헌법" if menu == "🏛️ 헌법 판례집" else "행정법"
    st.title(menu)
    st.write("---")
    
    search_key = f'search_{subject}'
    subject_search = st.text_input("🔍 판례 검색", placeholder="판례 번호, 제목 등 검색", key=search_key)
    
    col_mid, col_sub, col_grade = st.columns(3)
    mid_options = ["전체"] + list(categories.get(subject, {}).keys())
    with col_mid: sel_mid = st.selectbox("📂 목차 선택", mid_options)
    with col_sub:
        sel_sub = st.selectbox("📑 소분류 선택", ["전체"] + categories.get(subject, {}).get(sel_mid, [])) if sel_mid != "전체" else st.selectbox("📑 소분류 선택", ["전체"], disabled=True)
    with col_grade: sel_grade = st.selectbox("⭐ 중요도 선택", ["전체", "S", "A+", "A", "B+", "B", "C+", "C"])
            
    st.write("") 
    st.markdown("<hr class='thin-line'>", unsafe_allow_html=True)
    c_sort1, c_sort2 = st.columns([3, 7])
    with c_sort1: sort_order = st.radio("정렬 기준", ["중요도순", "최신순"], horizontal=True, label_visibility="collapsed")

    df = df_all_precedents.copy()
    if not df.empty:
        df = df[df['main_cat'] == subject]
        if subject_search:
            mask = df.astype(str).apply(lambda x: x.str.contains(subject_search, case=False, na=False)).any(axis=1)
            df = df[mask]
        if sel_mid != "전체": df = df[df['mid_cat'] == sel_mid]
        if sel_sub != "전체": df = df[df['sub_cat'] == sel_sub]
        if sel_grade != "전체": df = df[df['p_grade'] == sel_grade]
            
        if sort_order == "중요도순":
            grade_map = {'S': 1, 'A+': 2, 'A': 3, 'B+': 4, 'B': 5, 'C+': 6, 'C': 7}
            df['grade_sort'] = df['p_grade'].map(grade_map).fillna(8)
            df = df.sort_values(by=['grade_sort', 'id'], ascending=[True, False])
        else:
            df = df.sort_values(by='id', ascending=False)
        rows = df.to_dict('records')
    else:
        rows = []

    total_items = len(rows)
    with c_sort2: st.markdown(f"<div style='padding-top: 10px; color: #777; font-size: 14px;'>검색된 판례: 총 <b>{total_items}</b>개</div>", unsafe_allow_html=True)
    st.markdown("<hr class='thin-line'>", unsafe_allow_html=True)

    if total_items == 0:
        st.info("해당 조건에 맞는 판례가 없습니다.")
    else:
        page_key = f'current_page_{subject}'
        if page_key not in st.session_state: st.session_state[page_key] = 1
        items_per_page = 10
        total_pages = (total_items - 1) // items_per_page + 1
        if st.session_state[page_key] > total_pages: st.session_state[page_key] = total_pages
        
        start_idx = (st.session_state[page_key] - 1) * items_per_page
        paged_rows = rows[start_idx : start_idx + items_per_page]

        for p in paged_rows:
            grade_mark = f"⭐ {p.get('p_grade', 'C')}"
            result_mark = f"[{p.get('p_result')}] " if subject == '헌법' and p.get('p_result') else ""
            rc = int(p.get('read_count', 0))
            read_badge = f" [🔄 {rc}회독]" if rc > 0 else ""
            
            with st.expander(f"{grade_mark} {result_mark}{p.get('p_number', '')} {p.get('p_title', '')}{read_badge}"):
                tab_view, tab_edit = st.tabs(["👁️ 열람", "✏️ 수정 및 삭제"])
                
                with tab_view:
                    st.markdown(f"**카테고리:** {p['main_cat']} > {p['mid_cat']} > {p['sub_cat']}")
                    if p.get('p_location'): st.markdown(f"**📖 교재 수록 위치:** {p['p_location']}")
                    if p.get('p_related'): st.markdown(f"**🔗 연관 판례 및 조문:** {p['p_related']}")
                    if p.get('p_tags'): 
                        tags_html = "".join([f"<span class='tag-badge'>#{t.strip()}</span>" for t in str(p['p_tags']).split(',') if t.strip()])
                        st.markdown(f"**🏷️ 태그:** {tags_html}", unsafe_allow_html=True)
                    
                    st.write("---")
                    st.write("**💡 판례 설명 (해설)**")
                    st.info(p.get('p_desc', '설명이 없습니다.'))
                    st.write("**📄 판례 요지 (원문)**")
                    st.write(p.get('p_content', '내용이 없습니다.'))
                    if p.get('p_exams'):
                        st.write("---")
                        st.write("**🏆 시험 출제 내역**")
                        for exam in str(p['p_exams']).split('\n'):
                            if exam.strip(): st.markdown(f"- {exam}")
                    
                with tab_edit:
                    with st.form(f"edit_form_{p['id']}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            e_grade = st.selectbox("⭐ 중요도", ["S", "A+", "A", "B+", "B", "C+", "C"], index=["S", "A+", "A", "B+", "B", "C+", "C"].index(p.get('p_grade', 'C')))
                            e_number = st.text_input("📌 판례 번호", str(p.get('p_number', '')))
                            e_loc = st.text_input("📖 교재 수록 위치", str(p.get('p_location', '')))
                        with c2:
                            e_title = st.text_input("📝 판례 제목", str(p.get('p_title', '')))
                            e_rel = st.text_input("🔗 연관 판례 및 조문", str(p.get('p_related', '')))
                            e_tags = st.text_input("🏷️ 태그 (쉼표 구분)", str(p.get('p_tags', '')))
                        
                        e_desc = st.text_area("💡 판례 설명", str(p.get('p_desc', '')), height=100)
                        e_content = st.text_area("📄 판례 요지", str(p.get('p_content', '')), height=150)
                        e_exams = st.text_area("🏆 시험 출제 내역", str(p.get('p_exams', '')), height=100)
                        
                        if st.form_submit_button("수정 저장", use_container_width=True):
                            df_update = load_precedents_df()
                            idx = df_update[df_update['id'].astype(str) == str(p['id'])].index
                            if not idx.empty:
                                df_update.loc[idx[0], "p_grade"] = e_grade
                                df_update.loc[idx[0], "p_number"] = e_number
                                df_update.loc[idx[0], "p_title"] = e_title
                                df_update.loc[idx[0], "p_location"] = e_loc
                                df_update.loc[idx[0], "p_related"] = e_rel
                                df_update.loc[idx[0], "p_tags"] = e_tags
                                df_update.loc[idx[0], "p_desc"] = e_desc
                                df_update.loc[idx[0], "p_content"] = e_content
                                df_update.loc[idx[0], "p_exams"] = sort_exams_desc(e_exams)
                                save_precedents_df(df_update)
                                st.success("✅ 수정 완료!")
                                st.rerun()

                    with st.expander("🚨 판례 삭제 (주의)"):
                        if st.button("🗑️ 이 판례 삭제하기", key=f"del_btn_{p['id']}", type="primary"):
                            df_delete = load_precedents_df()
                            df_delete = df_delete[df_delete['id'].astype(str) != str(p['id'])]
                            save_precedents_df(df_delete)
                            st.success("🗑️ 삭제되었습니다.")
                            st.rerun()
                            
        cols = st.columns(total_pages)
        for i in range(total_pages):
            with cols[i]:
                if st.button(str(i+1), key=f"page_{subject}_{i}", type="primary" if st.session_state[page_key]==i+1 else "secondary"):
                    st.session_state[page_key] = i+1
                    st.rerun()


# --- 3. 가중치 랜덤 복습 기능 (판례) ---
elif menu in ["🎲 헌법 랜덤 복습", "🎲 행정법 랜덤 복습"]:
    subject = "헌법" if "헌법" in menu else "행정법"
    st.title(f"🎲 {subject} 랜덤 복습")
    st.markdown(f"등록된 **{subject} 판례** 중 핵심 판례 위주로 무작위 출제됩니다. 내용을 먼저 떠올려 보세요!")
    st.write("---")
    
    if st.button("🔄 새로운 판례 불러오기", use_container_width=True):
        df = load_precedents_df()
        if not df.empty:
            df_subj = df[df['main_cat'] == subject]
            if not df_subj.empty:
                def assign_weight(grade):
                    if grade in ['S', 'A+']: return 5
                    elif grade in ['A', 'B+', 'B']: return 3
                    else: return 2
                weights = df_subj['p_grade'].apply(assign_weight)
                st.session_state[f'random_p_{subject}'] = df_subj.sample(1, weights=weights).iloc[0].to_dict()
                st.session_state[f'read_done_{subject}'] = False
            else:
                st.session_state[f'random_p_{subject}'] = None
                st.warning(f"등록된 {subject} 판례가 없습니다.")
        else:
            st.warning("등록된 판례가 없습니다.")

    p = st.session_state.get(f'random_p_{subject}')
    if p:
        st.write("")
        grade_mark = f"⭐ {p.get('p_grade', 'C')}" if p.get('p_grade') else ""
        rc = int(p.get('read_count', 0))
        read_badge = f" [현재 {rc}회독]"
        
        st.subheader(f"{grade_mark} {p.get('p_number', '')} {p.get('p_title', '')} {read_badge}")
        st.markdown(f"**카테고리:** {p['main_cat']} > {p['mid_cat']} > {p['sub_cat']}")
        if p.get('p_tags'): 
            tags_html = "".join([f"<span class='tag-badge'>#{t.strip()}</span>" for t in str(p['p_tags']).split(',') if t.strip()])
            st.markdown(f"**🏷️ 태그:** {tags_html}", unsafe_allow_html=True)
            
        st.write("")
        with st.expander("💡 판결 결과 및 내용 확인하기 (클릭)"):
            if subject == '헌법' and p.get('p_result'): st.markdown(f"### ⚖️ 판결 결과: [{p.get('p_result')}]")
            st.info(p.get('p_desc', '설명이 없습니다.'))
            st.write(p.get('p_content', '내용이 없습니다.'))
                
        st.write("")
        if st.session_state.get(f'read_done_{subject}'):
            st.success(f"🎉 **{int(p.get('read_count', 0)) + 1}번째 회독 완료!** 통계에 기록되었습니다.")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("✔️ 회독 완료", use_container_width=True, disabled=st.session_state.get(f'read_done_{subject}', False)):
                df_update = load_precedents_df()
                idx = df_update[df_update['id'].astype(str) == str(p['id'])].index
                if not idx.empty:
                    current_rc = int(df_update.loc[idx[0], "read_count"])
                    df_update.loc[idx[0], "read_count"] = current_rc + 1
                    save_precedents_df(df_update)
                    log_activity('read') # 통계 기록
                    
                    st.session_state[f'random_p_{subject}']['read_count'] = current_rc + 1
                    st.session_state[f'read_done_{subject}'] = True
                    st.rerun() 
        with col_btn2:
            if st.button("⏭️ 다음 판례", use_container_width=True, type="primary"):
                df_subj = load_precedents_df()[load_precedents_df()['main_cat'] == subject]
                if not df_subj.empty:
                    def assign_weight(grade):
                        if grade in ['S', 'A+']: return 5
                        elif grade in ['A', 'B+', 'B']: return 3
                        else: return 2
                    weights = df_subj['p_grade'].apply(assign_weight)
                    st.session_state[f'random_p_{subject}'] = df_subj.sample(1, weights=weights).iloc[0].to_dict()
                    st.session_state[f'read_done_{subject}'] = False
                st.rerun()


# --- 4. 지문 복습 ---
elif menu in ["📝 헌법 지문 복습", "📝 행정법 지문 복습"]:
    subject = "헌법" if menu == "📝 헌법 지문 복습" else "행정법"
    st.title(menu)
    st.write("---")
    
    df_passages = load_passages_df()
    if not df_passages.empty:
        df_sub = df_passages[df_passages['subject'] == subject].sort_values(by='id', ascending=False)
        if df_sub.empty:
            st.info(f"등록된 {subject} 지문이 없습니다.")
        else:
            for p in df_sub.to_dict('records'):
                ox_icon = "⭕" if p['is_true'] == 'O' else "❌"
                with st.expander(f"{ox_icon} {p['passage_text'][:30]}..."):
                    st.markdown(f"**📝 지문:** {p['passage_text']}")
                    st.markdown(f"**📚 출처:** {p['source']}")
                    st.markdown(f"**💡 정답 및 해설:** [{p['is_true']}] {p['explanation']}")
                    
                    with st.expander("✏️ 지문 삭제"):
                        if st.button("🗑️ 지문 삭제", key=f"del_pas_{p['id']}", type="primary"):
                            df_delete = load_passages_df()
                            df_delete = df_delete[df_delete['id'].astype(str) != str(p['id'])]
                            save_passages_df(df_delete)
                            st.success("삭제되었습니다.")
                            st.rerun()
    else:
        st.info("지문 데이터(passages) 시트가 비어있거나 생성되지 않았습니다.")


# --- 5. ✅ O/X 문제풀기 ---
elif menu == "✅ O/X 문제풀기":
    st.title("✅ 실전 O/X 문제풀기")
    st.write("---")
    
    ox_subject = st.radio("과목 선택", ["전체", "헌법", "행정법"], horizontal=True)
    
    if 'ox_current' not in st.session_state: st.session_state.ox_current = None
    if 'ox_answered' not in st.session_state: st.session_state.ox_answered = False
    
    if st.button("🔄 새로운 지문 뽑기", use_container_width=True, type="primary"):
        df_passages = load_passages_df()
        if not df_passages.empty:
            if ox_subject != "전체": df_passages = df_passages[df_passages['subject'] == ox_subject]
            if not df_passages.empty:
                st.session_state.ox_current = df_passages.sample(1).iloc[0].to_dict()
                st.session_state.ox_answered = False
            else:
                st.session_state.ox_current = None
                st.warning("해당 조건의 지문이 없습니다.")
        else:
            st.error("등록된 지문이 없습니다. 지문을 먼저 등록해주세요.")

    p = st.session_state.ox_current
    if p:
        st.write("")
        st.markdown(f"### 📝 Q. 다음 지문의 O/X 여부를 판별하시오.")
        st.info(f"**{p['passage_text']}**")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("⭕ 맞다 (O)", use_container_width=True, disabled=st.session_state.ox_answered):
                st.session_state.ox_user_answer = 'O'
                st.session_state.ox_answered = True
                log_activity('ox') # 통계 기록
                st.rerun()
        with c2:
            if st.button("❌ 틀리다 (X)", use_container_width=True, disabled=st.session_state.ox_answered):
                st.session_state.ox_user_answer = 'X'
                st.session_state.ox_answered = True
                log_activity('ox') # 통계 기록
                st.rerun()
                
        if st.session_state.ox_answered:
            st.write("---")
            correct = p['is_true'] == st.session_state.ox_user_answer
            if correct: st.success("🎉 정답입니다! (통계에 기록되었습니다)")
            else: st.error(f"😢 틀렸습니다. (정답: {p['is_true']})")
            
            st.markdown(f"**💡 해설:** {p['explanation']}")


# --- 6. 카테고리 관리 ---
elif menu == "📁 카테고리 관리":
    st.title("📁 Categories")
    st.write("목차와 세부 소분류를 추가하거나 삭제할 수 있습니다.")
    
    st.subheader("➕ 카테고리 추가")
    col1, col2 = st.columns(2)
    with col1:
        main_cat_add = st.selectbox("대분류 선택", ["헌법", "행정법"], key="add_main")
        new_mid = st.text_input("새로운 목차 이름")
        if st.button("목차 추가", use_container_width=True):
            if new_mid and add_category(main_cat_add, new_mid):
                st.success("추가됨!")
                st.rerun()
    with col2:
        mid_options_add = list(categories.get(main_cat_add, {}).keys())
        if mid_options_add:
            selected_mid_add = st.selectbox("목차 선택", mid_options_add, key="add_mid")
            new_sub = st.text_input("새로운 소분류 이름")
            if st.button("소분류 추가", use_container_width=True):
                if new_sub and add_category(main_cat_add, selected_mid_add, new_sub):
                    st.success("추가됨!")
                    st.rerun()

    st.write("---")
    st.subheader("🗑️ 카테고리 삭제")
    main_cat_del = st.selectbox("대분류 선택", ["헌법", "행정법"], key="del_main")
    col3, col4 = st.columns(2)
    mid_options_del = list(categories.get(main_cat_del, {}).keys())
    
    with col3:
        if mid_options_del:
            selected_mid_del = st.selectbox("삭제할 목차 선택", mid_options_del, key="del_mid_target")
            if st.button("목차 삭제 (하위 포함)", use_container_width=True, type="primary"):
                delete_category(main_cat_del, selected_mid_del)
                st.success(f"'{selected_mid_del}' 목차가 삭제되었습니다.")
                st.rerun()
    with col4:
        if mid_options_del:
            selected_mid_for_sub = st.selectbox("목차 먼저 선택", mid_options_del, key="del_mid_for_sub")
            sub_options_del = categories.get(main_cat_del, {}).get(selected_mid_for_sub, [])
            sub_options_del = [s for s in sub_options_del if s] 
            if sub_options_del:
                selected_sub_del = st.selectbox("삭제할 소분류 선택", sub_options_del, key="del_sub_target")
                if st.button("소분류 삭제", use_container_width=True, type="primary"):
                    delete_category(main_cat_del, selected_mid_for_sub, selected_sub_del)
                    st.success(f"'{selected_sub_del}' 소분류가 삭제되었습니다.")
                    st.rerun()


# --- 7. 판례 등록 ---
elif menu == "✍️ 판례 등록":
    st.title("✍️ Add Precedent")
    
    col1, col2, col3 = st.columns(3)
    with col1: reg_main = st.selectbox("대분류", ["헌법", "행정법"])
    mid_options = list(categories.get(reg_main, {}).keys())
    with col2: reg_mid = st.selectbox("목차", mid_options if mid_options else ["목차 없음"])
    sub_options = categories.get(reg_main, {}).get(reg_mid, []) if reg_mid != "목차 없음" else []
    with col3: reg_sub = st.selectbox("소분류", sub_options if sub_options else ["소분류 없음"])
        
    if reg_mid == "목차 없음" or reg_sub == "소분류 없음":
        st.warning("카테고리를 먼저 생성해주세요.")
    else:
        with st.form("precedent_form", clear_on_submit=True):
            c_grade, c_result = st.columns(2)
            with c_grade: p_grade = st.selectbox("⭐ 중요도", ["S", "A+", "A", "B+", "B", "C+", "C"], index=2)
            with c_result: p_result = st.selectbox("⚖️ 판결 결과", ["합헌", "위헌", "헌법불합치", "기각", "인용", "각하", "한정위헌", "기타"]) if reg_main == "헌법" else ""
            
            p_number = st.text_input("📌 판례 번호")
            p_title = st.text_input("📝 판례 제목")
            
            col_loc, col_rel = st.columns(2)
            with col_loc: p_location = st.text_input("📖 교재 수록 위치")
            with col_rel: p_related = st.text_input("🔗 연관 판례 및 조문")
            
            p_content = st.text_area("📄 판례 요지 및 내용 (원문)", height=150)
            p_desc = st.text_area("💡 판례 설명 (나만의 쉬운 해설)", height=100)
            p_tags = st.text_input("🏷️ 태그 (쉼표로 구분)")
            p_exams = st.text_area("🏆 시험 출제 내역 (엔터키로 구분)", height=100)
            
            if st.form_submit_button("저장", use_container_width=True):
                if p_number and p_title:
                    reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    cleaned_tags = ", ".join([tag.strip() for tag in p_tags.split(",") if tag.strip()])
                    df = load_precedents_df()
                    new_id = int(df['id'].max()) + 1 if not df.empty else 1
                    
                    new_row = pd.DataFrame([{"id": new_id, "main_cat": reg_main, "mid_cat": reg_mid, "sub_cat": reg_sub, "p_number": p_number, "p_title": p_title, "p_content": p_content, "p_tags": cleaned_tags, "p_location": p_location, "p_related": p_related, "p_exams": sort_exams_desc(p_exams), "reg_date": reg_date, "p_desc": p_desc, "p_grade": p_grade, "p_result": p_result, "read_count": 0}])
                    df = pd.concat([df, new_row], ignore_index=True)
                    save_precedents_df(df)
                    log_activity('reg') # 통계 기록
                    st.success("✅ 저장 완료!")
                else:
                    st.error("판례 번호와 제목을 입력하세요.")


# --- 8. 지문 등록 ---
elif menu == "✍️ 지문 등록":
    st.title("✍️ Add Passage")
    
    with st.form("passage_form", clear_on_submit=True):
        pas_main = st.selectbox("과목", ["헌법", "행정법"])
        pas_text = st.text_area("📝 지문 내용 (실제 출제 문장)")
        pas_source = st.text_input("📚 지문 출처 (예: 23년 국가직 7급)")
        pas_is_true = st.radio("✅ 참/거짓 정답 (O/X)", ["O", "X"], horizontal=True)
        pas_desc = st.text_area("💡 지문 해설 (오답인 이유 등)")
        
        if st.form_submit_button("지문 저장", use_container_width=True):
            if pas_text:
                df_pas = load_passages_df()
                new_id = int(df_pas['id'].max()) + 1 if not df_pas.empty else 1
                reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                new_row = pd.DataFrame([{"id": new_id, "subject": pas_main, "passage_text": pas_text, "source": pas_source, "is_true": pas_is_true, "explanation": pas_desc, "reg_date": reg_date}])
                df_pas = pd.concat([df_pas, new_row], ignore_index=True)
                save_passages_df(df_pas)
                log_activity('reg') # 통계 기록
                st.success("✅ 기출 지문이 저장되었습니다!")
            else:
                st.error("지문 내용을 입력해주세요.")
