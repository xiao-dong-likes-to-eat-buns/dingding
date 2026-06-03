#!/usr/bin/env python3
"""
保密行业早报 + AI选择题 每日钉钉推送
版本：v2.0 增强版
AI平台：硅基流动 SiliconFlow
模型：Qwen/Qwen2.5-7B-Instruct（免费）
"""
import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import os
import re
import random
import requests
from datetime import datetime
from bs4 import BeautifulSoup


# ============ 从环境变量读取 ============
WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=e17adcd8cc53e1b0ad5fbf4ee5068e2f6f07f1978dab344863b760598c9a47cf")
SECRET  = os.environ.get("DINGTALK_SECRET", "SEC9c363ba29c8f07aa7b0d844ebcca7e222379cef30605a570378d5076e90c99ea")
SILICON_API_KEY = os.environ.get("SILICON_API_KEY", "sk-hnhvcflnqfxtltspkvewybaqmooionihahrenoetzuwnynrm")

# ============ 硅基流动配置 ============
SILICON_BASE_URL = "https://api.siliconflow.cn/v1"
SILICON_MODEL    = "Qwen/Qwen2.5-7B-Instruct"


# =============================================
#       硅基流动 API 调用（兼容 OpenAI 格式）
# =============================================

def call_ai(prompt):
    """
    调用硅基流动 SiliconFlow API
    接口兼容 OpenAI 格式(citation:1)(citation:6)
    """
    headers = {
        "Authorization": f"Bearer {SILICON_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": SILICON_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是资深保密行业媒体编辑，擅长新闻整理和出题。"
                    "只返回合法JSON格式，不要用markdown代码块包裹，"
                    "不要添加任何多余文字。"
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 4000,
        "stream": False
    }

    resp = requests.post(
        f"{SILICON_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )
    resp.raise_for_status()

    result = resp.json()
    content = result["choices"][0]["message"]["content"].strip()
    return content


# =============================================
#       新闻抓取模块（增强版：带正文+链接）
# =============================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def fetch_article_content(url, max_chars=800):
    """抓取单篇文章的正文内容"""
    try:
        if not url or not url.startswith("http"):
            return ""
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        content_area = (
            soup.find("article")
            or soup.find("div", class_=re.compile(
                r"content|article|detail|body|rich_media_content"
            ))
            or soup.find("div", id=re.compile(
                r"content|article|detail"
            ))
        )
        if content_area:
            for tag in content_area.find_all(
                ["script", "style", "nav", "footer"]
            ):
                tag.decompose()
            text = content_area.get_text(separator="\n", strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text[:max_chars]
    except Exception as e:
        print(f"      抓正文失败: {e}")
    return ""


def fetch_sogou_weixin(keyword):
    """从搜狗微信搜索获取公众号文章"""
    news = []
    try:
        url = (
            f"https://weixin.sogou.com/weixin?type=2"
            f"&query={urllib.parse.quote(keyword)}"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for item in soup.find_all("div", class_="txt-box")[:6]:
            a_tag = item.find("a")
            p_tag = item.find("p", class_="txt-info")
            if a_tag:
                href = a_tag.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://weixin.sogou.com" + href
                news.append({
                    "title": a_tag.get_text(strip=True),
                    "summary": (
                        p_tag.get_text(strip=True) if p_tag else ""
                    ),
                    "source": "保密观(公众号)",
                    "url": href,
                    "content": ""
                })
    except Exception as e:
        print(f"    搜狗微信失败: {e}")
    return news


def fetch_gjbmj():
    """从国家保密局官网获取新闻"""
    news = []
    try:
        resp = requests.get(
            "http://www.gjbmj.gov.cn/",
            headers=HEADERS, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if len(title) > 8:
                href = a["href"]
                if not href.startswith("http"):
                    href = "http://www.gjbmj.gov.cn" + href
                news.append({
                    "title": title,
                    "summary": "",
                    "source": "国家保密局",
                    "url": href,
                    "content": ""
                })
    except Exception as e:
        print(f"    国家保密局失败: {e}")
    return news[:8]


def fetch_baomi_org():
    """从中国保密在线获取新闻"""
    news = []
    try:
        resp = requests.get(
            "http://www.baomi.org/",
            headers=HEADERS, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if len(title) > 10:
                href = a["href"]
                if not href.startswith("http"):
                    href = "http://www.baomi.org" + href
                news.append({
                    "title": title,
                    "summary": "",
                    "source": "中国保密在线",
                    "url": href,
                    "content": ""
                })
    except Exception as e:
        print(f"    中国保密在线失败: {e}")
    return news[:8]


def fetch_baidu_news(keyword):
    """从百度资讯搜索获取保密相关新闻"""
    news = []
    try:
        url = (
            f"https://www.baidu.com/s?rtt=1&bsst=1"
            f"&cl=2&tn=news&ie=utf-8"
            f"&word={urllib.parse.quote(keyword)}"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        results = soup.find_all(
            "div",
            class_=re.compile(r"result-op c-container|c-container")
        )
        for item in results[:6]:
            a_tag = item.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if len(title) < 8:
                continue
            summary_tag = item.find(
                "span",
                class_=re.compile(r"c-font-normal|content-right")
            )
            summary = (
                summary_tag.get_text(strip=True) if summary_tag else ""
            )
            source_tag = item.find(
                "span",
                class_=re.compile(r"c-color-gray")
            )
            source = (
                source_tag.get_text(strip=True)
                if source_tag else "百度资讯"
            )
            news.append({
                "title": title,
                "summary": summary,
                "source": source,
                "url": a_tag.get("href", ""),
                "content": ""
            })
    except Exception as e:
        print(f"    百度资讯失败: {e}")
    return news


def fetch_all_news():
    """汇总所有来源并抓取正文"""
    all_news = []

    print("  [1/5] 搜狗微信 - 保密观...")
    all_news += fetch_sogou_weixin("保密观")
    time.sleep(random.randint(2, 4))

    print("  [2/5] 搜狗微信 - 保密政策...")
    all_news += fetch_sogou_weixin("保密工作 国家安全")
    time.sleep(random.randint(2, 4))

    print("  [3/5] 百度资讯...")
    all_news += fetch_baidu_news("保密工作 最新")
    time.sleep(random.randint(2, 4))

    print("  [4/5] 国家保密局官网...")
    all_news += fetch_gjbmj()

    print("  [5/5] 中国保密在线...")
    all_news += fetch_baomi_org()

    # 去重
    seen = set()
    unique = []
    for item in all_news:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)
    print(f"  去重后共 {len(unique)} 条新闻")

    # 抓取前6篇文章正文
    print("  正在抓取文章正文...")
    for i, item in enumerate(unique[:6]):
        if item.get("url") and not item.get("content"):
            print(f"    [{i+1}/6] {item['title'][:30]}...")
            item["content"] = fetch_article_content(item["url"])
            time.sleep(random.randint(1, 3))

    return unique


# =============================================
#    AI 生成增强版早报 + 选择题
# =============================================

def generate_briefing_and_quiz(news_list):
    """将新闻素材交给AI生成增强版早报+选择题"""
    today = datetime.now()
    weekday_names = [
        "星期一", "星期二", "星期三",
        "星期四", "星期五", "星期六", "星期日"
    ]
    weekday = weekday_names[today.weekday()]

    # 拼接新闻素材（含正文和链接）
    news_text = ""
    for i, item in enumerate(news_list[:10], 1):
        news_text += f"\n--- 第{i}条 ---\n"
        news_text += f"标题：{item['title']}\n"
        news_text += f"来源：{item['source']}\n"
        if item.get("url"):
            news_text += f"链接：{item['url']}\n"
        if item.get("summary"):
            news_text += f"摘要：{item['summary']}\n"
        if item.get("content"):
            news_text += f"正文：{item['content'][:600]}\n"

    if not news_text.strip():
        news_text = "（今日暂未抓取到新闻，请根据保密行业热点生成）"

    prompt = f"""今天是{today.strftime('%Y年%m月%d日')} {weekday}。

以下是从权威媒体抓取的保密新闻素材，每条包含标题、来源、链接和正文：
{news_text}

请完成两项任务：

任务一：增强版行业早报
整理成「保密行业早报」，格式如下：

开头：🔐 **保密行业早报** | {today.strftime('%m月%d日')} {weekday}

📌 **今日要闻**（1-2条重要新闻）：
每条格式：
**序号. 标题** [来源]
2-3句话概括核心要点（涉及单位、具体事件、关键数据）
🔗 [查看原文](链接地址)

📰 **行业动态**（3-5条次要新闻）：
每条格式：
**序号. 标题** [来源]
一句话概括核心内容
🔗 [查看原文](链接地址)

🔑 **今日关键词**：3个关键词

📝 **编辑点评**：1-2句话概括今日态势

每条新闻务必附上链接。有正文内容时请基于正文提炼要点。

任务二：保密知识选择题
根据新闻内容和保密知识，生成6道单选题：
- 每题4个选项，1个正确答案
- 至少3道题直接来源于今日新闻
- 适合企业保密培训
- 每题附简短解析

严格按此JSON格式返回，不要用代码块，不要加其他文字：
{{"briefing": "早报markdown全文", "questions": [{{"question": "题目？", "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"], "answer": "A", "explanation": "解析"}}]}}"""

    try:
        raw_text = call_ai(prompt)
        print(f"  AI返回 {len(raw_text)} 字")

        cleaned = raw_text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()

        json_match = re.search(r'\{[\s\S]*\}', cleaned)
        if json_match:
            cleaned = json_match.group()

        return json.loads(cleaned)

    except Exception as e:
        print(f"  AI生成/解析失败: {e}")
        return generate_fallback(today, weekday, news_list)


def generate_fallback(today, weekday, news_list):
    """AI失败时的备用方案：直接拼接抓取的新闻"""
    briefing = (
        f"🔐 **保密行业早报** | "
        f"{today.strftime('%m月%d日')} {weekday}\n\n"
    )

    if news_list:
        briefing += "📌 **今日要闻**\n\n"
        for i, item in enumerate(news_list[:8], 1):
            briefing += f"**{i}. {item['title']}** "
            briefing += f"[{item['source']}]\n"
            if item.get("summary"):
                briefing += f"{item['summary']}\n"
            if item.get("url"):
                briefing += f"🔗 [查看原文]({item['url']})\n"
            briefing += "\n"
    else:
        briefing += "今日暂未获取到新闻，请检查配置。\n\n"

    briefing += "> 请关注「保密观」微信公众号获取更多资讯。"

    return {
        "briefing": briefing,
        "questions": [
            {
                "question": (
                    "涉密计算机连接互联网可能导致什么后果？"
                ),
                "options": [
                    "A. 无任何风险",
                    "B. 可能导致国家秘密泄露",
                    "C. 仅影响电脑速度",
                    "D. 只会导致断网"
                ],
                "answer": "B",
                "explanation": (
                    "涉密计算机连接互联网可能被植入木马、"
                    "远程控制，导致涉密信息泄露。"
                )
            }
        ]
    }


# =============================================
#            钉钉消息推送
# =============================================

def get_signed_url():
    """生成带签名的钉钉 Webhook 地址"""
    ts = str(round(time.time() * 1000))
    sign_str = f"{ts}\n{SECRET}"
    hmac_code = hmac.new(
        SECRET.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"{WEBHOOK}&timestamp={ts}&sign={sign}"


def send_markdown(title, content):
    """发送 Markdown 消息到钉钉群"""
    url = get_signed_url()
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": content}
    }
    resp = requests.post(url, json=payload, timeout=10)
    res = resp.json()
    if res.get("errcode") == 0:
        print(f"    ✅ {title} 推送成功")
    else:
        print(f"    ❌ {title} 推送失败: {res}")
    return res


def send_to_dingtalk(briefing, questions):
    """依次推送早报和选择题"""
    today = datetime.now().strftime("%m月%d日")

    # 推送早报（超长分段）
    print("  推送早报...")
    if len(briefing) > 18000:
        send_markdown(
            "🔐 保密行业早报（上）",
            briefing[:18000] + "\n\n> 见下一条"
        )
        time.sleep(2)
        send_markdown("🔐 保密行业早报（下）", briefing[18000:])
    else:
        send_markdown("🔐 保密行业早报", briefing)

    time.sleep(2)

    # 推送选择题
    print("  推送选择题...")
    quiz_text = (
        f"## 📝 保密知识测试 | {today}\n\n"
        f"> 请先独立作答，答案在消息下方\n\n---\n\n"
    )

    for i, q in enumerate(questions, 1):
        quiz_text += f"**第{i}题：{q['question']}**\n\n"
        for opt in q["options"]:
            quiz_text += f"{opt}\n"
        quiz_text += "\n"

    quiz_text += "---\n\n## 📋 答案与解析\n\n"
    for i, q in enumerate(questions, 1):
        quiz_text += f"**{i}. 答案：{q['answer']}**\n"
        quiz_text += f"> {q['explanation']}\n\n"

    send_markdown(f"📝 保密测试 {today}", quiz_text)


# =============================================
#               主程序入口
# =============================================

def main():
    print()
    print("=" * 55)
    print(f"  🔐 保密行业早报推送 v2.0（硅基流动版）")
    print(f"  模型：{SILICON_MODEL}")
    print(f"  时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # 第一步：抓取新闻
    print("\n[1/3] 从权威媒体抓取保密新闻...")
    news = fetch_all_news()

    # 第二步：AI 生成早报+选择题
    print("\n[2/3] 调用硅基流动AI生成增强版早报...")
    result = generate_briefing_and_quiz(news)
    briefing = result.get("briefing", "")
    questions = result.get("questions", [])
    print(f"  早报 {len(briefing)} 字, 选择题 {len(questions)} 道")

    # 第三步：推送到钉钉
    print("\n[3/3] 推送到钉钉群...")
    send_to_dingtalk(briefing, questions)

    print("\n🎉 今日增强版早报推送完成！")


if __name__ == "__main__":
    main()
