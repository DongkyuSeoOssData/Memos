from PyQt6.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor

def apply_ios_shadow(widget: QWidget, blur: int = 24, offset_y: int = 4, alpha: int = 40) -> None:
    """플랫 사각형 디자인 - 그림자 효과 전면 비활성화"""
    widget.setGraphicsEffect(None)

