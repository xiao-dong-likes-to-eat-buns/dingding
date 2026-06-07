#!/usr/bin/env python3
"""
功能二：选定文章 → 自动排版 → 写入钉钉知识库 → 推送通知 + 选择题

使用方式：
  GitHub Actions workflow_dispatch 手动触发
  输入参数：文章URL + 可选标题

或通过云函数HTTP触发：
  POST https://xxx/api/article?url=https://xxx&title=xxx
"""
import sys
import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from config import *


# =============================================
#       AI 调用
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
        "temperature": 0.6,
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
    cleaned = raw_text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    m = re.search(r'\{[\s\S]*\}', cleaned)
    if m:
        return json.loads(m.group())
    raise ValueError("无法解析JSON")


# =============================================
#       文章抓取与解析
# =============================================

def fetch_full_article(url):
    """
    抓取文章完整内容
    """
    print(f"  抓取文章: {url[:60]}...")
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=15
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 提取标题
        title = ""
        for tag in [
            soup.find("h1"),
            soup.find("h2"),
            soup.find("title"),
        ]:
            if tag and len(tag.get_text(strip=True)) > 4:
                title = tag.get_text(strip=True)
                break

        # 提取正文
        content_area = (
            soup.find("article")
            or soup.find(
                "div",
                class_=re.compile(
                    r"content|article|detail|body"
                    r"|rich_media_content|TRS_Editor"
                    r"|post_content|entry-content"
                )
            )
            or soup.find(
                "div",
                id=re.compile(
                    r"content|article|zoom|js_content"
                )
            )
        )

        content = ""
        if content_area:
            for tag in content_area.find_all(
                ["script", "style", "nav", "footer",
                 "header", "aside"]
            ):
                tag.decompose()

            # 保留段落结构
            paragraphs = []
            for p in content_area.find_all(
                ["p", "h2", "h3", "h4", "li", "blockquote"]
            ):
                text = p.get_text(strip=True)
                if text and len(text) > 5:
                    paragraphs.append(text)

            if paragraphs:
                content = "\n\n".join(paragraphs)
            else:
                content = content_area.get_text(
                    separator="\n", strip=True
                )

        content = re.sub(r'\n{3,}', '\n\n', content)

        print(f"  标题: {title[:40]}")
        print(f"  正文: {len(content)} 字")

        return {
            "title": title,
            "content": content[:6000],
            "url": url
        }

    except Exception as e:
        print(f"  抓取失败: {e}")
        return None


# =============================================
#    AI 排版增强 + 选择题生成
# =============================================

def format_and_generate_quiz(article):
    """
    AI 将原始文章重排版为知识库格式，并生成选择题
    """
    print("  AI 排版增强 + 生成选择题...")

    system_prompt = (
        "你是保密培训专家兼文档编辑，擅长将原始文章"
        "整理成结构清晰、便于学习的培训材料。"
        "只返回合法JSON，不要代码块。"
    )

    user_prompt = f"""以下是一篇保密相关文章，请完成两项任务：

=== 原始文章 ===
标题：{article['title']}
来源：{article['url']}

正文：
{article['content'][:4000]}

=== 任务一：排版增强 ===

将文章整理成适合在钉钉知识库中阅读的格式，要求：

1. 标题层级清晰（用 ## 和 ### 分节）
2. 核心内容加粗标注
3. 保留原文的关键信息，不篡改事实
4. 在文末添加「📌 要点提炼」，用3-5个要点概括全文
5. 在文末添加「⚠️ 涉密人员须知」，结合内容给出1-2条实务建议
6. 整体格式适合手机阅读，段落不要太长

输出格式如下：
🔐 **[文章标题]**

📅 整理时间：今日日期
📎 原文来源：来源链接

---

[增强后的正文内容]

---

📌 **要点提炼**
1. xxx
2. xxx
3. xxx

⚠️ **涉密人员须知**
- xxx
- xxx

=== 任务二：选择题 ===

根据文章内容，生成5道单选题：
- 每题4个选项，1个正确答案
- 考察文章中的关键知识点
- 适合涉密人员保密培训
- 每题附解析

=== 输出格式 ===

严格按此JSON返回：
{{"formatted_article": "排版后的markdown全文", "questions": [{{"question": "题目？", "options": ["A. xx", "B. xx", "C. xx", "D. xx"], "answer": "A", "explanation": "解析"}}]}}"""

    try:
        raw = call_ai(system_prompt, user_prompt)
        print(f"  AI返回 {len(raw)} 字")
        return parse_ai_json(raw)
    except Exception as e:
        print(f"  AI处理失败: {e}")
        # 兜底：直接用原文
        today = datetime.now().strftime("%Y年%m月%d日")
        return {
            "formatted_article": (
                f"🔐 **{article['title']}**\n\n"
                f"📅 整理时间：{today}\n"
                f"📎 原文：[查看原文]({article['url']})\n\n"
                f"---\n\n{article['content'][:3000]}\n\n"
                f"---\n\n> AI排版失败，显示原文。"
            ),
            "questions": [
                {
                    "question": "涉密文件应如何保管？",
                    "options": [
                        "A. 放在办公桌上",
                        "B. 锁入保密柜",
                        "C. 带回家中",
                        "D. 交给同事保管"
                    ],
                    "answer": "B",
                    "explanation": (
                        "涉密文件应存放在符合保密要求的保密柜中，"
                        "不得随意放置。"
                    )
                }
            ]
        }


# =============================================
#    钉钉知识库 API
# =============================================

def get_dingtalk_token():
    """
    获取钉钉企业应用 access_token
    """
    print("  获取钉钉 access_token...")
    url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    payload = {
        "appKey": DINGTALK_APP_KEY,
        "appSecret": DINGTALK_APP_SECRET
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    token = data.get("accessToken", "")
    expire = data.get("expireIn", 0)
    print(f"  token获取成功，有效期 {expire}秒")
    return token


def create_wiki_document(token, title, content):
    """
    在钉钉知识库中创建文档
    """
    print(f"  写入知识库: {title[:30]}...")
    url = (
        f"https://api.dingtalk.com/v1.0/doc/spaces"
        f"/{DINGTALK_SPACE_ID}/nodes"
    )
    headers = {
        "x-acs-dingtalk-access-token": token,
        "Content-Type": "application/json"
    }

    # 钉钉知识库文档创建
    payload = {
        "nodeType": "DOC",
        "title": title,
        "body": content
    }

    try:
        resp = requests.post(
            url, headers=headers, json=payload, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        # 提取文档链接
        node_id = data.get("nodeId", "")
        doc_url = data.get("url", "")

        if not doc_url and node_id:
            doc_url = (
                f"https://alidocs.dingtalk.com"
                f"/i/nodes/{node_id}"
            )

        print(f"  ✅ 知识库文档已创建")
        print(f"  链接: {doc_url}")
        return doc_url

    except requests.exceptions.HTTPError as e:
        error_body = e.response.text if e.response else ""
        print(f"  ❌ 知识库创建失败: {e}")
        print(f"  响应: {error_body}")
        return ""
    except Exception as e:
        print(f"  ❌ 知识库创建异常: {e}")
        return ""


# =============================================
#    钉钉群消息推送
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


def send_kb_notification(article_title, doc_url, questions):
    """
    推送知识库更新通知 + 选择题
    """
    today = datetime.now().strftime("%m月%d日")

    # 推送通知
    notice = (
        f"## 📚 知识库更新通知\n\n"
        f"**新文章已入库：{article_title}**\n\n"
    )
    if doc_url:
        notice += f"🔗 [点击查看原文]({doc_url})\n\n"
    notice += (
        f"---\n\n"
        f"📅 更新时间：{today}\n\n"
        f"> 请涉密人员认真阅读，并完成下方测试题。"
    )
    send_markdown("📚 保密知识库更新", notice)
    time.sleep(2)

    # 推送选择题
    quiz = f"## 📝 知识库文章测试 | {today}\n\n"
    quiz += "> 阅读上方文章后作答，答案见下方\n\n---\n\n"

    for i, q in enumerate(questions, 1):
        quiz += f"**第{i}题：{q['question']}**\n\n"
        for opt in q["options"]:
            quiz += f"　　{opt}\n"
        quiz += "\n"

    quiz += "\n---\n\n## 📋 答案与解析\n\n"
    for i, q in enumerate(questions, 1):
        quiz += f"**第{i}题：{q['answer']}**\n"
        quiz += f"> {q['explanation']}\n\n"

    send_markdown(f"📝 文章测试 {today}", quiz)


# =============================================
#               主程序
# =============================================

def main():
    # 从环境变量或命令行参数获取文章URL
    article_url = os.environ.get("ARTICLE_URL", "")
    article_title_hint = os.environ.get("ARTICLE_TITLE", "")

    if not article_url and len(sys.argv) > 1:
        article_url = sys.argv[1]
    if not article_title_hint and len(sys.argv) > 2:
        article_title_hint = sys.argv[2]

    if not article_url:
        print("❌ 请提供文章URL！")
        print("用法: python article_to_kb.py <文章URL> [标题]")
        print("或设置环境变量 ARTICLE_URL")
        sys.exit(1)

    print()
    print("=" * 55)
    print(f"  📚 保密文章入库")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # 第一步：抓取文章
    print("\n[1/4] 抓取文章全文...")
    article = fetch_full_article(article_url)
    if not article:
        print("❌ 文章抓取失败，请检查URL")
        sys.exit(1)

    if article_title_hint:
        article["title"] = article_title_hint

    # 第二步：AI 排版 + 生成选择题
    print("\n[2/4] AI 排版增强 + 生成选择题...")
    result = format_and_generate_quiz(article)
    formatted = result.get("formatted_article", "")
    questions = result.get("questions", [])
    print(f"  排版后 {len(formatted)} 字, {len(questions)} 道题")

    # 第三步：写入钉钉知识库
    print("\n[3/4] 写入钉钉知识库...")
    doc_url = ""
    if DINGTALK_APP_KEY and DINGTALK_APP_SECRET and DINGTALK_SPACE_ID:
        try:
            token = get_dingtalk_token()
            doc_url = create_wiki_document(
                token,
                article["title"],
                formatted
            )
        except Exception as e:
            print(f"  ⚠️ 知识库写入失败: {e}")
            print("  将直接推送到群聊（不含知识库链接）")
    else:
        print("  ⚠️ 未配置知识库参数，跳过知识库写入")
        print("  如需知识库功能，请配置 DINGTALK_APP_KEY 等参数")

    # 第四步：推送通知 + 选择题
    print("\n[4/4] 推送群通知 + 选择题...")
    send_kb_notification(
        article["title"],
        doc_url,
        questions
    )

    print("\n🎉 文章入库完成！")


if __name__ == "__main__":
    import os
    main()
