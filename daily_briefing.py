#!/usr/bin/env python3
"""
保密行业早报 + AI选择题 每日钉钉推送
"""
import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import os
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup


# ============ 从环境变量读取配置 ============
WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=e17adcd8cc53e1b0ad5fbf4ee5068e2f6f07f1978dab344863b760598c9a47cf")
SECRET  = os.environ.get("DINGTALK_SECRET", "SEC9c363ba29c8f07aa7b0d844ebcca7e222379cef30605a570378d5076e90c99ea")
API_KEY = os.environ.get("AI_API_KEY", "sk-bb0a0e79a7f8412d9a9ab9a96545cac3")

# DeepSeek 配置
AI_URL   = "https://api.deepseek.com/v1/chat/completions"
AI_MODEL = "deepseek-chat"


# =============================================
#             新闻抓取模块
# =============================================

def fetch_sogou_weixin(keyword):
    """从搜狗微信搜索获取公众号文章"""
    news = []
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        }
        url = f"https://weixin.sogou.com/weixin?type=2&query={keyword}"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        articles = soup.find_all("div", class_="txt-box")
        for item in articles[:8]:
            a_tag = item.find("a")
            p_tag = item.find("p", class_="txt-info")
            if a_tag:
                news.append({
                    "title": a_tag.get_text(strip=True),
                    "summary": p_tag.get_text(strip=True) if p_tag else "",
                    "source": "保密观"
                })
    except Exception as e:
        print(f"    搜狗微信失败: {e}")
    return news


def fetch_gjbmj():
    """从国家保密局官网获取新闻标题"""
    news = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        resp = requests.get(
            "http://www.gjbmj.gov.cn/",
            headers=headers, timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if len(title) > 8:
                news.append({
                    "title": title,
                    "summary": "",
                    "source": "国家保密局"
                })
    except Exception as e:
        print(f"    国家保密局失败: {e}")
    return news[:10]


def fetch_all_news():
    """汇总所有来源"""
    print("  [1/3] 从搜狗微信搜索保密观...")
    all_news = fetch_sogou_weixin("保密观")

    print("  [1/3] 从搜狗微信搜索保密知识...")
    all_news += fetch_sogou_weixin("保密知识 国家安全")

    print("  [2/3] 从国家保密局官网...")
    all_news += fetch_gjbmj()

    # 去重
    seen = set()
    unique = []
    for item in all_news:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)

    print(f"  [3/3] 共获取 {len(unique)} 条不重复新闻")
    return unique


# =============================================
#         AI 生成早报 + 选择题
# =============================================

def call_ai(prompt):
    """调用 DeepSeek API"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是资深保密行业媒体编辑。只返回合法JSON，"
                    "不要用markdown代码块包裹，不要添加任何多余文字。"
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 4000
    }

    resp = requests.post(AI_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()

    # 清理可能的代码块标记
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text.strip())


def generate_briefing_and_quiz(news_list):
    """将新闻素材交给AI，生成早报+选择题"""
    today = datetime.now()
    weekday_names = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"]
    weekday = weekday_names[today.weekday()]

    # 拼接新闻素材
    news_text = ""
    for i, item in enumerate(news_list[:15], 1):
        news_text += f"{i}. [{item['source']}] {item['title']}\n"
        if item.get("summary"):
            news_text += f"   摘要：{item['summary']}\n"

    if not news_text.strip():
        news_text = "（今日暂未抓取到新闻，请根据保密行业热点生成内容）"

    prompt = f"""今天是{today.strftime('%Y年%m月%d日')} {weekday}。

以下是今天从权威媒体抓取的保密相关新闻素材：
{news_text}

请你完成以下两项任务：

## 任务一：行业早报
将以上新闻整理成「保密行业早报」，格式要求：
- 开头标题：🔐 保密行业早报 | {today.strftime('%m月%d日')} {weekday}
- 每条新闻一句话概括，标注来源，用序号列出
- 提炼2-3个「今日关键词」
- 如果新闻素材不足，可补充近期保密行业要闻
- 控制在400字以内

## 任务二：保密知识选择题
根据新闻内容和保密知识，生成6道单选题：
- 每题4个选项，1个正确答案
- 适合企业员工保密培训
- 每题附简短解析

严格按此JSON格式返回：
{{
  "briefing": "早报markdown全文",
  "questions": [
    {{
      "question": "题目？",
      "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"],
      "answer": "A",
      "explanation": "解析"
    }}
  ]
}}"""

    try:
        result = call_ai(prompt)
        return result
    except Exception as e:
        print(f"  AI生成失败: {e}")
        return {
            "briefing": (
                f"🔐 **保密行业早报** | {today.strftime('%m月%d日')} {weekday}\n\n"
                f"今日AI生成异常，请检查API配置。\n\n"
                f"💡 请关注「保密观」微信公众号获取最新资讯。"
            ),
            "questions": [
                {
                    "question": "涉密计算机连接互联网会带来什么风险？",
                    "options": [
                        "A. 无风险",
                        "B. 可能导致国家秘密泄露",
                        "C. 仅影响电脑速度",
                        "D. 只会影响网络信号"
                    ],
                    "answer": "B",
                    "explanation": "涉密计算机连接互联网可能导致木马入侵、数据窃取，造成泄密事故。"
                }
            ]
        }


# =============================================
#            钉钉消息推送
# =============================================

def get_signed_url():
    """生成带签名的钉钉Webhook地址"""
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
    """发送一条Markdown消息到钉钉群"""
    url = get_signed_url()
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": content
        }
    }
    resp = requests.post(url, json=payload, timeout=10)
    res = resp.json()
    if res.get("errcode") == 0:
        print(f"    ✅ {title} 推送成功")
    else:
        print(f"    ❌ {title} 推送失败: {res}")


def send_to_dingtalk(briefing, questions):
    """依次推送早报和选择题"""
    today = datetime.now().strftime("%m月%d日")

    # --- 推送早报 ---
    print("  推送早报...")
    send_markdown("🔐 保密行业早报", briefing)
    time.sleep(2)

    # --- 推送选择题 ---
    print("  推送选择题...")
    quiz_text = f"## 📝 保密知识测试 | {today}\n\n"
    quiz_text += "> 请先独立作答，答案在消息下方\n\n"
    quiz_text += "---\n\n"

    for i, q in enumerate(questions, 1):
        quiz_text += f"**第{i}题：{q['question']}**\n\n"
        for opt in q["options"]:
            quiz_text += f"{opt}\n"
        quiz_text += "\n"

    quiz_text += "---\n\n"
    quiz_text += "## 📋 答案与解析\n\n"

    for i, q in enumerate(questions, 1):
        quiz_text += f"**{i}. 答案：{q['answer']}**\n"
        quiz_text += f"> {q['explanation']}\n\n"

    send_markdown(f"📝 保密测试 {today}", quiz_text)


# =============================================
#               主程序入口
# =============================================

def main():
    print()
    print("=" * 50)
    print(f"  🔐 保密行业早报推送")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 第一步：抓取新闻
    print("\n[1/3] 从权威媒体抓取保密新闻...")
    news = fetch_all_news()

    # 第二步：AI 生成
    print("\n[2/3] 调用 DeepSeek AI 生成早报和选择题...")
    result = generate_briefing_and_quiz(news)
    briefing = result.get("briefing", "")
    questions = result.get("questions", [])
    print(f"  早报 {len(briefing)} 字, 选择题 {len(questions)} 道")

    # 第三步：推送钉钉
    print("\n[3/3] 推送到钉钉群...")
    send_to_dingtalk(briefing, questions)

    print("\n🎉 今日推送全部完成！")


if __name__ == "__main__":
    main()
