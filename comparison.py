import pandas as pd
import numpy as np

from collections import Counter
import os

###csv 병합
base_dir = "database"
sites = ["kakao", "tripadvisor", "tripdotcom"]
df_list = []

for site in sites:
    file_path = os.path.join(base_dir, f"preprocessed_reviews_{site}.csv")
    if os.path.exists(file_path):
        tmp_df = pd.read_csv(file_path)
        tmp_df['site'] = site  # 사이트명 
        df_list.append(tmp_df)

df = pd.concat(df_list, ignore_index=True)
print(f"총 데이터 건수: {len(df)}건\n")


##########################
# 1. 리뷰 스타일 비교
#########################
print("=== 1. 리뷰 스타일 비교 ===")
style_summary = df.groupby('site').agg(
    content_count=('content', 'count'),
    rating_mean=('rating', 'mean'),
    text_len_mean=('text_len', 'mean'),
    text_len_median=('text_len', 'median'),
    token_count_mean=('token_count', 'mean'),
    emoji_count_mean=('emoji_count', 'mean')
).reset_index()

print(style_summary.to_string(index=False))
print("\n")


##########################
# 2. 사이트별 키워드 빈도: top 15
#########################
print("=== 2. 사이트별 키워드 빈도: Top 15 ===")
top_keywords = {}

stop_words = {'경복궁', 'quot'} 
#불용어 리스트: 임의로 설정함, 필요시 추가 


for site in sites:
    site_tokens = df[df['site'] == site]['tokens'].dropna()
    # 공백 기준으로 토큰 분리
    all_words = [word for tokens_str in site_tokens for word in str(tokens_str).split()]
    
    # 1글자 단어, stop_words 제외 단어 추출 
    filtered_words = [w for w in all_words if len(w) > 1 and w not in stop_words]
    counts = Counter(filtered_words).most_common(15)
    
    top_keywords[site] = counts
    print(f"\n[{site.upper()}] 주요 키워드:")
    for word, count in counts:
        print(f"  - {word}: {count}회")

# 키워드 데이터프레임으로 변환 (시각화용)
keyword_dfs = []
for site, kw_list in top_keywords.items():
    tdf = pd.DataFrame(kw_list, columns=['word', 'count'])
    tdf['site'] = site
    keyword_dfs.append(tdf)
df_keywords = pd.concat(keyword_dfs, ignore_index=True)


##########################
# 3. 시계열 추이(연도, 월별)
#########################
print("\n=== 3. 연도별 리뷰 작성 수 추이 ===")
year_summary = df.groupby(['year', 'site'])['content'].count().unstack(fill_value=0)
print(year_summary)

print("\n=== 4. 월별(계절성) 리뷰 작성 수 추이 ===")
month_summary = df.groupby(['month', 'site'])['content'].count().unstack(fill_value=0)
print(month_summary)


##########################
# 4. 감정 분석, 감정별 주요 키워드
#########################
print("\n=== 4. 감정 분석, 감정별 주요 키워드 ===")

# 별점 별 그룹: 4~5(positive), 3(neutral), 1~2(negative)
def classify_sentiment(rating):
    if rating >= 4:
        return 'Positive'
    elif rating == 3:
        return 'Neutral'
    else:
        return 'Negative'

df['sentiment'] = df['rating'].apply(classify_sentiment)

sentiment_distribution = df.groupby(['site', 'sentiment'])['content'].count().unstack(fill_value=0)
print("[사이트별 감정 분포]")
print(sentiment_distribution)

# 감정별 주요 키워드
sentiment_keywords = []
for site in sites:
    for sent in ['Positive', 'Negative']:
        target_tokens = df[(df['site']==site) & (df['sentiment']==sent)]['tokens'].dropna()

        # negative 아예 없는 경우 예외 처리
        if len(target_tokens)==0:
            continue

        all_words = [word for tokens_str in target_tokens for word in str(tokens_str).split()]
        filtered_words = [w for w in all_words if len(w) > 1 and w not in stop_words]


        # 상위 10개 키워드 추출
        counts = Counter(filtered_words).most_common(10)
        
        for word, count in counts:
            sentiment_keywords.append({
                'site': site,
                'sentiment': sent,
                'word': word,
                'count': count
            })

df_sentiment_keywords = pd.DataFrame(sentiment_keywords)


##############
# 결과 저장
############
df_keywords.to_csv("database/comparison_top_keywords.csv", index=False, encoding='utf-8-sig')
year_summary.to_csv("database/comparison_year_summary.csv", encoding='utf-8-sig')
month_summary.to_csv("database/comparison_month_summary.csv", encoding='utf-8-sig')
style_summary.to_csv("database/comparison_style_summary.csv", index=False, encoding='utf-8-sig')
sentiment_distribution.to_csv("database/comparison_sentiment_dist.csv", encoding='utf-8-sig')
df_sentiment_keywords.to_csv("database/comparison_sentiment_keywords.csv", index=False, encoding='utf-8-sig')






