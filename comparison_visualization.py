import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ==========================================
# 1. 사이트별 주요 키워드 비율 (Document Frequency)
# ==========================================
# 1. 데이터 로드
df_style = pd.read_csv("database/comparison_style_summary.csv")
df_kw = pd.read_csv("database/comparison_top_keywords.csv")

# 2. 불용어(Stopwords) 정의 및 필터링
# 의미 없는 단순 긍정어 및 형용사를 리스트에 담아 제외
stop_words = ['좋다', '많다', '아름답다', '최고', '예쁘다', '멋지다']
df_kw_filtered = df_kw[~df_kw['word'].isin(stop_words)].copy()

# 3. 비중(DF %) 계산 (분모는 필터링 전 원본 전체 리뷰 수 유지)
total_map = dict(zip(df_style['site'], df_style['content_count']))
df_kw_filtered['total_reviews'] = df_kw_filtered['site'].map(total_map)
df_kw_filtered['df_pct'] = (df_kw_filtered['count'] / df_kw_filtered['total_reviews']) * 100
df_kw_top5 = df_kw_filtered.groupby('site').head(5).reset_index(drop=True)

# 5. 커스텀 라벨 생성 및 시각화 (비율% + 원본 빈도)
df_kw_top5['custom_label'] = df_kw_top5['df_pct'].round(1).astype(str) + '% (' + df_kw_top5['count'].astype(str) + '건)'

fig_kw = px.bar(
    df_kw_top5, x="df_pct", y="word", color="site", facet_row="site",
    orientation='h', title="1. 플랫폼별 Top 5 실질 키워드 언급 비율 (불용어 제외)",
    text='custom_label',
    category_orders={"site": ["kakao", "tripadvisor", "tripdotcom"]},
    labels={'df_pct': '언급 비중(%)', 'word': '키워드'}
)

fig_kw.update_yaxes(matches=None, showticklabels=True)
fig_kw.show()


# ==========================================
# 2. 연도별 리뷰 수 트렌드
# ==========================================
df_year = pd.read_csv("database/comparison_year_summary.csv")
sites = ['kakao', 'tripadvisor', 'tripdotcom']
colors = {'kakao': '#FEE500', 'tripadvisor': '#00AF87', 'tripdotcom': '#3370FF'}

fig_year = go.Figure()

for site in sites:
    # 연도별 정규화(%)
    pct_col = (df_year[site] / df_year[site].sum()) * 100
    
    fig_year.add_trace(go.Scatter(
        x=df_year['year'], 
        y=pct_col, 
        mode='lines+markers', 
        name=site.capitalize(),
        line=dict(width=3, color=colors[site]),
        marker=dict(size=6),
        customdata=df_year[site], # 툴팁용 원본 Count 데이터
        hovertemplate='%{y:.1f}% (원본: %{customdata}건)'
    ))

fig_year.update_layout(
    title='2. 플랫폼별 연도별 리뷰 작성 비율 트렌드 (%)',
    xaxis_title='연도 (Year)',
    yaxis_title='비중 (%)',
    hovermode='x unified',
    xaxis=dict(tickmode='linear', dtick=1)
)
fig_year.show()


# ==========================================
# 3. 월별(계절성) 리뷰 수 추이 및 비율
# ==========================================
df_month = pd.read_csv("database/comparison_month_summary.csv")

fig_month = go.Figure()

for site in sites:
    # 월별 정규화(%)
    pct_col = (df_month[site] / df_month[site].sum()) * 100
    
    fig_month.add_trace(go.Scatter(
        x=df_month['month'], 
        y=pct_col, 
        mode='lines+markers', 
        name=site.capitalize(),
        line=dict(width=3, color=colors[site]),
        marker=dict(size=8),
        customdata=df_month[site],
        hovertemplate='%{y:.1f}% (원본: %{customdata}건)'
    ))

fig_month.update_layout(
    title='3. 플랫폼별 월별 계절성 리뷰 비율 추이 (%)',
    xaxis_title='월 (Month)',
    yaxis_title='비중 (%)',
    hovermode='x unified',
    xaxis=dict(tickmode='linear', dtick=1)
)
fig_month.show()

# ==========================================
# 4. 요일별 리뷰 작성 비율
# ==========================================

# 1. 데이터 로드
df_kakao = pd.read_csv("database/preprocessed_reviews_kakao.csv")
df_ta = pd.read_csv("database/preprocessed_reviews_tripadvisor.csv")
df_tc = pd.read_csv("database/preprocessed_reviews_tripdotcom.csv")

# 2. 요일 매핑 로직 (0: 월 ~ 6: 일)
day_map = {0: '월요일', 1: '화요일', 2: '수요일', 3: '목요일', 4: '금요일', 5: '토요일', 6: '일요일'}
days_order = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

def get_dow_counts(df):
    # weekday 컬럼 값을 요일 문자열로 치환
    df['day_name'] = df['weekday'].map(day_map)
    df['day_name'] = pd.Categorical(df['day_name'], categories=days_order, ordered=True)
    counts = df['day_name'].value_counts().sort_index()
    return counts

kakao_counts = get_dow_counts(df_kakao)
ta_counts = get_dow_counts(df_ta)
tc_counts = get_dow_counts(df_tc)

# 3. 데이터프레임 병합 및 비율(%) 계산
df_dow = pd.DataFrame({
    'Day': days_order,
    'Kakao_Count': kakao_counts.values,
    'Tripadvisor_Count': ta_counts.values,
    'Tripdotcom_Count': tc_counts.values
})

# 절대적인 리뷰 빈도를 각 플랫폼 총합 대비 비중(%)으로 정규화
df_dow['Kakao'] = (df_dow['Kakao_Count'] / df_dow['Kakao_Count'].sum()) * 100
df_dow['Tripadvisor'] = (df_dow['Tripadvisor_Count'] / df_dow['Tripadvisor_Count'].sum()) * 100
df_dow['Tripdotcom'] = (df_dow['Tripdotcom_Count'] / df_dow['Tripdotcom_Count'].sum()) * 100

# 4. Plotly 시각화 (라인 그래프)
fig_dow = go.Figure()

colors = {'Kakao': '#FEE500', 'Tripadvisor': '#00AF87', 'Tripdotcom': '#3370FF'}
sites = ['Kakao', 'Tripadvisor', 'Tripdotcom']

for site in sites:
    fig_dow.add_trace(go.Scatter(
        x=df_dow['Day'], 
        y=df_dow[site], 
        mode='lines+markers', 
        name=site,
        line=dict(width=3, color=colors[site]),
        marker=dict(size=8),
        # 마우스 오버(Hover) 시 비율(%)과 원본 카운트를 함께 표출
        customdata=df_dow[f'{site}_Count'],
        hovertemplate='%{y:.1f}% (원본: %{customdata}건)'
    ))

fig_dow.update_layout(
    title='플랫폼별 요일별 리뷰 작성 비율 및 원본 빈도 추이',
    xaxis_title='요일',
    yaxis_title='비중 (%)',
    hovermode='x unified',
    xaxis=dict(tickangle=0)
)

fig_dow.show()

# ==========================================
# 4. 감정 분포 비교
# ==========================================

df_sent = pd.read_csv("database/comparison_sentiment_dist.csv")
df_sent['Total'] = df_sent['Negative'] + df_sent['Neutral'] + df_sent['Positive']

for col in ['Negative', 'Neutral', 'Positive']:
    df_sent[f'{col}_pct'] = (df_sent[col] / df_sent['Total']) * 100
    # 💡 핵심 수정: 감정별 커스텀 라벨 생성
    df_sent[f'{col}_label'] = df_sent[f'{col}_pct'].round(1).astype(str) + '% (' + df_sent[col].astype(str) + '건)'

fig_sent = go.Figure(data=[
    go.Bar(name='Negative', x=df_sent['site'], y=df_sent['Negative_pct'], 
           marker_color='crimson', text=df_sent['Negative_label'], textposition='auto'),
    go.Bar(name='Neutral', x=df_sent['site'], y=df_sent['Neutral_pct'], 
           marker_color='lightslategrey', text=df_sent['Neutral_label'], textposition='auto'),
    go.Bar(name='Positive', x=df_sent['site'], y=df_sent['Positive_pct'], 
           marker_color='royalblue', text=df_sent['Positive_label'], textposition='auto')
])

fig_sent.update_layout(
    barmode='stack', 
    title='4. 플랫폼별 감정 분포 비율 및 원본 수치', 
    yaxis_title='비율 (%)',
    xaxis_title='플랫폼'
)
fig_sent.show()



