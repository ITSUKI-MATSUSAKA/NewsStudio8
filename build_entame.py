import os
import re
import shutil

entame_dir = os.path.expanduser("~/Desktop/EntameNews")
news_dir = os.path.expanduser("~/Desktop/NewsSummary")

# Copy base from NewsSummary to make sure it's 100% bug free and uses new SDK
shutil.copy(os.path.join(news_dir, "update_news.py"), os.path.join(entame_dir, "update_news.py"))
shutil.copy(os.path.join(news_dir, "index.html"), os.path.join(entame_dir, "index.html"))

# 1. Modify update_news.py
entame_update_news = os.path.join(entame_dir, "update_news.py")
with open(entame_update_news, "r") as f:
    content = f.read()

new_categories = '''CATEGORIES = [
    {"id": "tab-game", "name": "ゲーム", "rss": "https://news.google.com/rss/search?q=%28VALORANT%20OR%20APEX%20OR%20%22ARC%20raiders%22%20OR%20%E3%82%BF%E3%83%AB%E3%82%B3%E3%83%95%20OR%20%22%E3%82%B9%E3%83%88%E3%83%AA%E3%83%BC%E3%83%88%E3%83%95%E3%82%A1%E3%82%A4%E3%82%BF%E3%83%BC6%22%20OR%20%E3%82%B9%E3%83%886%29%20%28%E5%A4%A7%E4%BC%9A%20OR%20%E6%94%BB%E7%95%A5%20OR%20e%E3%82%B9%E3%83%9D%E3%83%BC%E3%83%84%29&hl=ja&gl=JP&ceid=JP:ja"},
    {"id": "tab-book", "name": "本", "rss": "https://natalie.mu/comic/feed/news"},
    {"id": "tab-movie", "name": "映画", "rss": "https://news.google.com/rss/search?q=%28Netflix%20OR%20%22Amazon%20Prime%20Video%22%20OR%20%E3%83%8D%E3%83%88%E3%83%95%E3%83%AA%20OR%20%E3%82%A2%E3%83%9E%E3%83%97%E3%83%A9%29%20%28%E3%81%8A%E3%81%99%E3%81%99%E3%82%81%20OR%20%E6%96%B0%E4%BD%9C%29%20%28%E6%98%A0%E7%94%BB%20OR%20%E6%B5%B7%E5%A4%96%E3%83%89%E3%83%A9%E3%83%9E%29&hl=ja&gl=JP&ceid=JP:ja"},
    {"id": "tab-music", "name": "音楽", "rss": "https://news.google.com/rss/search?q=%28%22%E6%B4%8B%E6%A5%BD%22%20OR%20%22%E6%B5%B7%E5%A4%96%E3%83%90%E3%83%B3%E3%83%89%22%20OR%20%22%E6%B5%B7%E5%A4%96%E3%82%A2%E3%83%BC%E3%83%86%E3%82%A3%E3%82%B9%E3%83%88%22%20OR%20%22%E9%82%A6%E6%A5%BD%22%29%20%28%E3%83%95%E3%82%A7%E3%82%B9%20OR%20%E3%83%AD%E3%83%83%E3%82%AF%20OR%20%E3%83%92%E3%83%83%E3%83%97%E3%83%9B%E3%83%83%E3%83%97%20OR%20EDM%29&hl=ja&gl=JP&ceid=JP:ja"},
    {"id": "tab-coffee", "name": "コーヒー", "rss": "https://news.google.com/rss/search?q=%28%E3%82%B3%E3%83%BC%E3%83%92%E3%83%BC%20OR%20%E3%82%AB%E3%83%95%E3%82%A7%20OR%20%E3%82%B9%E3%82%BF%E3%83%90%20OR%20%E3%82%BF%E3%83%AA%E3%83%BC%E3%82%BA%29%20%28%E6%96%B0%E4%BD%9C%20OR%20%E3%83%AC%E3%83%93%E3%83%A5%E3%83%BC%29&hl=ja&gl=JP&ceid=JP:ja"}
]'''
content = re.sub(r'CATEGORIES\s*=\s*\[.*?\]', new_categories, content, flags=re.DOTALL)

new_prompt = '''prompt = f"""
あなたはポップで読者をワクワクさせるエンタメメディアの凄腕エディターです。
以下のニュース記事情報を分析し、指定されたフォーマットのJSONのみを返してください。不要なテキストを含めないでください。

【ニュース情報】
タイトル: {entry.title}
概要/URL: {entry.link}
発表時間: {time_ago}

【出力ルール・出力JSONフォーマット】
{{
  "title": "記事のタイトルをベースに、読者を惹きつけるワクワクする日本語タイトルに調整",
  "tags": "Game", "Anime", "Movie", "Cafe"などのような1〜2単語の英語またはカタカナのジャンルタグ（必ず文字列で1つだけ指定）,
  "sentiment": "positive", "negative", "neutral" のいずれか（明るい話題はpositive、懸念はnegative、一般的な製品発表などはneutral）,
  "sentiment_text": "「神アプデ」「期待の新作」「注目の話題」など、sentimentに合わせたポップな日本語テキスト",
  "rating": 3〜5の整数（エンタメとしての期待度・注目度）,
  "time_ago": "{time_ago}",
  "url": "{entry.link}",
  "summary_bullets": [
    "ニュースのもっともワクワクするポイント（簡潔な1行）",
    "ファンにとっての重要情報（簡潔な1行）",
    "今後の展開や期待（簡潔な1行）"
  ],
  "insight": "このニュース・作品の見どころや魅力（Fascinating Point）（2文程度で魅力が伝わる内容）",
  "action_plan": "読者が次に見るべき関連作品やおすすめの行動（Next Step）（「〜をチェックしてみましょう」「原作を読んでみよう等」）",
  "image_keyword": "記事の内容を的確に表す英語の画像検索キーワード2〜3語（例: pop culture, fantasy movie, cafe style）",
  "technical_terms": []
}}
"""'''
content = re.sub(r'prompt\s*=\s*f"""\nあなたは先進的なAI.*?\}\n"""', new_prompt, content, flags=re.DOTALL)

content = content.replace('Business Insight', 'Fascinating Point')
content = content.replace('今日からできるアクション', 'Next Step（次のおすすめ行動）')

with open(entame_update_news, "w") as f:
    f.write(content)

# 2. Modify index.html to match
entame_index = os.path.join(entame_dir, "index.html")
with open(entame_index, "r") as f:
    html = f.read()

# Change title
html = html.replace('<title>AIテックトレンド・最新ニュース</title>', '<title>最新エンタメニュース</title>')
html = html.replace('10秒でわかる！最新テックハイライト', '10秒でわかる！エンタメハイライト')
html = html.replace('Business Insight', 'Fascinating Point')
html = html.replace('今日からできるアクション', 'Next Step（次のおすすめ行動）')

# It's better to just let update_news.py rewrite the main block, but we should make sure the header looks entame-ish!
# Replace banner ad to say "準備中"
# wait, user specifically asked: "右側の広告バナーは消えてるしサイトの記事がほとんど読めないしバグってる" for NewsSummary, but for EntameNews they asked earlier to remove ads and show "Preparing"
html = re.sub(r'<div class="header-banner">.*?</div>', '<div class="header-banner"><div class="banner-text"><div class="banner-title">広告エリア</div><div class="banner-desc">現在準備中です</div></div></div>', html, flags=re.DOTALL)

html = html.replace('AI・ロボット・半導体の最新技術トレンドを毎朝7:00にお届けします', 'ゲーム・本・映画・音楽・コーヒーの最新エンタメニュースを毎日お届けします')

with open(entame_index, "w") as f:
    f.write(html)

# 3. Remove .git
git_path = os.path.join(entame_dir, ".git")
if os.path.exists(git_path):
    shutil.rmtree(git_path)

# Empty cache
cache_path = os.path.join(entame_dir, "article_cache.json")
if os.path.exists(cache_path):
    os.remove(cache_path)

print("EntameNews preparation completed successfully.")
