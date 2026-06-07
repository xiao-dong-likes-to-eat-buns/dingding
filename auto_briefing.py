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
#       AI 调用（带重试）
# =============================================

def call_ai(system_prompt, user_prompt):
    headers = {
        "Authorization": f"Bearer {SILICON_API_KEY}",
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
    for attempt in range(3):
        try:
            print(f"    AI请求第{attempt+1}次...")
            resp = requests.post(
                f"{SILICON_BASE_URL}/chat/completions",
                headers=headers, json=payload, timeout=120
            )
            print(f"    HTTP状态码: {resp.status_code}")
            if resp.status_code != 200:
                print(f"    响应: {resp.text[:300]}")
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"    第{attempt+1}次失败: {type(e).__name__}: {e}")
            if attempt < 2:
                time.sleep(5)
    raise RuntimeError("AI调用3次全部失败")


def parse_ai_json(raw_text):
    """从AI返回中提取JSON（多策略）"""
    cleaned = raw_text.strip()

    # 策略1: 去掉 markdown 代码块
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # 策略2: 找最外层 { ... }（非贪婪匹配第一个完整的JSON对象）
    # 先找第一个 { 和最后一个 } 的位置
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 策略3: 正则非贪婪匹配
    m = re.search(r'\{[^{}]*"briefing"[^{}]*\}', cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    # 策略4: 暴力正则
    m = re.search(r'\{[\s\S]*?\}(?=\s*$|\s*\n\n)', cleaned)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    # 策略5: 整段尝试
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    print(f"    JSON解析失败，原文前500字: {cleaned[:500]}")
    raise ValueError("无法解析JSON")


# =============================================
#       新闻抓取（多源 + RSS）
# =============================================

def fetch_rss_news(feed_url, source_name):
    """通过 RSS 抓取新闻（最稳定）"""
    news = []
    try:
        resp = requests.get(
            feed_url, headers={"User-Agent": UA}, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all("item") or soup.find_all("entry")
        for item in items[:6]:
            title_tag = item.find("title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if len(title) < 6:
                continue
            link_tag = item.find("link")
            url = ""
            if link_tag:
                url = link_tag.get("href", "") or link_tag.get_text(strip=True)
            desc_tag = item.find("description") or item.find("summary")
            summary = ""
            if desc_tag:
                summary_text = desc_tag.get_text(strip=True)
                summary = re.sub(r'<[^>]+>', '', summary_text)[:150]
            news.append({
                "title": title,
                "summary": summary,
                "source": source_name,
                "url": url,
                "content": ""
            })
    except Exception as e:
        print(f"    RSS[{source_name}]失败: {e}")
    return news


def fetch_bing_news(keyword):
    """从 Bing 资讯抓取"""
    news = []
    try:
        url = (
            "https://www.bing.com/news/search?"
            f"q={urllib.parse.quote(keyword)}"
            "&FORM=HDRSC7"
        )
        resp = requests.get(
            url, headers={"User-Agent": UA}, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 尝试多种选择器
        cards = (
            soup.find_all("div", class_=re.compile("news-card"))
            or soup.find_all("div", class_=re.compile("newsitem"))
            or soup.find_all("div", attrs={"data-t": True})
        )
        if not cards:
            # 最后尝试所有带标题链接的 div
            cards = soup.find_all("div", class_=re.compile("t_s"))

        for card in cards[:8]:
            a_tag = card.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if len(title) < 8:
                continue

            summary = ""
            for cls in ["snippet", "sk_body", "des"]:
                s = card.find("div", class_=re.compile(cls))
                if s:
                    summary = s.get_text(strip=True)[:150]
                    break

            source = "Bing资讯"
            for cls in ["source", "provider", "src"]:
                s = card.find("span", class_=re.compile(cls))
                if s:
                    source = s.get_text(strip=True)[:20]
                    break

            href = a_tag.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.bing.com" + href

            news.append({
                "title": title,
                "summary": summary,
                "source": source,
                "url": href,
                "content": ""
            })
    except Exception as e:
        print(f"    Bing[{keyword}]失败: {e}")
    return news


def fetch_sogou_news(keyword):
    """从搜狗新闻抓取"""
    news = []
    try:
        url = (
            "https://news.sogou.com/news?"
            f"query={urllib.parse.quote(keyword)}"
            "&sort=1"
        )
        resp = requests.get(
            url, headers={"User-Agent": UA}, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        items = soup.find_all("div", class_=re.compile("vrwrap|rb"))
        for item in items[:8]:
            a_tag = item.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            if len(title) < 8:
                continue
            # 注意：class_ 后面是单等号 =
            summary = ""
            des = item.find("p", class_="str_info")
            if des:
                summary = des.get_text(strip=True)[:100]
            news.append({
                "title": title,
                "summary": summary,
                "source": "搜狗新闻",
                "url": a_tag["href"],
                "content": ""
            })
    except Exception as e:
        print(f"    搜狗[{keyword}]失败: {e}")
    return news


def fetch_thepaper_news():
    """从澎湃新闻抓取"""
    news = []
    try:
        url = "https://www.thepaper.cn/searchResult?searchWord=%E4%BF%9D%E5%AF%86"
        resp = requests.get(
            url, headers={"User-Agent": UA}, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all("a", href=re.compile("newsDetail"))
        for item in items[:6]:
            title = item.get_text(strip=True)
            if len(title) > 8:
                href = item["href"]
                if not href.startswith("http"):
                    href = "https://www.thepaper.cn" + href
                news.append({
                    "title": title,
                    "summary": "",
                    "source": "澎湃新闻",
                    "url": href,
                    "content": ""
                })
    except Exception as e:
        print(f"    澎湃搜索失败: {e}")
    return news


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

    # RSS 源（最稳定，不被反爬）
    print("  [1/8] RSS - 保密观...")
    all_news += fetch_rss_news(
        "https://rsshub.app/wechat/ershicimi/5b98640b1389e47232386d36",
        "保密观"
    )
    time.sleep(1)

    print("  [2/8] RSS - 澎湃法治...")
    all_news += fetch_rss_news(
        "https://rsshub.app/thepaper/channel/25572",
        "澎湃新闻"
    )
    time.sleep(1)

    # Bing 搜索
    print("  [3/8] Bing - 保密案例通报...")
    all_news += fetch_bing_news("保密 案例 通报 违规 涉密")
    time.sleep(random.randint(2, 4))

    print("  [4/8] Bing - 保密政策法规...")
    all_news += fetch_bing_news("国家保密局 最新 规定 通知")
    time.sleep(random.randint(2, 4))

    print("  [5/8] Bing - 涉密人员管理...")
    all_news += fetch_bing_news("涉密人员 保密管理 培训")
    time.sleep(random.randint(2, 4))

    print("  [6/8] Bing - 保密技术防范...")
    all_news += fetch_bing_news("保密技术 网络安全 信息安全")
    time.sleep(random.randint(2, 4))

    print("  [7/8] 搜狗 - 保密...")
    all_news += fetch_sogou_news("保密 泄密 涉密 处分")
    time.sleep(random.randint(2, 4))

    print("  [8/8] 澎湃 - 保密...")
    all_news += fetch_thepaper_news()

    # 去重
    seen = set()
    unique = []
    for item in all_news:
        key = item["title"][:15]
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
        news_text += f"\n第{i}条：{item['title']}"
        if item.get("source"):
            news_text += f"（{item['source']}）"
        if item.get("summary"):
            news_text += f"\n摘要：{item['summary'][:200]}"
        if item.get("content"):
            news_text += f"\n正文：{item['content'][:300]}"
        news_text += "\n"

    if not news_text.strip():
        news_text = "暂未抓到新闻，请根据近期保密行业热点自拟内容。"

    system_prompt = "你是保密行业培训专家。只返回纯JSON，不要markdown代码块，不要任何多余文字。"

    user_prompt = f"""今天是{today.strftime('%Y年%m月%d日')} {weekday}。

新闻素材：
{news_text}

请基于以上素材生成保密知识早报和选择题。只保留与保密工作直接相关的新闻，排除政务新闻和无关内容。如果没有相关新闻就自拟。

只返回这个JSON格式，以{{开头，以}}结尾，不要任何其他文字：

{{
  "briefing": "用markdown格式写的早报，包含标题、今日精选2-3条新闻介绍、保密提醒、关键词",
  "questions": [
    {{"question": "题目", "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"], "answer": "A", "explanation": "解析"}}
  ]
}}

早报格式要求：
🔐 **保密知识早报** | {today.strftime('%m月%d日')} {weekday}

📌 **今日精选**

**1. 新闻标题**
[来源]
介绍内容3-5句话。

**2. 新闻标题**
[来源]
介绍内容3-5句话。

💡 **保密提醒**
给涉密人员1条实用工作建议。

🔑 **关键词**：词1 | 词2 | 词3

选择题：生成5-8道单选题，每题4选项，至少一半来自今日新闻，每题附解析。"""

    try:
        raw = call_ai(system_prompt, user_prompt)
        print(f"  AI返回 {len(raw)} 字")
        print(f"  AI原文前300字: {raw[:300]}")

        result = parse_ai_json(raw)

        if "briefing" not in result:
            raise ValueError("JSON缺少briefing字段")
        if "questions" not in result:
            result["questions"] = []

    
               # ========== 程序自动追加可点击的参考链接 ==========
        briefing = result.get("briefing", "")

        # 1. 从 briefing 中提取 **N. 标题**
        title_pattern = re.findall(r'\*\*(\d+)\.\s*(.+?)\*\*', briefing)

        # 2. 删除 AI 生成的旧参考链接区块
        lines = briefing.split("\n")
        clean_lines = []
        skip = False
        for line in lines:
            if "参考链接" in line:
                skip = True
                continue
            if skip and (line.strip().startswith("•") or line.strip() == "" or line.strip() == "---"):
                continue
            if skip and line.strip() != "":
                skip = False
            if not skip:
                clean_lines.append(line)
        briefing = "\n".join(clean_lines).rstrip()

        # 3. 用标题文字相似度匹配原始新闻URL（不用编号）
        if title_pattern:
            link_section = "\n\n---\n\n🔗 **参考链接**\n\n"
            has_link = False
            for idx_str, ai_title in title_pattern:
                ai_t = ai_title.strip()
                best_url = ""
                best_score = 0
                for item in news_list[:12]:
                    orig = item.get("title", "")
                    url = item.get("url", "")
                    if not orig or not url.startswith("http"):
                        continue
                    # 从长到短尝试匹配前N个字
                    for n in [20, 15, 10, 8, 6, 4]:
                        if ai_t[:n] in orig or orig[:n] in ai_t:
                            if n > best_score:
                                best_score = n
                                best_url = url
                            break
                if best_url:
                    link_section += f"• [{ai_t}]({best_url})\n"
                    has_link = True
                else:
                    link_section += f"• {ai_t}\n"
            link_section += "\n---\n"

            if has_link:
                briefing += link_section

        result["briefing"] = briefing
        return result



    except Exception as e:
        print(f"  AI失败: {type(e).__name__}: {e}")
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
                    "explanation": "涉密计算机连接互联网可能被植入木马，导致涉密信息泄露。"
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
