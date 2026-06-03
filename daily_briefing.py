#!/usr/bin/env python3
"""
保密行业早报 + AI选择题 每日钉钉推送
版本：v3.0 稳定版
AI平台：硅基流动 SiliconFlow
新闻源：百度资讯 + 政府网站 + 人民日报
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


# ============ 环境变量 ============
WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=e17adcd8cc53e1b0ad5fbf4ee5068e2f6f07f1978dab344863b760598c9a47cf")
SECRET  = os.environ.get("DINGTALK_SECRET", "SEC9c363ba29c8f07aa7b0d844ebcca7e222379cef30605a570378d5076e90c99ea")
SILICON_API_KEY = os.environ.get("SILICON_API_KEY", "sk-hnhvcflnqfxtltspkvewybaqmooionihahrenoetzuwnynrm")

# ============ 硅基流动配置 ============
SILICON_BASE_URL = "https://api.siliconflow.cn/v1"
SILICON_MODEL    = "Qwen/Qwen2.5-7B-Instruct"


# =============================================
#       硅基流动 API 调用
# =============================================

def call_ai(prompt):
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
                    "只返回合法JSON，不要用代码块包裹。"
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 4000,
        "stream": False
    }
    resp = requests.post(
        f"{SILICON_BASE_URL}/chat/completions",
        headers=headers, json=payload, timeout=60
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# =============================================
#    新闻抓取模块（v3 稳定版：去掉搜狗）
# =============================================

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def fetch_baidu_news(keyword):
    """
    百度资讯搜索 —— 最稳定的国内新闻源
    """
    news = []
    try:
        url = (
            "https://www.baidu.com/s?"
            "rtt=1&bsst=1&cl=2&tn=news&ie=utf-8"
            f"&word={urllib.parse.quote(keyword)}"
        )
        resp = requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 百度资讯搜索结果容器
        containers = soup.find_all(
            "div",
            class_=re.compile(
                r"result-op c-container|c-container"
            )
        )

        for item in containers[:8]:
            a_tag = item.find("a", href=True)
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            if len(title) < 6:
                continue

            # 提取摘要
            summary = ""
            for cls in [
                "c-font-normal",
                "content-right",
                "c-abstract"
            ]:
                s = item.find(
                    "span", class_=re.compile(cls)
                )
                if s:
                    summary = s.get_text(strip=True)
                    break

            # 提取来源名
            source = "百度资讯"
            for cls in ["c-color-gray", "source"]:
                s = item.find(
                    "span", class_=re.compile(cls)
                )
                if s:
                    txt = s.get_text(strip=True)
                    if txt and len(txt) < 30:
                        source = txt
                        break

            # 提取发布时间
            pub_time = ""
            time_tag = item.find(
                "span", class_=re.compile(r"c-color-gray")
            )
            if time_tag:
                t = time_tag.get_text(strip=True)
                if "小时" in t or "分钟" in t or "今天" in t:
                    pub_time = t

            href = a_tag.get("href", "")
            news.append({
                "title": title,
                "summary": summary,
                "source": source,
                "url": href,
                "time": pub_time,
                "content": ""
            })

    except Exception as e:
        print(f"    百度资讯[{keyword}]失败: {e}")
    return news


def fetch_gjbmj():
    """
    国家保密局官网
    """
    news = []
    try:
        resp = requests.get(
            "http://www.gjbmj.gov.cn/",
            headers={"User-Agent": UA},
            timeout=15
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
                    "time": "",
                    "content": ""
                })
    except Exception as e:
        print(f"    国家保密局失败: {e}")
    return news[:6]


def fetch_baomi_org():
    """
    中国保密在线
    """
    news = []
    try:
        resp = requests.get(
            "http://www.baomi.org/",
            headers={"User-Agent": UA},
            timeout=15
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
                    "time": "",
                    "content": ""
                })
    except Exception as e:
        print(f"    中国保密在线失败: {e}")
    return news[:6]


def fetch_article_content(url, max_chars=600):
    """
    抓取文章正文
    """
    try:
        if not url or not url.startswith("http"):
            return ""
        resp = requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=10
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        area = (
            soup.find("article")
            or soup.find(
                "div",
                class_=re.compile(
                    r"content|article|detail|body"
                    r"|rich_media_content"
                )
            )
            or soup.find(
                "div",
                id=re.compile(r"content|article")
            )
        )
        if area:
            for tag in area.find_all(
                ["script", "style", "nav", "footer"]
            ):
                tag.decompose()
            text = area.get_text(separator="\n", strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text[:max_chars]
    except Exception:
        pass
    return ""


def fetch_all_news():
    """
    汇总所有新闻源（v3 去掉搜狗，用百度资讯替代）
    """
    all_news = []

    # 来源1: 百度资讯 - 保密
    print("  [1/6] 百度资讯 - 保密...")
    all_news += fetch_baidu_news("保密工作 最新政策")
    time.sleep(random.randint(2, 4))

    # 来源2: 百度资讯 - 保密观
    print("  [2/6] 百度资讯 - 保密观...")
    all_news += fetch_baidu_news("保密观 微信公众号")
    time.sleep(random.randint(2, 4))

    # 来源3: 百度资讯 - 涉密
    print("  [3/6] 百度资讯 - 涉密...")
    all_news += fetch_baidu_news("涉密 国家秘密 案例")
    time.sleep(random.randint(2, 4))

    # 来源4: 百度资讯 - 国家安全
    print("  [4/6] 百度资讯 - 国家安全保密...")
    all_news += fetch_baidu_news("国家保密局 最新通知")
    time.sleep(random.randint(2, 4))

    # 来源5: 国家保密局官网
    print("  [5/6] 国家保密局官网...")
    all_news += fetch_gjbmj()

    # 来源6: 中国保密在线
    print("  [6/6] 中国保密在线...")
    all_news += fetch_baomi_org()

    # 去重
    seen = set()
    unique = []
    for item in all_news:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)

    print(f"  去重后共 {len(unique)} 条新闻")

    # 抓取前5篇正文
    print("  正在抓取正文...")
    count = 0
    for item in unique:
        if count >= 5:
            break
        if item.get("url") and not item.get("content"):
            content = fetch_article_content(item["url"])
            if content and len(content) > 50:
                item["content"] = content
                count += 1
                print(f"    ✓ {item['title'][:30]}...")
            time.sleep(random.randint(1, 2))

    return unique


# =============================================
#    AI 生成增强版早报 + 选择题
# =============================================

def generate_briefing_and_quiz(news_list):
    today = datetime.now()
    wk = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"]
    weekday = wk[today.weekday()]

    # 拼接素材
    news_text = ""
    for i, item in enumerate(news_list[:10], 1):
        news_text += f"\n--- 第{i}条 ---\n"
        news_text += f"标题：{item['title']}\n"
        news_text += f"来源：{item['source']}\n"
        if item.get("summary"):
            news_text += f"摘要：{item['summary']}\n"
        if item.get("content"):
            news_text += f"正文：{item['content'][:500]}\n"
        news_text += f"链接：{item['url']}\n"

    if not news_text.strip():
        news_text = "（今日暂未抓取到新闻，请根据近期保密热点生成）"

    # 钉钉 Markdown 链接格式: [文字](链接)
    prompt = f"""今天是{today.strftime('%Y年%m月%d日')} {weekday}。

以下是保密新闻素材：
{news_text}

请完成两项任务：

=== 任务一：行业早报 ===

严格按以下格式输出早报，不要有任何偏差：

🔐 **保密行业早报** | {today.strftime('%m月%d日')} {weekday}

📌 **今日要闻**

**1. 新闻标题**
[来源名称]
详细内容2-3句话，包括涉及的单位、具体事件、关键数据等，让读者不点链接也能了解核心信息。

**2. 新闻标题**
[来源名称]
详细内容2-3句话。

📰 **行业动态**

**3. 新闻标题** [来源名称]
一句话核心内容。

**4. 新闻标题** [来源名称]
一句话核心内容。

**5. 新闻标题** [来源名称]
一句话核心内容。

🔑 **关键词**：词1 | 词2 | 词3

📝 **编辑点评**：1-2句话点评今日态势。

要求：
- 今日要闻选最重要的1-2条，每条3-5句话详细展开
- 行业动态选3-5条，每条1-2句话
- 不要在早报中放任何链接URL（链接单独处理）
- 内容要基于素材中的正文来写，不要只重复标题

=== 任务二：选择题 ===

根据新闻内容生成6道保密知识单选题。
每题4个选项，1个正确答案，至少3题来自今日新闻。
每题附解析。

=== 输出格式 ===

严格按此JSON格式返回，不要代码块，不要多余文字：
{{"briefing": "早报markdown（不含链接URL）", "links": [{{"title": "新闻标题", "source": "来源", "url": "链接地址"}}], "questions": [{{"question": "题目？", "options": ["A. xx", "B. xx", "C. xx", "D. xx"], "answer": "A", "explanation": "解析"}}]}}"""

    try:
        raw = call_ai(prompt)
        print(f"  AI返回 {len(raw)} 字")

        cleaned = raw.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()

        m = re.search(r'\{[\s\S]*\}', cleaned)
        if m:
            cleaned = m.group()

        result = json.loads(cleaned)

        # 拼接最终早报：正文 + 链接区
        briefing = result.get("briefing", "")
        links = result.get("links", [])

        # 在早报末尾添加链接区
        if links:
            briefing += "\n\n---\n\n"
            briefing += "🔗 **原文链接**\n\n"
            for lk in links:
                t = lk.get("title", "")
                s = lk.get("source", "")
                u = lk.get("url", "")
                if t and u:
                    briefing += f"• [{t}]({u}) — {s}\n"
            briefing += "\n---\n"

        result["briefing"] = briefing
        return result

    except Exception as e:
        print(f"  AI生成失败: {e}")
        return generate_fallback(today, weekday, news_list)


def generate_fallback(today, weekday, news_list):
    """AI失败时的备用方案"""
    briefing = (
        f"🔐 **保密行业早报** | "
        f"{today.strftime('%m月%d日')} {weekday}\n\n"
    )

    if news_list:
        briefing += "📌 **今日要闻**\n\n"
        for i, item in enumerate(news_list[:6], 1):
            briefing += (
                f"**{i}. {item['title']}**\n"
                f"[{item['source']}]\n"
            )
            if item.get("summary"):
                briefing += f"{item['summary']}\n"
            briefing += "\n"

        briefing += "\n---\n\n🔗 **原文链接**\n\n"
        for i, item in enumerate(news_list[:6], 1):
            if item.get("url"):
                briefing += (
                    f"• [{item['title'][:25]}]({item['url']}) "
                    f"— {item['source']}\n"
                )
        briefing += "\n---\n"
    else:
        briefing += "今日暂未获取到新闻，请检查配置。\n"

    return {
        "briefing": briefing,
        "questions": [
            {
                "question": "涉密计算机连接互联网可能导致什么后果？",
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
    ts = str(round(time.time() * 1000))
    s = f"{ts}\n{SECRET}"
    h = hmac.new(
        SECRET.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(h))
    return f"{WEBHOOK}&timestamp={ts}&sign={sign}"


def send_markdown(title, content):
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


def send_to_dingtalk(briefing, questions):
    today = datetime.now().strftime("%m月%d日")

    # 推送早报
    print("  推送早报...")
    send_markdown("🔐 保密行业早报", briefing)

    time.sleep(2)

    # 推送选择题
    print("  推送选择题...")
    quiz = f"## 📝 保密知识测试 | {today}\n\n"
    quiz += "> 请先独立作答，答案见下方\n\n---\n\n"

    for i, q in enumerate(questions, 1):
        quiz += f"**第{i}题：{q['question']}**\n\n"
        for opt in q["options"]:
            quiz += f"　　{opt}\n"
        quiz += "\n"

    quiz += "\n---\n\n## 📋 答案与解析\n\n"
    for i, q in enumerate(questions, 1):
        quiz += f"**第{i}题：{q['answer']}**\n"
        quiz += f"> {q['explanation']}\n\n"

    send_markdown(f"📝 保密测试 {today}", quiz)


# =============================================
#               主程序
# =============================================

def main():
    print()
    print("=" * 55)
    print(f"  🔐 保密行业早报 v3.0（硅基流动版）")
    print(f"  模型: {SILICON_MODEL}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    print("\n[1/3] 抓取保密新闻...")
    news = fetch_all_news()

    print("\n[2/3] AI生成增强版早报...")
    result = generate_briefing_and_quiz(news)
    briefing = result.get("briefing", "")
    questions = result.get("questions", [])
    print(f"  早报 {len(briefing)} 字, 选择题 {len(questions)} 道")

    print("\n[3/3] 推送到钉钉...")
    send_to_dingtalk(briefing, questions)

    print("\n🎉 推送完成！")


if __name__ == "__main__":
    main()
