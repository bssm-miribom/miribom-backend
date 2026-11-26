"""시간대별 방문 비율 표 만들기: 도시철도 시간대별 하차 실측 → app/citizen/time_profile.json

  python3 scripts/build_time_profile.py [--ai-dir ../miribom-ai]
입력: miribom-ai/data/raw/metro/busan_metro_hourly.csv (공공데이터포털 3057229 부산교통공사 시간대별 승하차, 커밋 안 함)
방법:
  1. 장소별 가까운 역(miribom_ai.alert.peak_share.STATIONS, places.csv peak_share와 같은 대응)의 하차 인원을 날짜·시간별로 합침
  2. 하루 하차 합으로 나눠 '그날 시간별 비율'을 구하고, 휴일(주말·공휴일)·평일로 나눠 시간별 중앙값을 냄 → 합이 1이 되게 다시 나눔
  3. 시간대(오전 09-12·점심 12-14·오후 14-18·저녁 18-22)마다
     share = 그 시간대 비율 합 (하루 방문객 중 그 시간대 도착 비중)
     peak_ratio = 그 시간대 가장 붐빈 1시간 비율 ÷ 09-22시 중 가장 붐빈 1시간 비율 (0~1, 가장 붐비는 시간대 = 1)
     (평일 07-09시는 출근 하차가 커서 기준에서 뺌)
한계: 역 하차 = 장소 방문이 아님(부산역 이용객·통근 섞임, 흰여울은 역이 없어 남포 대리). 도착 시각 기준이라 머무는 시간은 반영 안 함 [팀 확인]
"""
import argparse
import json
import sys
from pathlib import Path

import holidays
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SLOTS = {"morning": ("오전", 9, 12), "lunch": ("점심", 12, 14), "afternoon": ("오후", 14, 18), "evening": ("저녁", 18, 22)}


def hour_of(col: str) -> int:
    return int(col.split("시")[0]) % 24   # '24시-01시' → 0시


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai-dir", default=str(ROOT.parent / "miribom-ai"))
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.ai_dir) / "src"))
    from miribom_ai.alert.peak_share import STATIONS

    src = Path(a.ai_dir) / "data" / "raw" / "metro" / "busan_metro_hourly.csv"
    h = pd.read_csv(src, parse_dates=["date"])
    h = h[h["type"] == "하차"]
    cols = [c for c in h.columns if "시-" in c]
    hol = {pd.Timestamp(d) for d in holidays.KR(years=range(h.date.min().year, h.date.max().year + 1))}
    out = {"source": "공공데이터포털 3057229 부산교통공사 도시철도 역별 시간대별 승하차 (하차)",
           "period": [str(h.date.min().date()), str(h.date.max().date())],
           "method": "가까운 역 하차 인원의 날짜별 시간 비율 → 휴일·평일별 시간별 중앙값. "
                     "share=시간대 비율 합, peak_ratio=시간대 최대 1시간 ÷ 09-22시 최대 1시간",
           "slots": {k: {"label": v[0], "start": f"{v[1]:02d}:00", "end": f"{v[2]:02d}:00"} for k, v in SLOTS.items()},
           "places": {}}
    for place, st in STATIONS.items():
        g = h[h["station"].isin(st)].groupby("date")[cols].sum()
        g.columns = [hour_of(c) for c in g.columns]
        g = g[g.sum(axis=1) > 0]
        share = g.div(g.sum(axis=1), axis=0)
        rest = (share.index.dayofweek >= 5) | share.index.isin(hol)
        prof = {}
        for kind, mask in (("rest", rest), ("work", ~rest)):
            m = share[mask].median()
            m = m / m.sum()
            top = m[list(range(9, 22))].max()   # 09-22시 안 최대 (07-09시 출근 하차 제외)
            prof[kind] = {"days": int(mask.sum()), "peak_hour": int(m[list(range(9, 22))].idxmax()),
                          "slots": {k: {"share": round(float(m[list(range(s, e))].sum()), 3),
                                        "peak_ratio": round(float(m[list(range(s, e))].max() / top), 3)}
                                    for k, (_, s, e) in SLOTS.items()}}
        out["places"][place] = {"stations": st, **prof}
    dst = ROOT / "app" / "citizen" / "time_profile.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for p, v in out["places"].items():
        print(p, {k: (v[k]["peak_hour"], {s: (x["share"], x["peak_ratio"]) for s, x in v[k]["slots"].items()}) for k in ("rest", "work")})


if __name__ == "__main__":
    main()
