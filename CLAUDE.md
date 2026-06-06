# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Japanese tech news aggregator website. `update_news.py` fetches articles from RSS feeds, analyzes each with the Gemini API, then rewrites `index.html` in place using regex substitution. The result is a single-file static site deployed via GitHub Pages.

## Running the update script

```bash
GEMINI_API_KEY=your_key python update_news.py
```

Requires: `pip install feedparser requests google-genai`

The script sleeps 20 seconds between Gemini API calls to avoid rate limits. A full run for 4 categories × 3 articles takes roughly 4–5 minutes.

## Architecture

**Data flow:**
1. `feedparser` fetches RSS feeds defined in `CATEGORIES`
2. For each entry: check `article_cache.json` → if miss, call Gemini (`gemini-2.5-flash`) → cache result
3. `generate_article_html()` builds HTML card strings
4. `generate_ticker_html()` fetches live market data from Yahoo Finance API
5. Three regex substitutions patch `index.html`: news tabs, ticker bar, and access ranking sidebar

**Cache** (`article_cache.json`): keyed by clean article URL, capped at 200 entries. Prevents re-calling Gemini for already-seen articles. Always check cache hit logic when changing the URL cleaning logic in `clean_url()`.

**HTML injection**: The script uses `re.sub` with `re.DOTALL` to find and replace specific regions in `index.html`. If the HTML structure of `index.html` changes (e.g. the `tabs-container` wrapper, ticker `<div>`, or `ranking-list` `<ul>`), the regex patterns in `main()` must be updated to match.

## Automation

**GitHub Actions** (`.github/workflows/`): Runs `update_news.py` daily at JST 07:00 and auto-commits `index.html` + `article_cache.json`. `GEMINI_API_KEY` must be set as a repository secret.

**Discord bot** (`discord_bot.py`): `!update` command in a designated channel triggers `update_news.py` as a subprocess. Requires `DISCORD_BOT_TOKEN` and optionally `DISCORD_CHANNEL_ID` environment variables.

## EntameNews variant

`build_entame.py` creates a sister site at `~/Desktop/EntameNews` by copying `update_news.py` and `index.html` from this repo and applying patches (different `CATEGORIES`, entertainment-focused Gemini prompt, updated UI labels). Run it after making changes to the base files that should propagate to EntameNews.

## Key environment variables

| Variable | Required | Used by |
|---|---|---|
| `GEMINI_API_KEY` | Yes | `update_news.py` |
| `DISCORD_BOT_TOKEN` | Bot only | `discord_bot.py` |
| `DISCORD_CHANNEL_ID` | Bot only | `discord_bot.py` |
