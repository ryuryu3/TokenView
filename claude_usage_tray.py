"""
Claude 사용량 트레이 (Windows 작업표시줄)

- 트레이 아이콘 숫자: 현재 5시간 세션 사용률(%) / 배경색: 초록<60, 노랑<85, 빨강
- 아이콘 아래 얇은 막대: 주간(7일) 사용률
- 마우스를 올리면 세션·주간 사용률과 리셋 시각 표시, 클릭하면 상세 메뉴
- 80% / 95% 도달 시 Windows 알림

데이터 출처: Claude Code가 저장한 OAuth 토큰(~/.claude/.credentials.json)으로
https://api.anthropic.com/api/oauth/usage 를 조회 (Claude Code의 /usage 와 같은 값).
※ 비공식 엔드포인트라 Anthropic 쪽 변경 시 동작이 멈출 수 있음.
"""

import datetime as dt
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

APP_NAME = "ClaudeUsageTray"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_PAGE = "https://claude.ai/settings/usage"
POLL_SECONDS = 300          # 5분마다 갱신
ALERT_LEVELS = (80, 95)     # 알림 기준(%)


# ---------------------------------------------------------------- 데이터
def credentials_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / ".credentials.json"


def read_token():
    """(accessToken, 만료여부) 반환. 파일이 없으면 FileNotFoundError."""
    data = json.loads(credentials_path().read_text(encoding="utf-8"))
    oauth = data.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    exp_ms = oauth.get("expiresAt")
    expired = bool(exp_ms) and dt.datetime.now().timestamp() * 1000 > exp_ms
    return token, expired


def fetch_usage(token: str) -> dict:
    r = requests.get(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "claude-usage-tray/1.0",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def parse_reset(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    # 소수점 이하 자릿수가 6자리를 넘으면 fromisoformat이 실패하므로 정리
    if "." in s:
        head, rest = s.split(".", 1)
        n = 0
        while n < len(rest) and rest[n].isdigit():
            n += 1
        frac, tz = rest[:n], rest[n:]
        s = f"{head}.{frac[:6]}{tz}"
    try:
        return dt.datetime.fromisoformat(s).astimezone()
    except ValueError:
        return None


def summarize(raw: dict) -> dict:
    """API 응답 → {'session': (pct, reset), 'weekly': (pct, reset), 'extra': [(label, pct, reset)]}"""
    def period(key):
        p = raw.get(key) or {}
        pct = p.get("utilization")
        return (None if pct is None else float(pct), parse_reset(p.get("resets_at")))

    labels = {"seven_day_opus": "주간 Opus", "seven_day_sonnet": "주간 Sonnet"}
    extra = []
    for k, v in raw.items():
        if k.startswith("seven_day_") and isinstance(v, dict) and v.get("utilization") is not None:
            extra.append((labels.get(k, k), float(v["utilization"]), parse_reset(v.get("resets_at"))))
    return {"session": period("five_hour"), "weekly": period("seven_day"), "extra": extra}


def until(t):
    if not t:
        return ""
    sec = int((t - dt.datetime.now().astimezone()).total_seconds())
    if sec <= 0:
        return "곧 리셋"
    h, m = divmod(sec // 60, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}일 {h}시간 후 리셋"
    return f"{h}시간 {m}분 후 리셋" if h else f"{m}분 후 리셋"


def fmt_pct(p):
    return "–" if p is None else f"{p:.0f}%"


# ---------------------------------------------------------------- 아이콘
def level_color(p):
    if p is None:
        return (120, 120, 120)
    if p < 60:
        return (46, 160, 67)
    if p < 85:
        return (210, 153, 0)
    return (207, 34, 46)


def load_font(size):
    for name in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def make_icon(session_pct, weekly_pct, error=False) -> Image.Image:
    S = 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=12,
                        fill=(90, 90, 90) if error else level_color(session_pct))

    text = "!" if error else ("--" if session_pct is None else str(min(int(round(session_pct)), 100)))
    size = {1: 50, 2: 44, 3: 32}.get(len(text), 30)
    font = load_font(size)
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((S - w) / 2 - box[0], (S - 12 - h) / 2 - box[1]), text, font=font, fill="white")

    # 주간 사용률 막대 (아래쪽)
    d.rectangle((6, S - 11, S - 7, S - 5), fill=(0, 0, 0, 90))
    if weekly_pct is not None and not error:
        x = 6 + (S - 13) * max(0.0, min(weekly_pct, 100.0)) / 100
        d.rectangle((6, S - 11, x, S - 5), fill="white")
    return img


# ---------------------------------------------------------------- 자동 실행
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command():
    if getattr(sys, "frozen", False):            # PyInstaller exe
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" "{Path(__file__).resolve()}"'


def autostart_enabled():
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on: bool):
    if os.name != "nt":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


# ---------------------------------------------------------------- 앱
class App:
    def __init__(self):
        import pystray  # 데스크톱 환경에서만 import
        self.pystray = pystray
        self.state = None
        self.error = "불러오는 중…"
        self.updated = None
        self.alerted = {}            # (구분, 리셋시각) -> 이미 알린 최고 단계
        self.wake = threading.Event()
        self.stop = threading.Event()

        M = pystray.MenuItem
        self.icon = pystray.Icon(
            APP_NAME,
            make_icon(None, None),
            "Claude 사용량",
            menu=pystray.Menu(
                M(lambda _: self.line("session"), None, enabled=False),
                M(lambda _: self.line("weekly"), None, enabled=False),
                M(lambda _: self.extra_line(), None, enabled=False,
                  visible=lambda _: bool(self.state and self.state["extra"])),
                M(lambda _: self.error or "", None, enabled=False, visible=lambda _: bool(self.error)),
                M(lambda _: f"갱신: {self.updated:%H:%M}" if self.updated else "갱신: –", None, enabled=False),
                pystray.Menu.SEPARATOR,
                M("지금 새로고침", lambda: self.wake.set(), default=True),
                M("사용량 페이지 열기", lambda: webbrowser.open(USAGE_PAGE)),
                M("Windows 시작 시 자동 실행", self.toggle_autostart,
                  checked=lambda _: autostart_enabled(), visible=os.name == "nt"),
                pystray.Menu.SEPARATOR,
                M("종료", self.quit),
            ),
        )

    # 메뉴 텍스트
    def line(self, key):
        name = "세션(5시간)" if key == "session" else "주간(7일)"
        if not self.state:
            return f"{name}: –"
        pct, reset = self.state[key]
        tail = f" · {until(reset)}" if reset else ""
        if key == "weekly" and reset:
            tail += f" ({reset:%m/%d %H:%M})"
        return f"{name}: {fmt_pct(pct)}{tail}"

    def extra_line(self):
        return " / ".join(f"{lbl} {fmt_pct(p)}" for lbl, p, _ in self.state["extra"])

    def tooltip(self):
        if self.error and not self.state:
            return f"Claude 사용량 – {self.error}"[:127]
        s_pct, s_reset = self.state["session"]
        w_pct, _ = self.state["weekly"]
        t = f"세션 {fmt_pct(s_pct)} ({until(s_reset) or '–'})\n주간 {fmt_pct(w_pct)}"
        if self.error:
            t += f"\n⚠ {self.error}"
        return t[:127]

    # 갱신
    def refresh(self):
        try:
            token, expired = read_token()
            if not token:
                raise RuntimeError("토큰 없음 – Claude Code 로그인 필요")
            try:
                raw = fetch_usage(token)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    raise RuntimeError("토큰 만료 – Claude Code를 한 번 실행하세요")
                raise
            self.state = summarize(raw)
            self.error = None
            self.updated = dt.datetime.now()
            self.check_alerts()
        except FileNotFoundError:
            self.error = "Claude Code 로그인 정보 없음"
        except requests.RequestException:
            self.error = "네트워크 오류 – 다음 주기에 재시도"
        except Exception as e:  # noqa: BLE001
            self.error = str(e)[:60]

        if self.state:
            self.icon.icon = make_icon(self.state["session"][0], self.state["weekly"][0])
        else:
            self.icon.icon = make_icon(None, None, error=True)
        self.icon.title = self.tooltip()
        self.icon.update_menu()

    def check_alerts(self):
        for key, name in (("session", "세션(5시간)"), ("weekly", "주간")):
            pct, reset = self.state[key]
            if pct is None:
                continue
            k = (key, reset.isoformat() if reset else "")
            done = self.alerted.get(k, 0)
            hit = max((lv for lv in ALERT_LEVELS if pct >= lv), default=0)
            if hit > done:
                self.alerted[k] = hit
                try:
                    self.icon.notify(f"{name} 사용량 {pct:.0f}% – {until(reset)}", "Claude 사용량")
                except Exception:  # noqa: BLE001
                    pass

    def loop(self, icon):
        icon.visible = True
        while not self.stop.is_set():
            self.refresh()
            self.wake.wait(POLL_SECONDS)
            self.wake.clear()

    def toggle_autostart(self, icon, item):
        set_autostart(not autostart_enabled())
        icon.update_menu()

    def quit(self, icon, item):
        self.stop.set()
        self.wake.set()
        icon.stop()

    def run(self):
        self.icon.run(setup=self.loop)


if __name__ == "__main__":
    App().run()
