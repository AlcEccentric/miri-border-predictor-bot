"""Idol metadata for type 5 (anniversary) events.

Type 5 events run 52 idols in parallel (idol_id 1..52). For rendering we
split them into the four canonical MLTD groups (13 idols each) so each
generated image holds one group.

Each idol has a name, a short code, and a theme color. Card portraits are
fetched from matsurihi.me and cached locally; both are embedded into the
HTML as base64 data URIs at render time.
"""
import base64
import os
import urllib.request

# Local cache directory for downloaded card portraits, named "{idol_id}.png".
_ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "idols",
)

# Card portrait source. Format: {id zero-padded to 3}{short}0011_0_b.png
_CARD_URL = "https://storage.matsurihi.me/mltd/card/{id:03d}{short}0011_0_b.png"

# idol_id -> {name, short, color}
IDOLS = {
    1: {"name": "天海春香", "short": "har", "color": "#e22b30"},
    2: {"name": "如月千早", "short": "chi", "color": "#2743d2"},
    3: {"name": "星井美希", "short": "mik", "color": "#b4e04b"},
    4: {"name": "萩原雪歩", "short": "yuk", "color": "#d3dde9"},
    5: {"name": "高槻やよい", "short": "yay", "color": "#f39939"},
    6: {"name": "菊地真", "short": "mak", "color": "#515558"},
    7: {"name": "水瀬伊織", "short": "ior", "color": "#fd99e1"},
    8: {"name": "四条貴音", "short": "tak", "color": "#a6126a"},
    9: {"name": "秋月律子", "short": "rit", "color": "#01a860"},
    10: {"name": "三浦あずさ", "short": "azu", "color": "#9238be"},
    11: {"name": "双海亜美", "short": "ami", "color": "#ffe43f"},
    12: {"name": "双海真美", "short": "mam", "color": "#ffe43f"},
    13: {"name": "我那覇響", "short": "hib", "color": "#01adb9"},
    14: {"name": "春日未来", "short": "mir", "color": "#ea5b76"},
    15: {"name": "最上静香", "short": "siz", "color": "#6495cf"},
    16: {"name": "伊吹翼", "short": "tsu", "color": "#fed552"},
    17: {"name": "田中琴葉", "short": "kth", "color": "#92cfbb"},
    18: {"name": "島原エレナ", "short": "ele", "color": "#9bce92"},
    19: {"name": "佐竹美奈子", "short": "min", "color": "#58a6dc"},
    20: {"name": "所恵美", "short": "meg", "color": "#454341"},
    21: {"name": "徳川まつり", "short": "mat", "color": "#5abfb7"},
    22: {"name": "箱崎星梨花", "short": "ser", "color": "#ed90ba"},
    23: {"name": "野々原茜", "short": "aka", "color": "#eb613f"},
    24: {"name": "望月杏奈", "short": "ann", "color": "#7e6ca8"},
    25: {"name": "ロコ", "short": "roc", "color": "#fff03c"},
    26: {"name": "七尾百合子", "short": "yur", "color": "#c7b83c"},
    27: {"name": "高山紗代子", "short": "say", "color": "#7f6575"},
    28: {"name": "松田亜利沙", "short": "ari", "color": "#b54461"},
    29: {"name": "高坂海美", "short": "umi", "color": "#e9739b"},
    30: {"name": "中谷育", "short": "iku", "color": "#f7e78e"},
    31: {"name": "天空橋朋花", "short": "tom", "color": "#bee3e3"},
    32: {"name": "エミリースチュアート", "short": "emi", "color": "#554171"},
    33: {"name": "北沢志保", "short": "sih", "color": "#afa690"},
    34: {"name": "舞浜歩", "short": "ayu", "color": "#e25a9b"},
    35: {"name": "木下ひなた", "short": "hin", "color": "#d1342c"},
    36: {"name": "矢吹可奈", "short": "kan", "color": "#f5ad3b"},
    37: {"name": "横山奈緒", "short": "nao", "color": "#788bc5"},
    38: {"name": "二階堂千鶴", "short": "chz", "color": "#f19557"},
    39: {"name": "馬場このみ", "short": "kon", "color": "#f1becb"},
    40: {"name": "大神環", "short": "tam", "color": "#ee762e"},
    41: {"name": "豊川風花", "short": "fuk", "color": "#7278a8"},
    42: {"name": "宮尾美也", "short": "miy", "color": "#d7a96b"},
    43: {"name": "福田のり子", "short": "nor", "color": "#eceb70"},
    44: {"name": "真壁瑞希", "short": "miz", "color": "#99b7dc"},
    45: {"name": "篠宮可憐", "short": "kar", "color": "#b63b40"},
    46: {"name": "百瀬莉緒", "short": "rio", "color": "#f19591"},
    47: {"name": "永吉昴", "short": "sub", "color": "#aeb49c"},
    48: {"name": "北上麗花", "short": "rei", "color": "#6bb6b0"},
    49: {"name": "周防桃子", "short": "mom", "color": "#efb864"},
    50: {"name": "ジュリア", "short": "jul", "color": "#d7385f"},
    51: {"name": "白石紬", "short": "tmg", "color": "#ebe1ff"},
    52: {"name": "桜守歌織", "short": "kao", "color": "#274079"},
}

# Ordered list of (key, display name, member idol_ids).
IDOL_GROUPS = [
    {
        "key": "allstars",
        "name": "AllStars",
        "members": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
    },
    {
        "key": "princess",
        "name": "Princess",
        "members": [14, 17, 19, 21, 26, 27, 28, 29, 30, 32, 36, 37, 43],
    },
    {
        "key": "fairy",
        "name": "Fairy",
        "members": [15, 20, 25, 31, 33, 34, 38, 44, 46, 47, 49, 50, 51],
    },
    {
        "key": "angel",
        "name": "Angel",
        "members": [16, 18, 22, 23, 24, 35, 39, 40, 41, 42, 45, 48, 52],
    },
]

# Accent color per group (used for the image header).
GROUP_COLORS = {
    "allstars": "#e22b30",
    "princess": "#f74b9a",
    "fairy": "#19a2f0",
    "angel": "#f3c84b",
}


def idol_name(idol_id: int) -> str:
    info = IDOLS.get(idol_id)
    return info["name"] if info else f"アイドル{idol_id}"


def idol_color(idol_id: int) -> str:
    info = IDOLS.get(idol_id)
    return info["color"] if info else "#2980b9"


def idol_short(idol_id: int) -> str:
    info = IDOLS.get(idol_id)
    return info["short"] if info else "?"


def contrast_text_color(hex_color: str) -> str:
    """Return black or white depending on the luminance of hex_color, so
    text drawn on that color stays readable (some idol colors are very
    light, e.g. 雪歩 / 紬 / ロコ).
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "#ffffff"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    # Perceived luminance (sRGB approximation).
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#2c3e50" if luminance > 0.6 else "#ffffff"


def _cached_image_path(idol_id: int):
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = os.path.join(_ASSETS_DIR, f"{idol_id}{ext}")
        if os.path.exists(path):
            return path
    return None


def _download_card(idol_id: int):
    """Download the idol's card portrait to the local cache. Returns the
    cached path, or None on failure.
    """
    info = IDOLS.get(idol_id)
    if not info:
        return None

    url = _CARD_URL.format(id=idol_id, short=info["short"])
    os.makedirs(_ASSETS_DIR, exist_ok=True)
    dest = os.path.join(_ASSETS_DIR, f"{idol_id}.png")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "miri-border-predictor-bot"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
        return dest
    except Exception as e:
        print(f"WARNING: failed to download card for idol {idol_id}: {e}")
        return None


def idol_image_data_uri(idol_id: int):
    """Return a base64 data URI for the idol's card portrait, fetching and
    caching it from matsurihi.me if not already local. Returns None if the
    image is unavailable (renderer falls back to a colored placeholder).
    """
    path = _cached_image_path(idol_id) or _download_card(idol_id)
    if not path:
        return None

    ext = os.path.splitext(path)[1].lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "image/png")

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_idol_render(idol_id: int, rows):
    """Build the dict the HTML renderer expects for one idol."""
    color = idol_color(idol_id)
    return {
        "name": idol_name(idol_id),
        "short": idol_short(idol_id).upper(),
        "color": color,
        "text_color": contrast_text_color(color),
        "image_uri": idol_image_data_uri(idol_id),
        "rows": rows,
    }
