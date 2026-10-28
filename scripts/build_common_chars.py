"""Build hub/data/common_chars.txt (offline): every character used in knowledge/entries and cheat deflections,
the replacement phrases of hub/wording.py, a hand-written list of everyday characters, digits and punctuation.

No official education-ministry list ships with the repo, so this is the documented substitute.
Usage: python scripts/build_common_chars.py
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from hub.wording import REPLACEMENTS, REACTIONS  # noqa: E402

EVERYDAY = (
    "我你他她它牠們的了是不有在這那個什麼怎麼為會可以也都就很和跟但因所如果還要想看說聽問答吃喝睡玩走跑跳飛游爬坐站躺笑哭叫唱畫寫讀"
    "爸媽哥姐弟妹爺奶公婆家人孩子朋友老師學校同學寶貝大小多少長短高矮胖瘦快慢冷熱涼暖乾濕軟硬輕重亮暗新舊好壞對錯真假難易"
    "天地日月星雲風雨雪霜霧雷電光影山水火土木金石海河湖花草樹葉果籽根枝蟲魚鳥獸貓狗牛羊馬豬雞鴨鵝兔鼠蛇龜蛙蝶蜂蟻"
    "紅橙黃綠藍紫黑白灰粉棕色彩顏手腳頭臉眼耳口鼻嘴牙舌心肚背肩膝指毛皮骨血汗淚肉身體力氣聲音味道香臭甜酸苦辣鹹"
    "早晨午晚夜天春夏秋冬年月週今明昨前後上下左右裡外中間旁邊東西南北一二三四五六七八九十百千萬零第次些每種樣"
    "車船機門窗桌椅床燈鐘球書筆紙碗杯盤鍋刀叉衣褲帽鞋襪傘包盒瓶罐線針洗澡刷買賣送拿放開關推拉打吹抓摸聞嚐"
    "來去回進出到過起落變成像讓給把被從向往跟著先才又再已經正在快要一直永遠常常有時候只幾點分秒"
    "彈拐擠擠聚飛蟲營養格感覺幫忙小心危險安全媽猜猜哇耶嗯喔啊呀呢吧嗎呢哈"
)
PUNCT = "，。！？、；：「」『』（）…～—,.!?;:'\"()-0123456789"


def main():
    chars = set(EVERYDAY) | set(PUNCT)
    for f in glob.glob(str(ROOT / "knowledge" / "entries" / "*" / "*.json")):
        e = json.load(open(f, encoding="utf-8"))
        text = " ".join([e.get("first_sentence", ""), e.get("ask_back", ""), *e.get("facts", []), *e.get("labels", []),
                         *e.get("bridges", {}).values()])
        chars |= {c for c in text if ord(c) > 127}
    for f in glob.glob(str(ROOT / "knowledge" / "cheats" / "*.json")):
        c = json.load(open(f, encoding="utf-8"))
        chars |= set(c.get("deflection_zh", ""))
    for _, b in REPLACEMENTS:
        chars |= set(b)
    for r in REACTIONS:
        chars |= set(r)
    chars -= set(" \n\t")
    out = ROOT / "hub" / "data" / "common_chars.txt"
    out.parent.mkdir(exist_ok=True)
    s = "".join(sorted(chars))
    out.write_text("\n".join(s[i:i + 50] for i in range(0, len(s), 50)) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(chars)} characters)")


if __name__ == "__main__":
    main()
