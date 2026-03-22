import os
import re
import json
import time
import hashlib
import urllib.parse
import urllib.request
import random
from datetime import datetime, timezone, timedelta

try:
    import feedparser
    import requests
    import google.generativeai as genai
except ImportError:
    print("【エラー】必要なライブラリが不足しています。")
    print("ターミナルで以下のコマンドを実行してインストールしてください：")
    print("pip install feedparser requests google-generativeai")
    exit(1)

# ==========================================
# ⚙️ 設定
# ==========================================
# Google GeminiのAPIキーをここに設定してください（無料枠で利用可能です）
# 取得方法: https://aistudio.google.com/app/apikey
# API_KEYは環境変数から読み込むため、ここでは設定しません。

# 取得するニュースのRSSフィードをタブごとに指定
CATEGORIES = [
    {"id": "tab-ai", "name": "AI", "rss": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"},
    {"id": "tab-robotics", "name": "ロボット", "rss": "https://news.yahoo.co.jp/rss/topics/it.xml"},
    {"id": "tab-semiconductor", "name": "半導体", "rss": "https://news.google.com/rss/search?q=%E5%8D%8A%E5%B0%8E%E4%BD%93&hl=ja&gl=JP&ceid=JP:ja"},
    {"id": "tab-security", "name": "セキュリティ", "rss": "https://rss.itmedia.co.jp/rss/2.0/news_security.xml"}
]

# 更新するHTMLファイルのパス
HTML_FILE_PATH = "index.html"

# ==========================================
# 📈 為替・仮想通貨リアルタイムデータの取得
# ==========================================
def generate_ticker_html():
    JST = timezone(timedelta(hours=+9), 'JST')
    now = datetime.now(JST)
    current_time_str = now.strftime("%Y/%m/%d %H:%M 更新")
    
    html = f'<div class="ticker__item" style="color: var(--text-secondary); margin-right: 20px;">🕒 {current_time_str}</div>\n'
    
    symbols = {
        '日経平均': '^N225',
        '日経平均先物': 'NIY=F',
        'NYダウ': '^DJI',
        'NASDAQ': '^IXIC',
        'S&P500': '^GSPC',
        'TOPIX': '1306.T', # TOPIX連動ETFを代替利用
        '米ドル/円': 'JPY=X',
        'Bitcoin': 'BTC-JPY'
    }

    def get_yahoo_price(sym):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1d"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                meta = data['chart']['result'][0]['meta']
                price = meta.get('regularMarketPrice')
                prev = meta.get('chartPreviousClose')
                if price and prev:
                    change = price - prev
                    change_pct = (change / prev) * 100
                    return price, change_pct
        except Exception:
            pass
        return None, None

    for name, sym in symbols.items():
        p, c = get_yahoo_price(sym)
        if p is not None:
            cls = "up" if c >= 0 else "down"
            sign = "+" if c > 0 else ""
            arrow = "▲" if c >= 0 else "▼"
            
            # Format display
            if sym == 'JPY=X':
                display_price = f"{p:.2f}円"
            elif sym == 'BTC-JPY':
                display_price = f"¥{p:,.0f}"
            elif sym == '1306.T':
                display_price = f"{p:,.1f}"
            elif sym == 'NIY=F':
                display_price = f"¥{p:,.0f}"
            else:
                display_price = f"{p:,.2f}"
                
            html += f'<div class="ticker__item {cls}">{name} {display_price} ({sign}{c:.2f}%) {arrow}</div>\n'
    
    # 取得失敗時に備えたフォールバック
    if html.count('<div') <= 1:
        html += '<div class="ticker__item up">日経平均 39,815.12 (+1.5%) ▲</div>\n'
        html += '<div class="ticker__item down">TOPIX 2,750.34 (-0.3%) ▼</div>\n'
    
    return html

# ==========================================
# 🔗 URLのクリーンアップ（リダイレクト警告対策）
# ==========================================
def clean_url(raw_url):
    """
    Googleアラートなどの中間リダイレクトURLから
    実際の記事のURL部分だけを抽出する
    例: https://www.google.com/url?rct=j&sa=t&url=https://news.yahoo.co.jp/...&ct=ga...
    """
    try:
        parsed = urllib.parse.urlparse(raw_url)
        query_params = urllib.parse.parse_qs(parsed.query)
        # 'url' や 'q' パラメータに実体が入っていることが多い
        if 'url' in query_params:
            return query_params['url'][0]
        if 'q' in query_params:
            return query_params['q'][0]
    except Exception:
        pass
    
    return raw_url

# ==========================================
# 🔑 Gemini API設定（環境変数は下部のanalyze_news_with_gemini内で読み込み）
# ==========================================
# 🤖 Gemini APIでニュースを分析・成形
# ==========================================
def analyze_news_with_gemini(entry, time_ago):
    API_KEY = os.environ.get("GEMINI_API_KEY", "")
    if not API_KEY:
        print("【エラー】環境変数 GEMINI_API_KEY が設定されていません。")
        return None
    genai.configure(api_key=API_KEY)
    # 最新の高速モデルを使用
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
あなたは先進的なAI・テクノロジーニュースメディアの凄腕エディターです。
以下のニュース記事情報を分析し、指定されたフォーマットのJSONのみを返してください。不要なテキスト（マークダウンの```jsonや説明文）を含めないでください。

【ニュース情報】
タイトル: {entry.title}
概要/URL: {entry.link}
発表時間: {time_ago}

【出力ルール・出力JSONフォーマット】
・回答は必ず100%正しいJSONフォーマットのみ（{{で始まり}}で終わる）を出力してください。
・キーや文字列はすべてダブルクォーテーション（"）で囲んでください。
・JSONの文法エラー（特に配列の最後の要素の後の余計なカンマ）は絶対に含めないでください。
・追加コメントやマークダウン（```json 等）は一切不要です。
{{
  "title": "記事のタイトルをベースに、読者を惹きつける洗練された日本語タイトルに調整",
  "tags": "AI / LLM", "Robotics", "SaaS", "Hardware"などのような1〜2単語の英語またはカタカナのジャンルタグ（必ず文字列で1つだけ指定）,
  "sentiment": "positive", "negative", "neutral" のいずれか（明るい話題はpositive、懸念はnegative、一般的な製品発表などはneutral）,
  "sentiment_text": "「明るい話題」「懸念される話題」「注目の話題」など、sentimentに合わせた日本語テキスト",
  "rating": 3〜5の整数（ビジネスにおける重要度）,
  "time_ago": "{time_ago}",
  "url": "{entry.link}",
  "summary_bullets": [
    "ニュースのもっとも重要なポイント（簡潔な1行）",
    "ビジネスや社会への影響（簡潔な1行）",
    "今後のトレンドや予測（簡潔な1行）"
  ],
  "insight": "ビジネスマンがこのニュースから得るべきインサイト（洞察）（1文程度で説得力のある内容）",
  "action_plan": "このニュースを読んで、読者が今日からできる具体的なアクション案（「〜を見直してみましょう」「〜を書き出してみましょう」等）",
  "image_keyword": "記事の内容を的確に表す英語の画像検索キーワード2〜3語（例: futuristic robot, cyber security network, smart tech office）",
  "technical_terms": [
    {{"term": "専門用語1(あれば。タイトルや要約に含まれるもの)", "explanation": "初心者向けの簡単な解説"}},
    {{"term": "専門用語2(あれば)", "explanation": "初心者向けの簡単な解説"}}
  ]
}}
"""
    try:
        response = model.generate_content(prompt)
        
        # セーフティブロックなどのチェック
        if not response.candidates or not response.candidates[0].content.parts:
            print("【エラー】AIの出力がブロックされました（セーフティ機能等の影響）")
            if response.candidates:
                print("Finish Reason:", response.candidates[0].finish_reason)
            return None

        text = response.text.strip()
        
        # JSON部分だけを確実に抽出するフォールバック
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            json_str = text[start_idx:end_idx+1]
        else:
            json_str = text
            
        return json.loads(json_str, strict=False)
        
    except json.JSONDecodeError as je:
        print(f"【JSON解析エラー】AIの回答が正しいJSON形式ではありませんでした: {je}")
        print(f"--- 実際のAIの出力 ---\n{text}\n----------------------")
        return None
    except Exception as e:
        error_msg = str(e)
        if "Quota exceeded" in error_msg or "429" in error_msg:
            print(f"\n【API制限エラー】Gemini APIの無料枠の制限（1日の回数や連続リクエスト数）に達しました。")
            print("しばらく時間をおいてから再度お試しください。")
            return "RATE_LIMIT"
        else:
            print(f"\n【Gemini API エラー】通信やAPIキーに問題がある可能性があります:")
            print(error_msg)
        return None

# ==========================================
# 🖼️ サムネイル画像の抽出
# ==========================================
def extract_thumbnail_url(entry, article_data=None):
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        return entry.media_thumbnail[0]["url"]
    if hasattr(entry, 'links'):
        for link in entry.links:
            if link.get("type", "").startswith("image"):
                return link["href"]
    if hasattr(entry, 'description') and "<img" in entry.description:
        m = re.search(r"<img[^>]+src=[\"'](.*?)[\"']", entry.description)
        if m:
            return m.group(1)
            
    # サムネイルが見つからない場合はAIが生成したキーワードでBingの画像検索結果（サムネイル）を取得する
    if article_data and 'image_keyword' in article_data:
        keyword = article_data['image_keyword']
        encoded = urllib.parse.quote(keyword)
        return f"https://tse2.mm.bing.net/th?q={encoded}&w=600&h=300&c=7&rs=1&p=0"

    title_hash = hashlib.md5(entry.title.encode('utf-8')).hexdigest()
    return f"https://picsum.photos/seed/{title_hash}/600/300"

# ==========================================
# 🏗️ HTMLの生成
# ==========================================
def generate_article_html(article_data, element_id, thumb_url):
    # Sentimentによるバッジの切り替え
    sentiment_class = article_data.get('sentiment', 'neutral')
    if sentiment_class == 'neutral':
        sentiment_class = 'positive' # デフォルトはpositive扱いで色をつける（青色などにする場合はHTML側のCSS調整が必要ですが、ここでは既存の色を利用します）
        
    badge_icon = '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />'
    if sentiment_class == 'negative':
        badge_icon = '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />'

    # スターの生成
    rating = article_data.get('rating', 3)
    stars_html = '<span class="star-filled">★</span>' * rating + '<span class="star-empty">★</span>' * (5 - rating)

    # 用語ツールチップの実装（タイトル内の用語を置換）
    title_html = article_data['title']
    for term_data in article_data.get('technical_terms', []):
        term = term_data['term']
        exp = term_data['explanation']
        tooltip_html = f'<span class="term-tooltip" data-tooltip="{exp}">{term}</span>'
        title_html = title_html.replace(term, tooltip_html)
        
    # サマリー箇条書きの生成
    summary_html = ""
    for idx, bullet in enumerate(article_data.get('summary_bullets', [])):
        # サマリー内にも用語があれば置換するかどうか（ここではシンプルにそのまま出力）
        bullet_html = bullet
        for term_data in article_data.get('technical_terms', []):
            term = term_data['term']
            exp = term_data['explanation']
            if term in bullet_html:
                tooltip_html = f'<span class="term-tooltip" data-tooltip="{exp}">{term}</span>'
                bullet_html = bullet_html.replace(term, tooltip_html)
        summary_html += f"<li>{bullet_html}</li>\n                            "

    html = f"""
                <!-- Article {element_id} -->
                <article class="news-card" id="article-{element_id}">
                    <img src="{thumb_url}" alt="Thumbnail" class="card-thumbnail" loading="lazy">
                    <div class="card-header">
                        <div class="tag-group">
                            <span class="sentiment-badge {sentiment_class}">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                    {badge_icon}
                                </svg>
                                {article_data.get('sentiment_text', '注目の話題')}
                            </span>
                            <span class="tag">{article_data.get('tags', 'News')}</span>
                            <div class="rating" aria-label="重要度: {rating}" title="重要度: {rating}">
                                {stars_html}
                            </div>
                        </div>
                        <span class="time-ago">{article_data['time_ago']}</span>
                    </div>
                    <h2 class="news-title"><a href="{article_data['url']}" target="_blank"
                            rel="noopener noreferrer" class="title-link">{title_html}</a></h2>

                    <div class="summary-box">
                        <div class="summary-title">
                            <svg viewBox="0 0 24 24">
                                <path
                                    d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"
                                    fill="currentColor" />
                            </svg>
                            10秒でわかる要約
                        </div>
                        <ul class="summary-list">
                            {summary_html.strip()}
                        </ul>
                    </div>

                    <div class="business-insight">
                        <div class="insight-title">Business Insight</div>
                        <div class="insight-text">{article_data.get('insight', '')}</div>
                    </div>

                    <div class="action-plan">
                        <div class="action-title">
                            <svg viewBox="0 0 24 24">
                                <path
                                    d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
                            </svg>
                            今日からできるアクション
                        </div>
                        <div class="action-text">{article_data.get('action_plan', '')}</div>
                    </div>

                    <div class="news-footer">
                        <a href="{article_data['url']}" target="_blank"
                            rel="noopener noreferrer" class="read-more-btn">
                            さらに詳しく
                            <svg viewBox="0 0 24 24">
                                <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" stroke-width="2"
                                    stroke-linecap="round" stroke-linejoin="round" fill="none" />
                            </svg>
                        </a>
                        <button class="share-btn" aria-label="Xでシェアする">
                            <svg viewBox="0 0 24 24">
                                <path
                                    d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                            </svg>
                        </button>
                    </div>
                </article>
"""
    return html

# ==========================================
# 🚀 キャッシュ管理 (API制限回避策)
# ==========================================
CACHE_FILE = "article_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    # 最新200件に制限
    if len(cache) > 200:
        keys_to_delete = list(cache.keys())[:-200]
        for k in keys_to_delete:
            del cache[k]
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"キャッシュの保存に失敗しました: {e}")

# ==========================================
# 🚀 メイン処理
# ==========================================
def main():
    JST = timezone(timedelta(hours=+9), 'JST')
    now = datetime.now(JST)

    tabs_btns_html = '        <div class="tabs-container" style="margin-top: 24px; max-width: 1200px; margin-left: auto; margin-right: auto; padding: 0 20px;">\\n            <div class="tab-list">\\n'
    for idx, cat in enumerate(CATEGORIES):
        is_active = ' active' if idx == 0 else ''
        tabs_btns_html += f'                <button class="tab-btn{is_active}" data-tab="{cat["id"]}">{cat["name"]}</button>\\n'
    tabs_btns_html += '            </div>\\n        </div>\\n\\n        <div class="layout-wrapper">\\n            <main aria-labelledby="app-title">\\n'

    panes_html = ""
    total_articles = 0
    cache = load_cache()
    all_analyzed_articles = []

    for idx, cat in enumerate(CATEGORIES):
        print(f"\n📡 {cat['name']} の記事を取得中...")
        is_active = ' active' if idx == 0 else ''
        panes_html += f'                <div id="{cat["id"]}" class="tab-pane{is_active}">\n'
        
        try:
            feed = feedparser.parse(cat["rss"])
            entries = feed.entries
            
            def get_published_time(entry):
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    return time.mktime(entry.published_parsed)
                return 0
            entries.sort(key=get_published_time, reverse=True)
            
            successful_count = 0
            target_count = 3
            
            for entry in entries:
                if successful_count >= target_count:
                    break
                    
                print(f"[{successful_count+1}/{target_count}] 記事を分析中: {entry.title}")
                
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=timezone.utc).astimezone(JST)
                    else:
                        pub_date = datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).astimezone(JST)       
                    diff = now - pub_date
                    hours = int(diff.total_seconds() / 3600)
                    if hours >= 24:
                        days = hours // 24
                        time_ago = f"{days}日前"
                    else:
                        time_ago = f"{hours}時間前" if hours > 0 else "たった今"
                except Exception:
                    time_ago = "最近"

                raw_url = getattr(entry, 'link', entry.title)
                article_url = clean_url(raw_url)

                if article_url in cache and cache[article_url].get('insight') != 'AIでの自動分析は現在一時的に停止中です。':
                    print("✅ キャッシュから記事データを読み込みます（APIリクエスト省略）")
                    article_data = cache[article_url]
                    article_data['time_ago'] = time_ago # time_agoは常に最新に更新
                else:
                    article_data = analyze_news_with_gemini(entry, time_ago)
                    
                    if article_data == "RATE_LIMIT":
                        print("⚠️ API制限に達しました。フォールバック用の記事データを生成して続行します。")
                        article_data = {
                            'title': entry.title,
                            'tags': 'News',
                            'sentiment': 'neutral',
                            'sentiment_text': '最新ニュース',
                            'rating': 3,
                            'time_ago': time_ago,
                            'url': article_url,
                            'summary_bullets': ['詳細なAI要約は現在API制限により取得できません。', 'リンク先より元記事をご覧ください。'],
                            'insight': 'AIでの自動分析は現在一時的に停止中です。',
                            'action_plan': 'ニュースの最新情報をチェックする',
                            'image_keyword': 'technology news digital'
                        }
                    elif isinstance(article_data, dict):
                        # URLをクリーンなものに上書き
                        article_data['url'] = article_url
                        # 成功した場合はキャッシュに保存
                        cache[article_url] = article_data
                        
                    time.sleep(20) # レートリミット対策 (Geminiの制限を完全に避けるため20秒待機)
                
                if isinstance(article_data, dict):
                    thumb_url = extract_thumbnail_url(entry, article_data)
                    element_id = f'{cat["id"].replace("tab-", "")}-{successful_count + 1}'
                    panes_html += generate_article_html(article_data, element_id, thumb_url)
                    all_analyzed_articles.append(article_data)
                    successful_count += 1
                    total_articles += 1
                else:
                    print("分析に失敗したためスキップし、次の記事でリトライします。")
                
        except Exception as e:
            print(f"{cat['name']} フィードの処理に失敗しました: {e}")
            
        panes_html += '                </div>\n'

    # 処理完了時にキャッシュを永続化
    save_cache(cache)

    if total_articles == 0:
        print("更新するHTMLが生成されませんでした。")
        return

    new_articles_html = tabs_btns_html + panes_html

    # index.htmlの書き換え
    print("📝 index.html ファイルを更新中...")
    try:
        with open(HTML_FILE_PATH, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 1. ニュースタブの更新（tabs-containerとlayout-wrapperを含む形式に）
        pattern = r'(<div class="tabs-container".*?)(<main aria-labelledby="app-title">)(.*?)(</main>)'
        replacement = new_articles_html + r'            \4'
        updated_html = re.sub(pattern, replacement, html_content, flags=re.DOTALL)
        
        # 2. ニュースティッカーの更新
        tickerPattern = r'(<div class="ticker">)(.*?)(</div>\s*</div>\s*<!-- Header Ad Banner)'
        new_ticker_html = generate_ticker_html()
        updated_html = re.sub(tickerPattern, rf'\1\n                {new_ticker_html}            \3', updated_html, flags=re.DOTALL)

        # 3. アクセスランキングの更新
        ranking_html = ""
        # 取得した記事から3件ピックアップしてランキング項目を作成
        top_articles = random.sample(all_analyzed_articles, min(3, len(all_analyzed_articles))) if all_analyzed_articles else []
        for i, article in enumerate(top_articles):
            title_text = article.get('title', '')
            url = article.get('url', '#')
            ranking_html += f'''                        <li>
                            <a href="{url}" class="ranking-item" target="_blank" rel="noopener noreferrer">
                                <span class="ranking-number">{i+1}</span>
                                <span class="ranking-text">{title_text}</span>
                            </a>
                        </li>\n'''
        
        ranking_pattern = r'(<ul class="ranking-list">)(.*?)(</ul>)'
        if ranking_html:
            updated_html = re.sub(ranking_pattern, rf'\1\n{ranking_html}                    \3', updated_html, flags=re.DOTALL)

        with open(HTML_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(updated_html)
            
        print("✨ 更新が完了しました！")
    except Exception as e:
        print(f"ファイルの書き換えに失敗しました: {e}")

if __name__ == "__main__":
    main()
