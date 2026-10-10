DARK_THEMES = {
    "dark":    {"name": "🌙 Charcoal Gray (기본 다크)",   "bg": "#0D0D0D", "card": "#141416", "input": "#1C1C1E", "text": "#F2F2F7", "border": "rgba(255, 255, 255, 0.14)", "icon": "#FFFFFF", "accent": "#0A84FF", "highlight_text": "#FFFFFF"},
    "nord":    {"name": "❄️ Nord Dark (북유럽 쿨그레이)", "bg": "#242933", "card": "#2E3440", "input": "#3B4252", "text": "#ECEFF4", "border": "rgba(236, 239, 244, 0.16)", "icon": "#ECEFF4", "accent": "#88C0D0", "highlight_text": "#FFFFFF"},
    "tokyo":   {"name": "🌌 Tokyo Night (미드나잇 네이비)","bg": "#16161E", "card": "#1A1B26", "input": "#24283B", "text": "#C0CAF5", "border": "rgba(192, 202, 245, 0.16)", "icon": "#C0CAF5", "accent": "#7AA2F7", "highlight_text": "#FFFFFF"},
    "dracula": {"name": "🧛 Dracula Dark (다크 흑연색)",   "bg": "#21222C", "card": "#282A36", "input": "#44475A", "text": "#F8F8F2", "border": "rgba(248, 248, 242, 0.16)", "icon": "#F8F8F2", "accent": "#BD93F9", "highlight_text": "#FFFFFF"},
    "mono":    {"name": "◼ Mono Graphite (미니멀 다크)",   "bg": "#0C0C0E", "card": "#151518", "input": "#1C1C20", "text": "#EDEDEF", "border": "rgba(237, 237, 239, 0.13)", "icon": "#EDEDEF", "accent": "#8B93FF", "highlight_text": "#FFFFFF"}
}

LIGHT_THEMES = {
    "white":   {"name": "☀️ Apple Pure White (클래식 화이트)", "bg": "#F2F2F7", "card": "#FFFFFF", "input": "#FFFFFF", "text": "#1C1C1E", "border": "rgba(0, 0, 0, 0.12)", "icon": "#1C1C1E", "accent": "#007AFF", "highlight_text": "#FFFFFF"},
    "ivory":   {"name": "📄 Warm Ivory (눈편한 웜 화이트)",    "bg": "#F9F8F6", "card": "#FFFFFF", "input": "#FFFFFF", "text": "#2C2A29", "border": "rgba(44, 42, 41, 0.14)", "icon": "#2C2A29", "accent": "#D97706", "highlight_text": "#FFFFFF"},
    "silver":  {"name": "❄️ Cool Silver (모던 실버 화이트)",   "bg": "#F1F5F9", "card": "#FFFFFF", "input": "#FFFFFF", "text": "#0F172A", "border": "rgba(15, 23, 42, 0.12)", "icon": "#0F172A", "accent": "#0284C7", "highlight_text": "#FFFFFF"},
    "mono":    {"name": "◻ Mono Paper (미니멀 화이트)",    "bg": "#FAFAFA", "card": "#FFFFFF", "input": "#FFFFFF", "text": "#18181B", "border": "rgba(24, 24, 27, 0.13)", "icon": "#18181B", "accent": "#4F46E5", "highlight_text": "#FFFFFF"}
}

def app_palette(settings: dict) -> tuple:
    """환경설정에서 고른 앱 색 테마와 다크 여부를 돌려줍니다. → (팔레트, is_dark)"""
    if settings.get("app_theme", "white") == "dark":
        return DARK_THEMES.get(settings.get("dark_theme_mode", "dark"), DARK_THEMES["dark"]), True
    return LIGHT_THEMES.get(settings.get("light_theme_mode", "white"), LIGHT_THEMES["white"]), False


def memo_palette(is_dark: bool) -> dict:
    """메모 창은 앱 테마가 아니라 메모 자신의 배경 밝기에 맞춘 기본 팔레트를 씁니다."""
    return DARK_THEMES["dark"] if is_dark else LIGHT_THEMES["white"]
