DOMAIN = "shenzhen_water"

CONF_CUSTOMER_CODE = "customer_code"
CONF_OPENID = "openid"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"

# ---------------------------------------------------------------------------
# “环水管家”小程序的通用参数：同一个深圳水务小程序对所有用户都一样，
# 所以写死在这里作为默认值。个人数据（OpenId / 户号）只走配置项。
# 来源：解包本机缓存的小程序包 wx987545bf02573f61（版本 203）核对过。
# ---------------------------------------------------------------------------

BASE_URL = "https://szgk.sz-water.com.cn"
MINI_PROGRAM_APPID = "wx987545bf02573f61"
MINI_PROGRAM_VERSION = "203"

# 小程序里的 globalData.tenantId
DEFAULT_TENANT_ID = "18a85453-ee3f-4cda-b3bf-7f6421319dcc"
# 小程序里硬编码的 Channel:"wxxcx"
DEFAULT_CHANNEL = "wxxcx"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 MiniProgramEnv/Mac "
    "MicroMessenger/7.0.20"
)

# 请求/响应加密：AES key = PREFIX + 04A52C9F[8:24] + SUFFIX
REQUEST_KEY_PREFIX = "CD3AA097"
REQUEST_KEY_SUFFIX = "CE92AD77"

# 单次请求超时（秒）
TIMEOUT = 20

# 默认轮询间隔（分钟），用户可在「配置」里改。水务账单更新很慢，默认 6 小时。
DEFAULT_UPDATE_INTERVAL_MINUTES = 360
MIN_UPDATE_INTERVAL_MINUTES = 30
MAX_UPDATE_INTERVAL_MINUTES = 1440

PLATFORMS = ["sensor"]


def mini_program_referer() -> str:
    """Return the Referer the mini program would send."""
    return (
        f"https://servicewechat.com/{MINI_PROGRAM_APPID}/"
        f"{MINI_PROGRAM_VERSION}/page-frame.html"
    )
