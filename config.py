"""
共享配置模块
"""
import os

# ============ 钉钉 Webhook（群消息推送） ============
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=e17adcd8cc53e1b0ad5fbf4ee5068e2f6f07f1978dab344863b760598c9a47cf")
DINGTALK_SECRET  = os.environ.get("DINGTALK_SECRET", "SEC9c363ba29c8f07aa7b0d844ebcca7e222379cef30605a570378d5076e90c99ea")

# ============ 钉钉企业应用（知识库操作） ============
DINGTALK_APP_KEY    = os.environ.get("DINGTALK_APP_KEY", "dingpxyyh6nk8korajmq")
DINGTALK_APP_SECRET = os.environ.get("DINGTALK_APP_SECRET", "o8I-2iW5XECLGS6MGxWMbaaqH4K_k40mTEgLrDJwMZd-m76NsUWglAskMtz7_Xo2")
DINGTALK_SPACE_ID   = os.environ.get("DINGTALK_SPACE_ID", "b6Vz6LODZkn7VmZ9")

# ============ 硅基流动 AI ============
SILICON_API_KEY  = os.environ.get("SILICON_API_KEY", "sk-hnhvcflnqfxtltspkvewybaqmooionihahrenoetzuwnynrm")
SILICON_BASE_URL = "https://api.siliconflow.cn/v1"
SILICON_MODEL    = "Qwen/Qwen2.5-72B-Instruct"

# ============ 保密关键词（用于过滤非相关内容） ============
BM_KEYWORDS = [
    "保密", "涉密", "密级", "泄密", "窃密",
    "定密", "解密", "密码", "加密", "机密",
    "秘密", "绝密", "国安", "国家安全",
    "保密法", "保密工作", "保密观", "脱密",
    "涉密人员", "涉密载体", "涉密文件",
    "涉密计算机", "涉密网络", "涉密信息系统",
    "网络安全", "信息安全", "数据安全",
    "保密审查", "保密检查", "保密培训",
    "保密资质", "保密制度", "保密管理",
]

# ============ 排除关键词（过滤时政等无关新闻） ============
EXCLUDE_KEYWORDS = [
    "习近平", "总书记", "出访", "会谈",
    "会见", "外交", "勋章", "仪式",
    "经济", "股市", "楼市", "体育",
    "娱乐", "明星", "综艺", "电影",
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
