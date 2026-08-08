import sys
import re
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon
from PyQt6.QtCore import Qt, QRect, QByteArray
from PyQt6.QtSvg import QSvgRenderer

def main():
    app = QApplication(sys.argv)
    
    # Create 256x256 pixmap for the icon
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Draw white rounded background
    painter.setBrush(QColor("#FFFFFF"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 256, 256, 72, 72)
    
    # Read memo.svg
    svg_path = Path("icons") / "memo.svg"
    if not svg_path.exists():
        print("memo.svg not found.")
        return
        
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_data = f.read()
        
    # Recolor to black
    svg_data = re.sub(r'stroke="[^"]+"', 'stroke="#000000"', svg_data)
    if re.search(r'fill="#[0-9a-fA-F]{3,6}"', svg_data):
        svg_data = re.sub(r'fill="#[0-9a-fA-F]{3,6}"', 'fill="#000000"', svg_data)
    elif "stroke=" not in svg_data:
        svg_data = re.sub(r'<path(?![^>]*(?:stroke="none"|fill="none"))', '<path fill="#000000" ', svg_data)
        
    # Render SVG in the center (size 160x160 with 48px padding)
    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    from PyQt6.QtCore import QRectF
    renderer.render(painter, QRectF(48, 48, 160, 160))
    
    painter.end()
    
    # Save as memo.ico
    pixmap.toImage().save("icons/memo.ico")
    print("icons/memo.ico generated successfully.")

if __name__ == "__main__":
    main()
