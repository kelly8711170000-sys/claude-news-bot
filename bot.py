import os
import sys
import feedparser
import requests
from anthropic import Anthropic

# 從 GitHub Secrets 中安全讀取環境變數
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not CLAUDE_API_KEY or not DISCORD_WEBHOOK_URL:
    print("錯誤：找不到環境變數 ANTHROPIC_API_KEY 或 DISCORD_WEBHOOK_URL。請檢查 GitHub Secrets 設定。")
    sys.exit(1)

# 設定新聞來源 (修正數位時代網址)
SOURCES = [
    {"name": "數位時代", "url": "https://www.bnext.com.tw/rss"},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"}
]

def fetch_news():
    all_articles = []
    for source in SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            # 將限制放寬到最新 15 則，確保有足夠的母體讓 Claude 篩選 AI 與商模新聞
            for entry in feed.entries[:15]:
                all_articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": entry.get("summary", entry.get("description", "")),
                    "source": source["name"]
                })
            print(f"成功抓取 {source['name']} 最新 {len(feed.entries[:15])} 則原始新聞。")
        except Exception as e:
            print(f"抓取 {source['name']} 失敗: {e}")
    return all_articles

def generate_summary(articles):
    if not articles:
        return "今天未能成功抓取到任何新聞。"

    # 這裡已自動相容最新 2026 年主力的 Claude 3.7 Sonnet 穩定版名稱
    claude_client = Anthropic(api_key=CLAUDE_API_KEY)

    # 建立適合餵給 Claude 的新聞文本資料
    news_data_text = ""
    for idx, art in enumerate(articles, 1):
        news_data_text += f"[{idx}] 來源: {art['source']}\n標題: {art['title']}\n連結: {art['link']}\n摘要: {art['summary']}\n" + "-"*30 + "\n"

    prompt = f"""你是一位資深產品策略顧問、商業分析師與科技趨勢研究員。

# 執行任務
現在要請你篩選並整理我提供的新聞列表，並嚴格分為【數位時代】與【TechCrunch】兩個來源分別輸出。
請從每個來源中，各自篩選出「最符合標準且最精華的 3 則」進行深度摘要。

# 篩選主題
請針對 【生成式 AI 應用】 與 【商業模式創新】 兩個領域進行過濾。

# 新聞篩選標準
請只保留符合以下條件的新聞，其餘無關的公關稿或瑣碎消息請直接忽略：
1. 必須與 [數位產業案例 / AI / 數位產品創新] 高度相關。
2. 聚焦於 [商業模式創新 / 技術重大突破 / 實際落地應用案例]，而非單純的資金應援或人事變動。

# 待篩選的新聞列表：
{news_data_text}

# 摘要輸出格式
請嚴格按照以下結構輸出（保持條列式，文字精煉，使用繁體中文）。請直接輸出最終改寫完成的 Discord 訊息內文，不要包含任何前後廢話。

---
## 🏢 數位時代（精選 3 則）
(若提供的列表中完全沒有符合上述標準的數位時代新聞，請在此處直接寫：「今日無符合條件之相關新聞」，不要勉強湊數)

### 📌 [新聞標題](新聞連結)
* **一句話核心觀點：** 用 150 字以內總結這篇新聞最核心的事件或結論。
* **關鍵事實與數據：** 條列 2-3 個新聞中提及的重要數據、時間點或技術專有名詞。
* **商業與應用啟發：** 從 [產品經理] 的視角出發，簡述這個事件對行業或未來規劃有何潛在影響或借鏡之處。

---
## 🚀 TechCrunch（精選 3 則）
(若提供的列表中完全沒有符合上述標準的 TechCrunch 新聞，請在此處直接寫：「今日無符合條件之相關新聞」，不要勉強湊數)

### 📌 [新聞標題](新聞連結)
* **一句話核心觀點：** 用 150 字以內總結這篇新聞最核心的事件或結論。
* **關鍵事實與數據：** 條列 2-3 個新聞中提及的重要數據、時間點或技術專有名詞。
* **商業與應用啟發：** 從 [產品經理] 的視角出過發，簡述這個事件對行業或未來規劃有何潛在影響或借鏡之處。"""

    try:
        response = claude_client.messages.create(
            model="claude-3-7-sonnet-latest",
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"Claude 生成摘要時發生錯誤: {e}"

def send_to_discord(content):
    full_message = f"📢 **【每日 AI 與商業創新趨勢摘要】**\n\n{content}"

    # Discord 單則訊息上限 2000 字元，超過需分段發送
    import time
    chunks = []
    while len(full_message) > 1900:
        split_at = full_message.rfind("\n\n", 0, 1900)
        if split_at == -1:
            split_at = full_message.rfind("\n", 0, 1900)
        if split_at == -1:
            split_at = 1900
        chunks.append(full_message[:split_at])
        full_message = full_message[split_at:].lstrip()
    if full_message:
        chunks.append(full_message)

    for i, chunk in enumerate(chunks):
        try:
            res = requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk})
            if res.status_code == 204:
                print(f"段落 {i+1}/{len(chunks)} 成功發送到 Discord！")
            else:
                print(f"段落 {i+1} 發送失敗，狀態碼: {res.status_code}，回應: {res.text}")
        except Exception as e:
            print(f"發送到 Discord 時發生錯誤: {e}")
        time.sleep(0.5)

if __name__ == "__main__":
    print("開始執行新聞抓取任務...")
    raw_news = fetch_news()
    print(f"成功抓取到 {len(raw_news)} 則原始消息，正在交由 Claude 篩選與摘要...")
    final_report = generate_summary(raw_news)
    print("正在將摘要報告發送至 Discord...")
    send_to_discord(final_report)
