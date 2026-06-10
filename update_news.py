import os
import re
import html
import json
import time
import hashlib
import urllib.parse
import urllib.request
import random
from datetime import datetime, timezone, timedelta
from google import genai

try:
    import feedparser
    import requests
except ImportError:
    print("【エラー】必要なライブラリが不足しています。")
    print("ターミナルで以下のコマンドを実行してインストールしてください：")
    print("pip install feedparser requests google-genai")
    exit(1)

# ==========================================
# ⚙️ 設定
# ==========================================
# Google GeminiのAPIキーをここに設定してください（無料枠で利用可能です）
# 取得方法: https://aistudio.google.com/app/apikey
# API_KEYは環境変数から読み込むため、ここでは設定しません。

# 取得するニュースのRSSフィード（カテゴリーごとに複数指定でソース多様化）
CATEGORIES = [
    {
        "id": "tab-ai", "name": "AI",
        "feeds": [
            "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",
            "https://news.google.com/rss/search?q=AI+生成AI+人工知能&hl=ja&gl=JP&ceid=JP:ja",
        ]
    },
    {
        "id": "tab-it", "name": "IT",
        "feeds": [
            "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
            "https://news.google.com/rss/search?q=IT+テクノロジー+デジタル&hl=ja&gl=JP&ceid=JP:ja",
        ]
    },
    {
        "id": "tab-robotics", "name": "ロボット",
        "feeds": [
            "https://news.google.com/rss/search?q=ロボット+テクノロジー+自動化&hl=ja&gl=JP&ceid=JP:ja",
            "https://news.google.com/rss/search?q=ドローン+自動運転+ロボット&hl=ja&gl=JP&ceid=JP:ja",
        ]
    },
    {
        "id": "tab-semiconductor", "name": "半導体",
        "feeds": [
            "https://news.google.com/rss/search?q=半導体+チップ+製造&hl=ja&gl=JP&ceid=JP:ja",
            "https://news.google.com/rss/search?q=TSMC+NVIDIA+半導体産業&hl=ja&gl=JP&ceid=JP:ja",
        ]
    },
    {
        "id": "tab-security", "name": "セキュリティ",
        "feeds": [
            "https://rss.itmedia.co.jp/rss/2.0/news_security.xml",
            "https://news.google.com/rss/search?q=サイバーセキュリティ+情報漏洩&hl=ja&gl=JP&ceid=JP:ja",
        ]
    },
]

# 更新するHTMLファイルのパス
HTML_FILE_PATH = "index.html"

# AI要約の有効/無効 (Trueに変えると Gemini API でAI要約を生成します)
GEMINI_ENABLED = False

# ジャンルタグの色・背景色
TAG_COLORS = {
    'AI':          '#7c3aed',
    'ロボット':    '#059669',
    '半導体':      '#d97706',
    'セキュリティ': '#dc2626',
}
TAG_TINTS = {
    'AI':          'rgba(124, 58, 237, 0.10)',
    'ロボット':    'rgba(5, 150, 105, 0.10)',
    '半導体':      'rgba(217, 119, 6, 0.10)',
    'セキュリティ': 'rgba(220, 38, 38, 0.10)',
}

# 記事URLからソース名を抽出
SOURCE_MAP = {
    'itmedia.co.jp':         'ITmedia',
    'monoist.itmedia.co.jp': 'MONOist',
    'eetimes.itmedia.co.jp': 'EE Times',
    'news.yahoo.co.jp':      'Yahoo!ニュース',
    'nikkei.com':            '日経',
    'asahi.com':             '朝日新聞',
    'mainichi.jp':           '毎日新聞',
    'ascii.jp':              'ASCII',
    'mynavi.jp':             'Mynavi',
    'zdnet.com':             'ZDNet',
    'google.com':            'Google News',
}

def get_source_name(url):
    try:
        host = urllib.parse.urlparse(url).netloc.replace('www.', '')
        for domain, name in SOURCE_MAP.items():
            if domain in host:
                return name
        return host.split('.')[0].capitalize()
    except Exception:
        return ''

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
DEBUG_LOG = "debug_errors.txt"

def _log_error(msg):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def analyze_news_with_gemini(entry, time_ago):
    API_KEY = os.environ.get("GEMINI_API_KEY", "")
    if not API_KEY:
        _log_error("FATAL: GEMINI_API_KEY is not set")
        return None
    
    # 新しいSDKでのクライアント初期化
    client = genai.Client(api_key=API_KEY)
    
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
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash-lite',
                contents=prompt,
            )

            # セーフティブロックなどのチェック
            if not response.candidates or not response.candidates[0].content.parts:
                print("【エラー】AIの出力がブロックされました（セーフティ機能等の影響）")
                if response.candidates:
                    print("Finish Reason:", response.candidates[0].finish_reason)
                return None  # セーフティブロックはリトライしても変わらないため即終了

            text = response.text.strip()

            # JSON部分だけを確実に抽出するフォールバック
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            json_str = text[start_idx:end_idx+1] if start_idx != -1 and end_idx != -1 else text

            return json.loads(json_str, strict=False)

        except json.JSONDecodeError as je:
            print(f"【JSON解析エラー】試行{attempt+1}/3: {je}")
            if attempt < 2:
                time.sleep(15)
                continue
            return None
        except Exception as e:
            error_msg = str(e)
            _log_error(f"RAW_ERROR [{entry.title[:40]}]: {error_msg}")
            if "429" in error_msg or "Quota exceeded" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                wait = 60 * (attempt + 1)
                print(f"\n【API制限エラー】試行{attempt+1}/3: {wait}秒待機後にリトライします...")
                if attempt < 2:
                    time.sleep(wait)
                    continue
                return "RATE_LIMIT"
            else:
                print(f"\n【Gemini API エラー】通信やAPIキーに問題がある可能性があります: {error_msg}")
                return None

    return None

# ==========================================
# 🖼️ サムネイル画像の抽出
# ==========================================
MIN_THUMB_WIDTH = 300  # これ未満の幅が判明している場合はプレースホルダーを使用

def fetch_og_image(url, timeout=3):
    """記事URLからog:imageメタタグの画像URLを取得する"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read(16384).decode('utf-8', errors='ignore')
        for pattern in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']{10,})["\']',
            r'<meta[^>]+content=["\']([^"\']{10,})["\'][^>]+property=["\']og:image["\']',
        ]:
            m = re.search(pattern, content, re.IGNORECASE)
            if m and m.group(1).startswith('http'):
                return m.group(1)
    except Exception:
        pass
    return None

def _pick_best_image(items, url_key='url', w_key='width', h_key='height'):
    """複数の画像候補から最高解像度のものを選ぶ。幅が判明していてMIN未満なら除外。"""
    candidates = []
    for item in items:
        url = item.get(url_key, '')
        if not url or not url.startswith('http'):
            continue
        try:
            w = int(item.get(w_key, 0))
        except (ValueError, TypeError):
            w = 0
        try:
            h = int(item.get(h_key, 0))
        except (ValueError, TypeError):
            h = 0
        if 0 < w < MIN_THUMB_WIDTH:
            continue  # 幅が判明していて小さすぎる
        candidates.append((w * h, url))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]

def extract_thumbnail_url(entry, article_data=None):
    # 1. media_thumbnail（複数あれば最高解像度を選択）
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        url = _pick_best_image(entry.media_thumbnail)
        if url:
            return url
    # 2. media_content（複数あれば最高解像度を選択）
    if hasattr(entry, 'media_content') and entry.media_content:
        imgs = [mc for mc in entry.media_content
                if any(ext in mc.get('url', '').lower() for ext in ['.jpg', '.jpeg', '.png', '.webp'])]
        url = _pick_best_image(imgs)
        if url:
            return url
    # 3. image type リンク
    if hasattr(entry, 'links'):
        for link in entry.links:
            if link.get("type", "").startswith("image"):
                return link["href"]
    # 4. description/summary 内の <img>
    for field in ['description', 'summary']:
        text = getattr(entry, field, '') or ''
        if '<img' in text:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', text)
            if m and m.group(1).startswith('http'):
                return m.group(1)
    # 5. 記事ページの og:image を取得（写真系画像が期待できる）
    article_url = (article_data or {}).get('url', '') or getattr(entry, 'link', '')
    if article_url:
        og = fetch_og_image(article_url)
        if og:
            return og
    # 6. 画像なし → プレースホルダー表示
    return None

# ==========================================
# 🏗️ HTMLの生成
# ==========================================
def generate_article_html(article_data, element_id, thumb_url, is_first=False):
    tag       = article_data.get('tags', 'News')
    url       = article_data.get('url', '#')
    title     = article_data.get('title', '')
    time_ago  = article_data.get('time_ago', '')
    desc      = article_data.get('description', '')
    source    = article_data.get('source', '')

    tag_color  = TAG_COLORS.get(tag, '#6b7280')
    tint       = TAG_TINTS.get(tag, 'rgba(107,114,128,0.08)')
    tag_html   = f'<span class="tag" style="background:{tag_color};color:#fff;">{tag}</span>'
    desc_html  = f'<p class="article-desc">{desc}</p>' if desc else ''
    src_text   = f'{source} · {time_ago}' if source else time_ago

    if thumb_url:
        thumb_html = f'<img src="{thumb_url}" alt="" class="card-thumbnail" loading="lazy">'
    else:
        # 画像なし・小さすぎる場合はジャンル色背景＋カメラアイコンで統一
        thumb_html = (
            f'<div class="thumb-placeholder">'
            f'<svg width="40" height="40" viewBox="0 0 24 24" fill="none" '
            f'stroke="{tag_color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5">'
            f'<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
            f'<circle cx="12" cy="13" r="4"/>'
            f'</svg>'
            f'</div>'
        )

    if is_first:
        return f"""
                <!-- Article {element_id} (featured) -->
                <article class="news-card featured" id="article-{element_id}">
                    <div class="thumb-wrapper" style="background:{tint};">
                        {thumb_html}
                    </div>
                    <div class="card-content">
                        <div class="tag-group">
                            {tag_html}
                            <span class="tag-secondary">注目</span>
                        </div>
                        <h2 class="news-title"><a href="{url}" target="_blank"
                                rel="noopener noreferrer" class="title-link">{title}</a></h2>
                        {desc_html}
                        <div class="source-time">{src_text}</div>
                    </div>
                </article>
"""
    else:
        return f"""
                <!-- Article {element_id} -->
                <article class="news-card" id="article-{element_id}">
                    <div class="thumb-wrapper" style="background:{tint};">
                        {thumb_html}
                    </div>
                    <div class="card-content">
                        {tag_html}
                        <h2 class="news-title"><a href="{url}" target="_blank"
                                rel="noopener noreferrer" class="title-link">{title}</a></h2>
                        {desc_html}
                        <div class="source-time">{src_text}</div>
                    </div>
                </article>
"""

# ==========================================
# 🚀 キャッシュ管理 (API制限回避策)
# ==========================================
CACHE_FILE = "article_cache.json"

def get_cache_key(title):
    """記事タイトルのハッシュをキャッシュキーとして返す。
    URLはGoogle NewsなどでRSS取得のたびに変化するため、
    タイトルベースにすることで同じ記事の重複API呼び出しを防ぐ。"""
    return hashlib.md5(title.lower().strip().encode('utf-8')).hexdigest()

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
    open(DEBUG_LOG, "w").close()  # 実行ごとにログをリセット
    JST = timezone(timedelta(hours=+9), 'JST')
    now = datetime.now(JST)

    tabs_btns_html = '        <div class="tabs-container" style="margin-top: 24px; max-width: 1200px; margin-left: auto; margin-right: auto; padding: 0 20px;">\\n            <div class="tab-list">\\n'
    for cat in CATEGORIES:
        tabs_btns_html += f'                <button class="tab-btn" data-tab="{cat["id"]}">{cat["name"]}</button>\\n'
    tabs_btns_html += '            </div>\\n        </div>\\n\\n        <div class="layout-wrapper">\\n            <main aria-labelledby="app-title">\\n'

    panes_html = ""
    total_articles = 0
    cache = load_cache()
    all_analyzed_articles = []

    def get_published_time(entry):
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            return time.mktime(entry.published_parsed)
        return 0

    for cat in CATEGORIES:
        print(f"\n📡 {cat['name']} の記事を取得中...")
        color = TAG_COLORS.get(cat['name'], '#6b7280')
        panes_html += f'                <section id="{cat["id"]}" class="category-section">\n'
        panes_html += f'                    <h2 class="section-heading"><span class="tag" style="background:{color};color:#fff;">{cat["name"]}</span></h2>\n'
        panes_html += '                    <div class="articles-grid">\n'

        try:
            # 複数フィードからエントリを収集して重複排除
            all_entries = []
            for rss_url in cat["feeds"]:
                try:
                    f = feedparser.parse(rss_url, agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                    all_entries.extend(f.entries)
                except Exception:
                    pass
            seen_keys = set()
            entries = []
            for e in all_entries:
                key = e.title.lower().strip()[:30]
                if key not in seen_keys:
                    seen_keys.add(key)
                    entries.append(e)
            entries.sort(key=get_published_time, reverse=True)

            successful_count = 0
            target_count = 5

            for entry in entries:
                if successful_count >= target_count:
                    break

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
                cache_key = get_cache_key(entry.title)

                if not GEMINI_ENABLED:
                    raw_desc = getattr(entry, 'summary', '') or getattr(entry, 'description', '') or ''
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', '', raw_desc)).strip()
                    if not clean_desc:
                        continue  # 説明文なしの記事はスキップ
                    if len(clean_desc) > 280:
                        clean_desc = clean_desc[:277] + '…'
                    article_data = {
                        'title': entry.title,
                        'tags': cat['name'],
                        'time_ago': time_ago,
                        'url': article_url,
                        'description': clean_desc,
                        'source': get_source_name(article_url),
                        'image_keyword': entry.title,
                    }
                elif cache_key in cache and cache[cache_key].get('insight') != 'AIでの自動分析は現在一時的に停止中です。':
                    print("✅ キャッシュから記事データを読み込みます（APIリクエスト省略）")
                    article_data = cache[cache_key].copy()
                    article_data['time_ago'] = time_ago
                    article_data['url'] = article_url
                else:
                    # GEMINI_ENABLED = True のときだけここを通る
                    article_data = analyze_news_with_gemini(entry, time_ago)
                    if article_data == "RATE_LIMIT" or not article_data:
                        article_data = {
                            'title': entry.title,
                            'tags': cat['name'],
                            'time_ago': time_ago,
                            'url': article_url,
                            'description': '',
                            'source': get_source_name(article_url),
                            'image_keyword': entry.title,
                        }
                    elif isinstance(article_data, dict):
                        article_data['url'] = article_url
                        cache[cache_key] = article_data
                    time.sleep(35)

                if isinstance(article_data, dict):
                    thumb_url = extract_thumbnail_url(entry, article_data)
                    element_id = f'{cat["id"].replace("tab-", "")}-{successful_count + 1}'
                    panes_html += generate_article_html(article_data, element_id, thumb_url, is_first=(successful_count == 0))
                    all_analyzed_articles.append(article_data)
                    successful_count += 1
                    total_articles += 1

        except Exception as e:
            print(f"{cat['name']} フィードの処理に失敗しました: {e}")

        panes_html += '                    </div>\n'
        panes_html += '                </section>\n'

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

# test 