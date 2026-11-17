"""지도에서 그린 다각형(경도·위도) 면적 계산 (A-08). 병목 구간은 수십~수천 ㎡라 평면 근사로 충분함"""
import math

R = 6_371_008.8   # 지구 평균 반지름(m)


def polygon_area_m2(points: list[list[float]]) -> float:
    """points: [[경도, 위도], ...] (3개 이상, 닫지 않아도 됨) → ㎡"""
    if len(points) < 3:
        raise ValueError("꼭짓점이 3개 이상이어야 함")
    lat0 = math.radians(sum(p[1] for p in points) / len(points))
    xy = [(math.radians(lon) * R * math.cos(lat0), math.radians(lat) * R) for lon, lat in points]
    s = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]))
    return abs(s) / 2


def centroid(points: list[list[float]]) -> tuple[float, float]:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
