"""대응 점검표 기본 항목, 경보 알림 문안·발송(A-12, B-01), 안전 안내 문자 문안(A-13)

- 발송은 settings.notify_mode가 "dry_run"이면 기록만 남김 (시연 기본값). 실제 문자·카카오 발송은 업체 계약 뒤 send()만 바꾸면 됨 [팀 확인]
"""
import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import can_see
from app.core.config import settings
from app.auth.models import Account
from app.judge.models import DailyResult
from app.places.models import Place
from app.response.models import Contact, Notification

log = logging.getLogger("miribom.notify")

ALERT_STAGES = ("stage2", "stage3")   # 2단계부터 자동 발송
STAGE_NAME = {"stage1": "1단계", "stage2": "2단계", "stage3": "3단계", "pending": "판정 보류", "none": "대응 없음"}

# 단계별 점검표 기본 항목 (기능명세 A-10·B-03) [팀 확인]
CHECKLIST = {
    "stage1": [("watch", "현장 상황 모니터링"), ("route", "동선 안내 표지 준비")],
    "stage2": [("staff", "병목 통로 인력 배치 준비"), ("route", "동선 안내 표지 설치"), ("notice", "시민 공지 검토")],
    "stage3": [("staff", "병목 통로 인력 배치"), ("route", "동선 안내 표지 설치"), ("oneway", "일방통행 동선 운영"),
               ("close", "출입 통제 검토"), ("notice", "시민 공지·안전 안내 문자 검토")],
}


def checklist_items(level: str) -> list[dict]:
    return [{"id": i, "label": label, "done": False, "by": None, "at": None} for i, label in CHECKLIST.get(level, [])]


def _man(n: int | None) -> str:
    if n is None:
        return "-"
    return f"{n / 10000:.1f}만" if n >= 10000 else f"{n:,}"


def alert_text(row: dict, link: str) -> str:
    """대시보드 한 줄(PlaceRow) → 알림 문안. 예: [미리봄 3단계] 북항친수공원 · 내일 예상 4.2만~9.8만 명 · …"""
    d1 = row.get("d1") or {}
    parts = [f"[미리봄 {STAGE_NAME.get(row['stage'], row['stage'])}] {row['name']}"]
    if d1:
        parts.append(f"내일 예상 {_man(d1.get('low'))}~{_man(d1.get('high'))} 명")
        if d1.get("density_mid") is not None:
            parts.append(f"병목 1㎡당 {d1['density_mid']:.1f}명")
    if row.get("missing"):
        parts.append("빠진 자료: " + ", ".join(row["missing"]))
    parts.append(f"점검표: {link}")
    return " · ".join(parts)


def send(channel: str | None, to: str | None, text: str) -> str:
    """실제 발송 자리. 지금은 기록만 (dry_run)"""
    if settings.notify_mode != "send" or not channel or not to:
        return "dry_run" if channel else "no_contact"
    log.warning("실제 발송 수단이 아직 없음 (%s → %s)", channel, to)
    return "failed"


def _orgs_for(s: Session, place: Place) -> list[Account]:
    """그 장소를 볼 수 있는 협력 기관 계정 (부산시는 대시보드로 보므로 뺌)"""
    return [a for a in s.scalars(select(Account).where(Account.org_type != "city")) if can_see(a, place)]


def notify(s: Session, place: Place, judge_day: date, row: dict, orgs: list[Account], reason: str = "auto") -> list[Notification]:
    contacts = {c.org: c for c in s.scalars(select(Contact))}
    link = f"{settings.public_base_url}/admin/place/{place.id}?judge_day={judge_day}"
    text = alert_text(row, link)
    out = []
    for a in orgs:
        c = contacts.get(a.username)
        n = Notification(place_id=place.id, judge_day=judge_day, org=a.username, stage=row["stage"],
                         channel=c.channel if c else None, text=text, reason=reason,
                         status=send(c.channel if c else None, c.to if c else None, text))
        s.add(n)
        out.append(n)
    return out


def auto_notify(s: Session, result: DailyResult) -> int:
    """06시 판정 뒤 2단계 이상인 장소를 관할 기관에 알림. 같은 날 같은 단계로 이미 보냈으면 건너뜀"""
    from app.dashboard import views
    if result.replay:
        return 0
    city = s.scalars(select(Account).where(Account.org_type == "city")).first()
    rows = [x for x in views.dashboard(s, result, city)["places"] if x["stage"] in ALERT_STAGES] if city else []
    sent = 0
    for row in rows:
        place = s.get(Place, row["id"])
        done = {(n.org, n.stage) for n in s.scalars(select(Notification).where(
            Notification.place_id == place.id, Notification.judge_day == result.judge_day, Notification.reason == "auto"))}
        orgs = [a for a in _orgs_for(s, place) if (a.username, row["stage"]) not in done]
        sent += len(notify(s, place, result.judge_day, row, orgs))
    s.commit()
    return sent


def sms_draft(place: Place, row: dict | None) -> str:
    """안전 안내 문자 검토용 문안 (90자 안). 실제 발송은 부산시가 기존 체계로 함"""
    d1 = (row or {}).get("d1") or {}
    when = ""
    if d1.get("date"):
        dt = datetime.fromisoformat(d1["date"])
        when = f"{dt.month}.{dt.day}.({'월화수목금토일'[dt.weekday()]}) "
    text = f"[부산시] {place.name} {when}인파 밀집이 예상됩니다. 방문 자제, 대중교통 이용, 현장 안내에 따라 주시기 바랍니다."
    if len(text) > 90:
        text = f"[부산시] {place.name} {when}인파 밀집 예상. 방문 자제·대중교통 이용 바랍니다."
    return text[:90]
