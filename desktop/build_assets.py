"""Create the native app icon from code; no external image dependencies."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPainterPath
from PySide6.QtCore import Qt

app = QApplication([])
image = QImage(256,256,QImage.Format.Format_ARGB32); image.fill(Qt.GlobalColor.transparent)
p = QPainter(image); p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#3478ed')); p.drawRoundedRect(8,8,240,240,58,58)
path=QPainterPath(); path.moveTo(165,53); path.cubicTo(99,35,53,93,72,151); path.cubicTo(92,211,166,215,201,160); path.cubicTo(150,179,104,128,129,84); path.cubicTo(139,67,151,59,165,53); path.closeSubpath()
p.setBrush(QColor('#ffffff')); p.drawPath(path)
p.setPen(QPen(QColor('#d6e7ff'),7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap)); p.drawLine(187,53,187,81); p.drawLine(173,67,201,67); p.end()
target=Path(__file__).parent/'assets'; target.mkdir(exist_ok=True)
if not image.save(str(target/'moon.ico'),'ICO'): raise RuntimeError('ICO encoder unavailable')
