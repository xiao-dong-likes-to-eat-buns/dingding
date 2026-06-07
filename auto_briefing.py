#!/usr/bin/env python3
"""
功能一：自动推送保密知识到钉钉群
- 从权威媒体抓取保密新闻
- AI 智能筛选（只保留涉密人员相关内容）
- 生成行业早报 + 5~8道选择题
- 推送到钉钉群
"""
import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import re
import random
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from config import *


# =============================================
#       AI 调用
# =============================================

def call_ai(system_prompt, user_prompt):
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": SILICON_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
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


def parse_ai_json(raw_text):
    """从AI返回中提取JSON"""
    cleaned = raw_text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    cleaned = cleaned.strip()
    m = re.search(r'\{[\s\S]*\}', cleaned)
    if m:
        return json.loads(m.group())
    raise ValueError("无法解析JSON")


# =============================================
#       新闻抓取
# =============================================

def fetch_baidu_news(keyword):
    news = []
    try:
        url = (
            "https://www.baidu.com/s?"
            "rtt=1&bsst=1&cl=2&tn=news&ie=utf-8"
            f"&word={urllib.parse.quote(keyword)}"
        )
        resp = requests.get(
            url, headers={"User-Agent": UA}, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
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
            summary = ""
            for cls in [
                "c-font-normal", "content-right", "c-abstract"
            ]:
                s = item.find("span", class_=re.compile(cls))
                if s:
                    summary = s.get_text(strip=True)
                    break
            source = "百度资讯"
            for cls in ["c-color-gray"]:
                s = item.find("span", class_=re.compile(cls))
                if s:
                    txt = s.get_text(strip=True)
                    if txt and 2 < len(txt) < 30:
                        source = txt
                        break
            news.append({
                "title": title,
                "summary": summary,
                "source": source,
                "url": a_tag.get("href", ""),
                "content": ""
            })
    except Exception as e:
        print(f"    百度[{keyword}]失败: {e}")
    return news


def fetch_gjbmj_filtered():
    news = []
    try:
        resp = requests.get(
            "http://www.gjbmj.gov.cn/",
            headers={"User-Agent": UA}, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if len(title) > 8:
                has_bm = any(kw in title for kw in BM_KEYWORDS)
                has_ex = any(kw in title for kw in EXCLUDE_KEYWORDS)
                if has_bm and not has_ex:
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
        print(f"    国保局失败: {e}")
    return news[:6]


def fetch_article_content(url, max_chars=500):
    try:
        if not url or not url.startswith("http"):
            return ""
        resp = requests.get(
            url, headers={"User-Agent": UA}, timeout=10
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        area = (
            soup.find("article")
            or soup.find(
                "div",
                class_=re.compile(
                    r"content|article|detail|body"
                    r"|rich_media_content|TRS_Editor"
                )
            )
            or soup.find(
                "div",
                id=re.compile(r"content|article|zoom")
            )
        )
        if area:
            for tag in area.find_all(
                ["script", "style", "nav", "footer", "header"]
            ):
                tag.decompose()
            text = area.get_text(separator="\n", strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text[:max_chars]
    except Exception:
        pass
    return ""


def fetch_all_news():
    all_news = []

    print("  [1/5] 百度资讯 - 保密案例通报...")
    all_news += fetch_baidu_news("保密 案例 通报 违规 涉密")
    time.sleep(random.randint(2, 4))

    print("  [2/5] 百度资讯 - 保密政策法规...")
    all_news += fetch_baidu_news("国家保密局 最新 规定 通知")
    time.sleep(random.randint(2, 4))

    print("  [3/5] 百度资讯 - 涉密人员管理...")
    all_news += fetch_baidu_news("涉密人员 保密管理 培训")
    time.sleep(random.randint(2, 4))

    print("  [4/5] 百度资讯 - 保密技术防范...")
    all_news += fetch_baidu_news("保密技术 网络安全 信息安全")
    time.sleep(random.randint(2, 4))

    print("  [5/5] 国家保密局官网...")
    all_news += fetch_gjbmj_filtered()

    # 去重
    seen = set()
    unique = []
    for item in all_news:
        key = item["title"][:20]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    print(f"  去重后共 {len(unique)} 条")

    # 抓取正文
    count = 0
    for item in unique:
        if count >= 5:
            break
        if item.get("url") and not item.get("content"):
            content = fetch_article_content(item["url"])
            if content and len(content) > 50:
                item["content"] = content
                count += 1
            time.sleep(random.randint(1, 2))

    return unique


# =============================================
#    AI 智能筛选 + 生成早报和选择题
# =============================================

def generate_briefing_and_quiz(news_list):
    today = datetime.now()
    wk = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"]
    weekday = wk[today.weekday()]

    news_text = ""
    for i, item in enumerate(news_list[:12], 1):
        news_text += f"\n--- 第{i}条 ---\n"
        news_text += f"标题：{item['title']}\n"
        news_text += f"来源：{item['source']}\n"
        if item.get("summary"):
            news_text += f"摘要：{item['summary']}\n"
        if item.get("content"):
            news_text += f"正文：{item['content'][:500]}\n"

    if not news_text.strip():
        news_text = "（暂未抓到新闻，请根据近期保密行业热点生成）"

    system_prompt = (
        "你是资深保密行业培训专家，专注于为涉密人员提供"
        "实用的保密知识和技能培训内容。"
        "只返回合法JSON，不要代码块。"
    )

    user_prompt = f"""今天是{today.strftime('%Y年%m月%d日')} {weekday}。

以下是从权威媒体抓取的保密相关新闻素材：
{news_text}

=== 筛选要求 ===

你必须严格筛选，只保留以下类型的内容（适合涉密人员学习）：
✅ 保密违规案例及处分通报
✅ 保密法律法规的最新解读和要求
✅ 涉密人员管理的政策和实务
✅ 涉密载体、涉密信息系统管理规定
✅ 保密技术防范知识和技能
✅ 保密检查和审查相关要求
✅ 保密培训和教育相关内容

必须排除以下内容：
❌ 领导人外事活动、政务新闻（即使来自保密局网站）
❌ 与保密工作无直接关系的政策
❌ 纯粹的宣传口号或表态性内容
❌ 过于久远的旧闻

如果筛选后没有合适的内容，请根据近期保密热点自拟一条实用知识。

=== 输出格式 ===

严格按此JSON格式返回：
{{"briefing": "早报markdown", "links": [{{"index": 1, "url": "链接", "source": "来源"}}], "questions": [{{"question": "题目？", "options": ["A. xx", "B. xx", "C. xx", "D. xx"], "answer": "A", "explanation": "解析"}}]}}

=== 早报格式 ===

🔐 **保密知识早报** | {today.strftime('%m月%d日')} {weekday}

📌 **今日精选**

**1. 标题**
[来源]
3-5句话详细介绍，让涉密人员了解核心要点、具体要求和实务建议。

**2. 标题**
[来源]
3-5句话详细介绍。

💡 **保密提醒**
结合今日内容，给涉密人员1条实用的工作建议。

🔑 **关键词**：词1 | 词2 | 词3

=== 选择题要求 ===
生成5-8道单选题，每题4选项，1个正确答案。
至少一半题目来自今日新闻，其余考察涉密人员必备知识。
每题附简短解析。"""

    try:
        raw = call_ai(system_prompt, user_prompt)
        print(f"  AI返回 {len(raw)} 字")
        result = parse_ai_json(raw)

        # 拼接链接区
        briefing = result.get("briefing", "")
        ai_links = result.get("links", [])
        url_map = {}
        for lk in ai_links:
            idx = lk.get("index")
            url = lk.get("url", "")
            if idx and url and url.startswith("http"):
                url_map[idx] = url
        for i, item in enumerate(news_list[:12], 1):
            if i not in url_map and item.get("url"):
                url_map[i] = item["url"]

        title_pattern = re.findall(
            r'\*\*(\d+)\.\s*(.+?)\*\*', briefing
        )
        if title_pattern:
            briefing += "\n\n---\n\n🔗 **参考链接**\n\n"
            for idx_str, title in title_pattern:
                idx = int(idx_str)
                url = url_map.get(idx, "")
                if url:
                    clean_t = title.strip()[:30]
                    briefing += f"• [{clean_t}]({url})\n"
            briefing += "\n---\n"

        result["briefing"] = briefing
        return result

    except Exception as e:
        print(f"  AI失败: {e}")
        return {
            "briefing": (
                f"🔐 **保密知识早报** | "
                f"{today.strftime('%m月%d日')} {weekday}\n\n"
                f"今日AI生成异常，请检查配置。\n\n"
                f"> 请关注「保密观」公众号获取保密知识。"
            ),
            "questions": [
                {
                    "question": "涉密计算机连接互联网可能导致什么？",
                    "options": [
                        "A. 无风险",
                        "B. 可能导致国家秘密泄露",
                        "C. 仅影响速度",
                        "D. 只会断网"
                    ],
                    "answer": "B",
                    "explanation": (
                        "涉密计算机连接互联网可能被植入木马，"
                        "导致涉密信息泄露。"
                    )
                }
            ]
        }


# =============================================
#            钉钉消息推送
# =============================================

def get_signed_url():
    ts = str(round(time.time() * 1000))
    s = f"{ts}\n{DINGTALK_SECRET}"
    h = hmac.new(
        DINGTALK_SECRET.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(h))
    return f"{DINGTALK_WEBHOOK}&timestamp={ts}&sign={sign}"


def send_markdown(title, content):
    url = get_signed_url()
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": content}
    }
    resp = requests.post(url, json=payload, timeout=10)
    res = resp.json()
    if res.get("errcode") == 0:
        print(f"    ✅ {title}")
    else:
        print(f"    ❌ {title}: {res}")


def send_quiz(questions):
    today = datetime.now().strftime("%m月%d日")
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
    print(f"  🔐 保密知识自动推送")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    print("\n[1/3] 抓取保密新闻...")
    news = fetch_all_news()

    print(f"\n[2/3] AI筛选 + 生成早报和选择题...")
    result = generate_briefing_and_quiz(news)
    briefing = result.get("briefing", "")
    questions = result.get("questions", [])
    print(f"  早报 {len(briefing)} 字, {len(questions)} 道题")

    print("\n[3/3] 推送到钉钉...")
    send_markdown("🔐 保密知识早报", briefing)
    time.sleep(2)
    send_quiz(questions)

    print("\n🎉 推送完成！")


if __name__ == "__main__":
    main()
