"""Light desktop UI. All I/O jobs run outside the Qt event loop."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import traceback
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QRunnable, QObject, Signal, Slot, QThreadPool, QTimer, QTime, QSize, QLockFile, QSignalBlocker, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap, QLinearGradient, QShortcut, QKeySequence, QAction, QActionGroup
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFrame,
    QHBoxLayout, QVBoxLayout, QGridLayout, QStackedWidget, QLineEdit, QCheckBox, QTimeEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar,
    QScrollArea, QFileDialog, QSpinBox, QSystemTrayIcon, QMenu, QMessageBox, QAbstractSpinBox, QComboBox, QGraphicsOpacityEffect, QStyleOptionSpinBox, QStyleOptionButton, QStyle, QSlider)
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .core import Service, UserError, CHINA, now, legacy, ROOT, TASK_DESCRIPTION
from .appearance import Preferences, THEMES, WallpaperReader, palette, stylesheet, apply_native_palette, system_dark
from .notifications import EventNotifications
from .live_wallpaper import WallpaperCanvas, LiveWallpaper
from .accounts import StandardService
from . import updates
from .titlebar import TitleBar

BLUE = '#3478ed'
MUTED = '#7789a2'


def icon(name, color=BLUE, size=24):
    ratio = QApplication.primaryScreen().devicePixelRatio() if QApplication.instance() else 1
    pixmap = QPixmap(int(size * ratio), int(size * ratio)); pixmap.setDevicePixelRatio(ratio); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(QColor(color), 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name == 'moon':
        painter.drawArc(4, 3, 17, 18, 65 * 16, 285 * 16); painter.drawArc(10, 0, 14, 15, 130 * 16, 210 * 16); painter.drawLine(18, 4, 18, 8); painter.drawLine(16, 6, 20, 6)
    elif name == 'clock':
        painter.drawEllipse(3, 3, 18, 18); painter.drawLine(12, 7, 12, 12); painter.drawLine(12, 12, 16, 15)
    elif name == 'cloud':
        painter.drawArc(3, 9, 10, 11, 85 * 16, 185 * 16); painter.drawArc(7, 4, 12, 13, 0, 190 * 16); painter.drawArc(14, 9, 8, 11, -90 * 16, 190 * 16); painter.drawLine(8, 20, 18, 20)
    elif name == 'laptop':
        painter.drawRoundedRect(5, 4, 14, 13, 2, 2); painter.drawLine(2, 20, 22, 20); painter.drawLine(4, 17, 2, 20); painter.drawLine(20, 17, 22, 20)
    elif name == 'grid':
        for x, y in [(4, 4), (14, 4), (4, 14), (14, 14)]: painter.drawRoundedRect(x, y, 6, 6, 1, 1)
    elif name == 'logs':
        painter.drawRoundedRect(5, 3, 14, 18, 2, 2)
        for y in [8, 12, 16]: painter.drawLine(9, y, 15, y)
    elif name == 'check':
        painter.drawLine(5, 12, 10, 17); painter.drawLine(10, 17, 20, 6)
    elif name == 'user':
        painter.drawEllipse(8, 3, 8, 8); painter.drawArc(4, 12, 16, 14, 0, 180 * 16); painter.drawLine(4, 19, 20, 19)
    elif name == 'settings':
        for y, x in [(6, 8), (12, 16), (18, 10)]:
            painter.drawLine(3, y, 21, y); painter.setBrush(QColor('#ffffff')); painter.drawEllipse(x - 2, y - 2, 4, 4)
    elif name == 'shield':
        from PySide6.QtGui import QPainterPath
        path = QPainterPath(); path.moveTo(12, 3); path.lineTo(20, 6); path.lineTo(19, 15); path.quadTo(16, 20, 12, 22); path.quadTo(8, 20, 5, 15); path.lineTo(4, 6); path.closeSubpath(); painter.drawPath(path)
        painter.drawLine(8, 12, 11, 15); painter.drawLine(11, 15, 16, 9)
    else:
        painter.drawEllipse(5, 5, 14, 14); painter.drawLine(12, 8, 12, 16); painter.drawLine(8, 12, 16, 12)
    painter.end()
    return QIcon(pixmap)


def text(value='', style='Body', wrap=False):
    label = QLabel(value); label.setObjectName(style); label.setWordWrap(wrap)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def button(value, name=None, primary=False):
    result = QPushButton(value); result.setCursor(Qt.CursorShape.PointingHandCursor)
    result.setObjectName('Primary' if primary else 'Secondary'); result.setMinimumHeight(38)
    if name:
        result.setIcon(icon(name, '#ffffff' if primary else BLUE, 18)); result.setProperty('glyph',name)
    return result


def card():
    frame = QFrame(); frame.setObjectName('Card')
    layout = QVBoxLayout(frame); layout.setContentsMargins(24, 22, 24, 22); layout.setSpacing(12)
    return frame, layout


def icon_label(name,size):
    label=QLabel(); label.setProperty('glyph',name); label.setProperty('glyphSize',size)
    label.setPixmap(icon(name,BLUE,size).pixmap(size,size)); return label


STYLES = '''
QWidget { color:#24364f; font-family:"Microsoft YaHei UI","Segoe UI"; font-size:13px; }
QMainWindow,QWidget#Main { background:#f5f8fd; }
QLabel { background:transparent; }
QFrame#Card { background:#ffffff; border:1px solid #e3ebf5; border-radius:16px; }
QWidget#Sidebar { background:#ffffff; border-right:1px solid #e6edf6; }
QLabel#Eyebrow { color:#8e9db1; font-size:11px; letter-spacing:2px; }
QLabel#Heading { font-size:27px; font-weight:600; color:#243b5e; }
QLabel#Section { font-size:16px; font-weight:600; }
QLabel#Muted { color:#7789a2; font-size:12px; }
QLabel#Small { color:#8091a9; font-size:11px; }
QLabel#Time { color:#2c579b; font-size:59px; font-family:"Segoe UI"; font-weight:500; }
QLabel#Status { color:#2d496d; font-size:22px; font-weight:500; }
QLabel#Pill { background:#e9f6ef; color:#328a65; border-radius:7px; padding:5px 10px; font-size:11px; }
QLabel#PlanPill { min-height:22px; background:#e9f6ef; color:#328a65; border-radius:9px; padding:8px 16px; font-size:14px; font-weight:600; }
QLabel#PlanPill[health="ok"] { padding-left:36px; }
QLabel#Countdown { font-size:18px; font-weight:600; padding:10px 12px; border-radius:9px; min-height:28px; color:#2d496d; background:#edf4ff; }
QCheckBox#planEnabled { font-size:14px; font-weight:600; spacing:10px; }
QCheckBox#planEnabled::indicator { width:24px; height:24px; border-radius:6px; }
QLabel#Warning { background:#fff4df; color:#967027; border:1px solid #f5dfb1; border-radius:10px; padding:13px; }
QLabel#Notice { background:#edf4ff; color:#4c73ab; border:1px solid #dce8fb; border-radius:10px; padding:12px; }
QLabel#Error { background:#fff0f0; color:#b35459; border:1px solid #f2d8da; border-radius:10px; padding:12px; }
QPushButton { border:1px solid #dfe7f2; border-radius:9px; padding:8px 15px; background:#ffffff; color:#59718f; }
QPushButton:hover { background:#f0f5fd; border-color:#cbdaf0; }
QPushButton:pressed { background:#e8f0fd; }
QPushButton:disabled { color:#a7b3c4; background:#f0f3f8; border-color:#e6ebf2; }
QPushButton#Primary { background:#3478ed; color:#ffffff; border-color:#3478ed; font-weight:500; }
QPushButton#Primary:hover { background:#286be0; }
QPushButton#Primary:disabled { background:#abc6f6; border-color:#abc6f6; color:#ffffff; }
QPushButton#Nav { text-align:left; padding:13px 15px; background:transparent; border:0; color:#7d8da3; }
QPushButton#Nav:hover { background:#f3f7fd; }
QPushButton#Nav:checked { color:#3478ed; background:#eaf2ff; font-weight:500; }
QPushButton#Mode { text-align:left; padding:20px; border-radius:14px; min-height:92px; }
QPushButton#Mode:checked { background:#f3f7ff; border:1px solid #8fb4f3; color:#3478ed; }
QLineEdit,QSpinBox,QTimeEdit { background:#fbfcff; border:1px solid #dce6f4; border-radius:9px; padding:11px; selection-background-color:#bad2fb; color:#3f5b7e; }
QLineEdit:focus,QSpinBox:focus,QTimeEdit:focus { border:1px solid #6e9fec; }
QTimeEdit { font-size:31px; font-family:"Segoe UI"; min-height:53px; padding:9px 16px; }
QTimeEdit::up-button,QTimeEdit::down-button { width:22px; border:0; background:#edf4ff; }
QTimeEdit::up-button { border-top-right-radius:8px; }
QTimeEdit::down-button { border-bottom-right-radius:8px; }
QCheckBox { spacing:8px; color:#7186a2; }
QCheckBox::indicator { width:17px; height:17px; border:1px solid #cad9ed; border-radius:5px; background:#ffffff; }
QCheckBox::indicator:checked { background:#3478ed; border-color:#3478ed; }
QProgressBar { border:0; background:#e9eff9; border-radius:3px; max-height:5px; min-height:5px; }
QProgressBar::chunk { background:#7ea9f0; border-radius:3px; }
QTableWidget { background:#ffffff; border:0; gridline-color:#edf1f7; alternate-background-color:#fafcff; selection-background-color:#eaf2ff; }
QHeaderView::section { background:#f5f8fd; color:#8596af; border:0; padding:11px 8px; font-weight:400; }
QTableWidget::item { padding:8px; border:0; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { background:transparent; width:9px; margin:2px; }
QScrollBar::handle:vertical { background:#d6e1f0; border-radius:3px; min-height:28px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QMenu { background:#ffffff; border:1px solid #e2eaf5; padding:5px; }
QMenu::item { padding:8px 21px; }
QMenu::item:selected { background:#edf4ff; }
'''


class JobSignals(QObject):
    done = Signal(object)
    error = Signal(str)


class Job(QRunnable):
    def __init__(self, operation):
        super().__init__(); self.operation = operation; self.signals = JobSignals()

    def run(self):
        try: self.signals.done.emit(self.operation())
        except (UserError, ValueError, legacy.BusyError) as exc: self.signals.error.emit(str(exc))
        except Exception as exc:
            logging.error('Desktop job error type: %s', type(exc).__name__)
            self.signals.error.emit('操作未完成，请检查连接与权限后重试。')


class JobReceiver(QObject):
    """Give queued Python callbacks a persistent QObject on the UI thread."""
    def __init__(self, parent, complete, failed):
        super().__init__(parent); self.complete = complete; self.failed = failed

    @Slot(object)
    def done(self, value):
        self.complete(value)

    @Slot(str)
    def error(self, message):
        self.failed(message)


def connect_job(window, task, complete, failed):
    receiver = JobReceiver(window, complete, failed)
    task.signals.done.connect(receiver.done, Qt.ConnectionType.QueuedConnection)
    task.signals.error.connect(receiver.error, Qt.ConnectionType.QueuedConnection)
    window.jobs[id(task)] = (task, receiver)


def release_job(window, key):
    entry = window.jobs.pop(key, None)
    if entry: entry[1].deleteLater()


class Brand(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        p = getattr(self.window(), 'theme_colors', palette('light'))
        gradient = QLinearGradient(0, 0, self.width(), self.height()); gradient.setColorAt(0, QColor(p['bg'])); gradient.setColorAt(1, QColor(p['glow']))
        if getattr(self.window(),'preferences',None) and self.window().preferences.value['theme']=='wallpaper':painter.setOpacity(.6)
        painter.fillRect(self.rect(), gradient);painter.setOpacity(1)
        painter.setPen(QPen(QColor(p['border']), 1))
        x, y = self.width() / 2, self.height() * .34
        for radius in [86, 118, 151]: painter.drawEllipse(int(x-radius), int(y-radius), radius*2, radius*2)
        painter.end()


class StartupOverlay(QWidget):
    """Short non-blocking moon reveal; animation owns no account/network work."""
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName('StartupOverlay'); self.setGeometry(window.rect())
        self.setStyleSheet('QWidget#StartupOverlay {background:'+window.theme_colors['bg']+';}')
        layout=QVBoxLayout(self); layout.addStretch()
        moon=QLabel(); moon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        moon.setPixmap(icon('moon',window.theme_colors['accent_text'],80).pixmap(80,80)); layout.addWidget(moon)
        title=text('晚安助手','Heading'); title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addSpacing(20); layout.addWidget(title)
        caption=text('把每天，安排妥当。','Muted'); caption.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(caption); layout.addStretch()
        effect=QGraphicsOpacityEffect(self); self.setGraphicsEffect(effect)
        self.animation=QPropertyAnimation(effect,b'opacity',self); self.animation.setDuration(800)
        self.animation.setStartValue(0.0); self.animation.setKeyValueAt(.27,1.0); self.animation.setKeyValueAt(.64,1.0); self.animation.setEndValue(0.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.finished.connect(self.deleteLater)
        self.show(); self.raise_(); self.animation.start()


class ThemeCombo(QComboBox):
    def paintEvent(self,event):
        super().paintEvent(event)
        p=getattr(self.window(),'theme_colors',palette('light'))
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(p['muted']),1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        x,y=self.width()-15,self.height()//2
        painter.drawLine(x-3,y-2,x,y+1); painter.drawLine(x,y+1,x+3,y-2); painter.end()


class PlanPill(QLabel):
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('PlanPill')

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.property('health')!='ok':return
        colors=getattr(self.window(),'theme_colors',palette('light'))
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(colors['success']),2.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        x,y=17,self.height()//2
        painter.drawLine(x-5,y,x-1,y+4);painter.drawLine(x-1,y+4,x+6,y-5);painter.end()


class PlanCheckBox(QCheckBox):
    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.isChecked():return
        option=QStyleOptionButton();self.initStyleOption(option)
        rect=self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator,option,self)
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#ffffff'),2.6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        x,y=rect.center().x(),rect.center().y()
        painter.drawLine(x-6,y,x-2,y+4);painter.drawLine(x-2,y+4,x+6,y-5);painter.end()


class TimeEdit(QTimeEdit):
    def stepBy(self,steps):
        self.interpretText()
        factor=60 if self.currentSection()==QTimeEdit.Section.HourSection else 1
        current=self.time().hour()*60+self.time().minute()
        lower=self.minimumTime().hour()*60+self.minimumTime().minute()
        upper=self.maximumTime().hour()*60+self.maximumTime().minute()
        value=max(lower,min(upper,current+int(steps)*factor))
        section=self.currentSection();self.setTime(QTime(value//60,value%60));self.setCurrentSection(section)

    def stepEnabled(self):
        flags=QAbstractSpinBox.StepEnabledFlag.StepNone
        if self.time()<self.maximumTime():flags|=QAbstractSpinBox.StepEnabledFlag.StepUpEnabled
        if self.time()>self.minimumTime():flags|=QAbstractSpinBox.StepEnabledFlag.StepDownEnabled
        return flags

    def paintEvent(self,event):
        super().paintEvent(event)
        p=getattr(self.window(),'theme_colors',palette('light'))
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(p['muted']),1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        option=QStyleOptionSpinBox(); self.initStyleOption(option)
        for part,sign in [(QStyle.SubControl.SC_SpinBoxUp,-1),(QStyle.SubControl.SC_SpinBoxDown,1)]:
            center=self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox,option,part,self).center()
            x,y=center.x(),center.y()
            painter.drawLine(x-3,y-sign,x,y+sign); painter.drawLine(x,y+sign,x+3,y-sign)
        painter.end()


class Window(QMainWindow):
    runtime_error = Signal(str)

    def __init__(self, service):
        super().__init__()
        # Qt's offscreen test platform has no system font database on Windows.
        if not QFontDatabase.families():
            import os
            font_root = Path(os.environ.get('WINDIR','C:/Windows')) / 'Fonts'
            for name in ['msyh.ttc','msyhbd.ttc','segoeui.ttf']:
                if (font_root/name).exists(): QFontDatabase.addApplicationFont(str(font_root/name))
        self.service = service; self.standard=getattr(service,'edition',None)=='standard'; self.login_adding=False
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(2)
        self.preferences = Preferences(service.data); self.wallpaper_reader = WallpaperReader()
        self.transparency_preview=self.preferences.value['surface_transparency']
        self.transparency_render_timer=QTimer(self); self.transparency_render_timer.setSingleShot(True)
        self.transparency_render_timer.timeout.connect(self.apply_theme)
        self.transparency_save_timer=QTimer(self); self.transparency_save_timer.setSingleShot(True)
        self.transparency_save_timer.timeout.connect(self.flush_transparency)
        self.appearance_pool = QThreadPool(self); self.appearance_pool.setMaxThreadCount(1); self.wallpaper_reading=False
        self.update_pool = QThreadPool(self); self.update_pool.setMaxThreadCount(1)
        self.update_checking=False; self.update_release=None; self.update_notified_version=''
        self.event_notifications = EventNotifications(now()); self.wallpaper_source = '正在读取本机壁纸…'
        self.theme_combos = []; self.theme_colors = palette(self.preferences.value['theme'],self.preferences.value['accent'],self.preferences.value['wallpaper_dark'])
        self.jobs = {}; self.busy = False; self.rendering = False; self.authenticated = False; self.task_state = None; self.configuration_error=''; self.task_probe_error=''; self.remote_state = None; self.probing = False
        self.state = service.status(); self.controls = []; self.nav_buttons = []; self._quitting = False
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)
        self.setWindowTitle('晚安助手 · AHUT'); self.setWindowIcon(icon('moon')); self.resize(1180, 820); self.setMinimumSize(980, 690)
        self.wallpaper_canvas=WallpaperCanvas(); self.setCentralWidget(self.wallpaper_canvas)
        canvas_layout=QVBoxLayout(self.wallpaper_canvas);canvas_layout.setContentsMargins(0,0,0,0);canvas_layout.setSpacing(0)
        self.title_bar=TitleBar(self);canvas_layout.addWidget(self.title_bar)
        self.root_stack = QStackedWidget();canvas_layout.addWidget(self.root_stack)
        self.build_login(); self.build_main(); self.root_stack.setCurrentIndex(0); self.apply_theme(); self.refresh()
        self.refresh_timer = QTimer(self); self.refresh_timer.timeout.connect(self.refresh); self.refresh_timer.start(30_000)
        self.countdown_timer = QTimer(self); self.countdown_timer.timeout.connect(self.countdown); self.countdown_timer.start(1000)
        self.build_tray()
        self.live_wallpaper=LiveWallpaper(self,lambda:self.preferences.value['engine_path'])
        self.live_wallpaper.frame_ready.connect(self.wallpaper_canvas.set_frame)
        self.live_wallpaper.status_changed.connect(self.wallpaper_info.setText)
        QApplication.instance().aboutToQuit.connect(self.live_wallpaper.shutdown)
        self.event_timer=QTimer(self); self.event_timer.timeout.connect(self.poll_notifications); self.event_timer.start(5000)
        self.wallpaper_timer=QTimer(self); self.wallpaper_timer.timeout.connect(self.refresh_wallpaper); self.wallpaper_timer.start(20_000)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self.system_theme_changed)
        QTimer.singleShot(0,self.refresh_wallpaper)
        self.runtime_error.connect(self.recover_error, Qt.ConnectionType.QueuedConnection)
        self.task_timer = QTimer(self); self.task_timer.timeout.connect(self.probe_task); self.task_timer.start(60_000)
        QTimer.singleShot(100, self.probe_task)
        self.update_timer=QTimer(self); self.update_timer.setInterval(4*60*60*1000)
        self.update_timer.timeout.connect(self.auto_check_update); self.update_timer.start()
        self.update_start_timer=QTimer(self); self.update_start_timer.setSingleShot(True)
        self.update_start_timer.timeout.connect(self.auto_check_update); self.update_start_timer.start(8000)
        if self.state['configured'] and self.state['auto_login']:
            QTimer.singleShot(350, self.login_saved)

    def add_control(self, control):
        self.controls.append(control); return control

    def build_login(self):
        page = QWidget(); layout = QHBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        brand = Brand(); left = QVBoxLayout(brand); left.setContentsMargins(48, 35, 48, 35)
        logo_row = QHBoxLayout(); logo = icon_label('moon',27); logo_row.addWidget(logo); logo_row.addWidget(text('晚安助手', 'Section')); logo_row.addStretch(); left.addLayout(logo_row)
        left.addStretch(2); moon = icon_label('moon',90); moon.setAlignment(Qt.AlignmentFlag.AlignCenter); left.addWidget(moon); left.addSpacing(48)
        headline = text('把每天的签到，\n安排妥当。', 'LoginHeadline'); left.addWidget(headline)
        left.addSpacing(11); left.addWidget(text('两个账号，各自安排，从容切换。' if self.standard else '本机与云端，随需要自由切换。', 'Muted')); left.addStretch(2); left.addWidget(text('安徽工业大学 · 普通版 · 双账号' if self.standard else '安徽工业大学 · 个人晚寝签到助手', 'Small'))
        layout.addWidget(brand, 1)
        right = QWidget(); right.setObjectName('LoginRight'); rv = QVBoxLayout(right); rv.setContentsMargins(45, 35, 45, 35)
        theme_row=QHBoxLayout(); theme_row.addStretch(); theme_row.addWidget(self.theme_combo()); rv.addLayout(theme_row); rv.addStretch()
        form_widget = QWidget(); form_widget.setMinimumWidth(340); form_widget.setMaximumWidth(365); form = QVBoxLayout(form_widget); form.setContentsMargins(0, 0, 0, 0); form.setSpacing(10)
        form.addWidget(text('WELCOME BACK', 'Eyebrow')); form.addWidget(text('登录学校账号', 'Heading')); form.addWidget(text('使用安徽工业大学考勤系统账号', 'Muted')); form.addSpacing(27)
        form.addWidget(text('学号', 'Muted')); self.student_edit = QLineEdit(); self.student_edit.setObjectName('studentId'); self.student_edit.setPlaceholderText('请输入学号'); self.student_edit.setMaxLength(20); form.addWidget(self.student_edit)
        form.addSpacing(10); form.addWidget(text('考勤系统密码', 'Muted')); self.password_edit = QLineEdit(); self.password_edit.setObjectName('password'); self.password_edit.setEchoMode(QLineEdit.EchoMode.Password); form.addWidget(self.password_edit)
        self.default_password_hint=text('考勤系统默认密码为：Ahgydx@920','Small',True);form.addWidget(self.default_password_hint)
        self.auto_check = QCheckBox('下次自动验证已保存的账号'); self.auto_check.setChecked(self.state.get('auto_login', True)); form.addWidget(self.auto_check); form.addSpacing(16)
        self.login_button = self.add_control(button('验证并进入', 'check', True)); self.login_button.setObjectName('Primary'); self.login_button.clicked.connect(self.login); form.addWidget(self.login_button)
        self.login_error = text('', 'Error', True); self.login_error.hide(); form.addWidget(self.login_error)
        self.login_progress = QProgressBar(); self.login_progress.setRange(0, 0); self.login_progress.setTextVisible(False); self.login_progress.hide(); form.addWidget(self.login_progress)
        form.addWidget(text('凭据在本机加密保存，用于每日定时执行。\n登录仅验证账号，不会提交签到。', 'Small', True)); form.addSpacing(10)
        self.offline_button = button('离线查看已保存的配置'); self.offline_button.clicked.connect(self.enter_offline); self.offline_button.setVisible(self.state['configured']); form.addWidget(self.offline_button)
        self.login_update_status=text('','Small',True); self.login_update_status.hide(); form.addWidget(self.login_update_status)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(form_widget); row.addStretch(); rv.addLayout(row); rv.addStretch(); layout.addWidget(right, 1)
        self.password_edit.returnPressed.connect(self.login); self.student_edit.returnPressed.connect(lambda: self.password_edit.setFocus())
        if self.state['configured']:
            self.student_edit.setText(self.saved_student()); self.password_edit.setPlaceholderText('已加密保存，留空使用原密码')
        else: self.password_edit.setPlaceholderText('请输入考勤系统密码')
        self.root_stack.addWidget(page)

    def build_main(self):
        main = QWidget(); main.setObjectName('Main'); layout = QHBoxLayout(main); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        sidebar = QWidget(); sidebar.setObjectName('Sidebar'); sidebar.setFixedWidth(205); side = QVBoxLayout(sidebar); side.setContentsMargins(17, 30, 17, 22); side.setSpacing(8)
        brand = QHBoxLayout(); logo = icon_label('moon',30); brand.addWidget(logo); labels = QVBoxLayout(); labels.addWidget(text('晚安助手', 'Section')); labels.addWidget(text('每天，安排妥当', 'Small')); brand.addLayout(labels); brand.addStretch(); side.addLayout(brand); side.addSpacing(24)
        titles = [('签到概览', 'grid'), ('定时设置', 'clock'), ('执行端', 'cloud'), ('运行记录', 'logs'), ('账号管理' if self.standard else '账号与连接', 'settings'), ('外观与通知', 'moon')]
        for index, (title, glyph) in enumerate(titles):
            item = QPushButton(title); item.setObjectName('Nav'); item.setProperty('glyph',glyph); item.setIcon(icon(glyph, '#7e94b3', 19)); item.setCheckable(True); item.clicked.connect(lambda checked, i=index: self.go(i)); side.addWidget(item); self.nav_buttons.append(item)
            QShortcut(QKeySequence('Ctrl+' + str(index + 1)), self, activated=lambda i=index: self.go(i))
        side.addStretch(); self.account_badge = text('', 'Muted'); side.addWidget(self.account_badge)
        if self.standard:
            self.account_combo=self.add_control(QComboBox()); self.account_combo.setAccessibleName('当前考勤账号'); self.account_combo.currentIndexChanged.connect(self.select_account); side.addWidget(self.account_combo)
            add=self.add_control(button('添加账号', 'user')); add.clicked.connect(lambda:self.show_login(add=True)); side.addWidget(add); self.sidebar_add=add
        relogin = self.add_control(button('重新验证当前账号' if self.standard else '切换 / 验证账号', 'user')); relogin.clicked.connect(lambda:self.show_login()); side.addWidget(relogin); side.addWidget(text('凭据加密 · 北京时间', 'Small')); layout.addWidget(sidebar)
        content = QWidget(); cv = QVBoxLayout(content); cv.setContentsMargins(30, 25, 30, 15); cv.setSpacing(15)
        heading_row = QHBoxLayout(); heading_col = QVBoxLayout(); heading_col.setSpacing(3); heading_col.addWidget(text('AHUT · DORM CHECK-IN', 'Eyebrow')); self.page_heading = text('签到概览', 'Heading'); heading_col.addWidget(self.page_heading); self.page_subtitle = text('', 'Muted'); heading_col.addWidget(self.page_subtitle); heading_row.addLayout(heading_col); heading_row.addStretch(); heading_row.addWidget(self.theme_combo()); self.auth_badge = text('未联网验证', 'Pill'); heading_row.addWidget(self.auth_badge, alignment=Qt.AlignmentFlag.AlignVCenter); cv.addLayout(heading_row)
        self.migration_frame = QFrame(); self.migration_frame.setObjectName('Card'); migration_layout = QHBoxLayout(self.migration_frame); migration_layout.setContentsMargins(14, 10, 14, 10); migration_layout.addWidget(text('新版尚未接管。旧版任务保持原有安排。', 'Muted'), 1); self.takeover_button = self.add_control(button('接管本机计划', 'check', True)); self.takeover_button.clicked.connect(lambda: self.job('正在接管本机计划…', self.service.activate_local,plan_job=True)); migration_layout.addWidget(self.takeover_button); cv.addWidget(self.migration_frame)
        self.notice = text('', 'Notice', True); self.notice.hide(); cv.addWidget(self.notice)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setTextVisible(False); self.progress.hide(); cv.addWidget(self.progress)
        self.pages = QStackedWidget()
        for page in [self.overview(),self.schedule_page(),self.mode_page(),self.history_page(),self.settings_page(),self.appearance_page()]:
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); scroll.viewport().setAutoFillBackground(False); page.setAutoFillBackground(False); self.pages.addWidget(scroll)
        cv.addWidget(self.pages, 1)
        footer = QHBoxLayout(); self.status_text = text('本机界面可关闭，系统计划继续保留。', 'Small'); footer.addWidget(self.status_text, 1); footer.addWidget(text('Asia/Shanghai · 北京时间', 'Small')); cv.addLayout(footer); layout.addWidget(content, 1); self.root_stack.addWidget(main); self.go(0)

    def overview(self):
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(18)
        self.configuration_notice=text('', 'Error', True);self.configuration_notice.setVisible(False);outer.addWidget(self.configuration_notice)
        self.execution_feedback=text('', 'Warning', True);self.execution_feedback.setVisible(False);outer.addWidget(self.execution_feedback)
        self.repair_record_button=self.add_control(button('从成功日志修复本地记录','logs'))
        self.repair_record_button.setVisible(False);self.repair_record_button.clicked.connect(self.repair_records)
        outer.addWidget(self.repair_record_button,alignment=Qt.AlignmentFlag.AlignLeft)
        top = QHBoxLayout(); top.setSpacing(16)
        frame, box = card(); head = QHBoxLayout(); head.addWidget(text('下一次签到', 'Section')); head.addStretch(); self.plan_pill = PlanPill(); head.addWidget(self.plan_pill); box.addLayout(head)
        self.big_time = text('22:00', 'Time'); box.addWidget(self.big_time); self.next_label = text('', 'Muted'); box.addWidget(self.next_label); self.count_label = text('', 'Countdown', True); box.addWidget(self.count_label); box.addSpacing(5)
        end = QHBoxLayout(); self.executor_label = text('', 'Small'); end.addWidget(self.executor_label, 1); edit = button('调整时间', 'clock'); edit.clicked.connect(lambda: self.go(1)); end.addWidget(edit); box.addLayout(end); top.addWidget(frame, 3)
        today, tv = card(); tv.addWidget(text('今日状态', 'Section')); tv.addSpacing(7); clock = icon_label('clock',30); tv.addWidget(clock); self.today_status = text('', 'Status'); tv.addWidget(self.today_status); self.today_detail = text('', 'Muted', True); tv.addWidget(self.today_detail); tv.addStretch(); tv.addWidget(text('当天成功后跳过重复执行', 'Small')); top.addWidget(today, 2); outer.addLayout(top)
        if self.standard:
            summary,summary_box=card(); summary_box.addWidget(text('双账号计划', 'Section')); self.account_summary=text('', 'Muted', True); summary_box.addWidget(self.account_summary); outer.addWidget(summary)
        label = QHBoxLayout(); label.addWidget(text('运行模式', 'Section')); label.addStretch(); label.addWidget(text('普通版 · 本机执行' if self.standard else '手动切换 · 两端互斥', 'Small')); outer.addLayout(label)
        modes = QHBoxLayout(); self.quick_local = self.mode_button('本机运行', '电脑开机、联网并保持登录', 'laptop', 'local'); self.quick_cloud = self.mode_button('云端运行', '由 VPS 执行，电脑关机也可运行', 'cloud', 'cloud'); modes.addWidget(self.quick_local); modes.addWidget(self.quick_cloud); outer.addLayout(modes)
        if self.standard:self.quick_cloud.setText('VPS 云端运行\n后续付费版开放');self.quick_cloud.setEnabled(False)
        self.mode_hint = text('', 'Small', True); outer.addWidget(self.mode_hint)
        row = QHBoxLayout(); row.addWidget(text('最近运行', 'Section'), 1); logs = button('查看记录', 'logs'); logs.clicked.connect(lambda: self.go(3)); row.addWidget(logs); outer.addLayout(row)
        self.recent_label = text('暂时没有执行记录。', 'Muted', True); outer.addWidget(self.recent_label); outer.addStretch()
        return page

    def mode_button(self, title, description, glyph, mode):
        result = self.add_control(QPushButton(title + '\n' + description)); result.setObjectName('Mode'); result.setProperty('glyph',glyph); result.setIcon(icon(glyph, BLUE, 27)); result.setIconSize(QSize(27, 27)); result.setCheckable(True)
        result.clicked.connect(lambda: self.switch(mode)); return result

    def schedule_page(self):
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(17)
        frame, box = card(); header = QHBoxLayout(); label_col = QVBoxLayout(); label_col.addWidget(text('每天自动签到', 'Section')); label_col.addWidget(text('每天一个时间，统一使用北京时间。', 'Muted')); header.addLayout(label_col, 1); self.enabled_check = self.add_control(PlanCheckBox('启用计划')); self.enabled_check.setObjectName('planEnabled'); self.enabled_check.toggled.connect(self.toggle_enabled); header.addWidget(self.enabled_check); box.addLayout(header); box.addSpacing(18); box.addWidget(text('执行时间', 'Muted'))
        row = QHBoxLayout(); self.time_edit = TimeEdit(QTime(22, 0)); self.time_edit.setObjectName('scheduleTime'); self.time_edit.setDisplayFormat('HH:mm'); self.time_edit.setMinimumTime(QTime(21, 30)); self.time_edit.setMaximumTime(QTime(23, 30)); self.time_edit.setCurrentSection(QTimeEdit.Section.MinuteSection); self.time_edit.setMinimumWidth(210); self.time_edit.timeChanged.connect(self.schedule_dirty); row.addWidget(self.time_edit); row.addSpacing(10); self.save_time = self.add_control(button('保存并应用', 'check', True)); self.save_time.clicked.connect(self.apply_time); row.addWidget(self.save_time); row.addStretch(); box.addLayout(row)
        quick = QHBoxLayout()
        for value in ['21:40', '22:00', '22:10', '22:20']:
            item = button(value); item.clicked.connect(lambda checked=False, v=value: self.time_edit.setTime(QTime.fromString(v, 'HH:mm'))); quick.addWidget(item)
        quick.addStretch(); box.addLayout(quick); self.schedule_saved = text('', 'Small', True); box.addWidget(self.schedule_saved)
        box.addWidget(text('可设定北京时间 21:30–23:30；实际开放时段以学校系统为准。\n修改后同步系统任务与执行窗口，错过当天时间不会补交昨天的签到。', 'Notice', True)); outer.addWidget(frame)
        rules, rv = card(); rv.addWidget(text('执行规则', 'Section')); rv.addWidget(text(('• 两个账号各自设置时间、启用和暂停\n• 切换当前账号不会停止另一个账号的计划\n• 每个账号当天成功后跳过重复执行\n• 在各自设定时间起 15 分钟内执行，不跨日补签\n• 关闭界面后，本机系统任务继续保留' if self.standard else '• 同一天成功后跳过重复执行\n• 在设定时间起的 15 分钟内执行，不跨日补签\n• 备用端离线时显示“待同步”，启用它之前必须同步\n• 关闭界面不会停止系统计划；暂停计划才会停止自动执行'), 'Muted', True)); outer.addWidget(rules); outer.addStretch(); return page

    def mode_page(self):
        if self.standard:
            page=QWidget();outer=QVBoxLayout(page);outer.setContentsMargins(0,0,0,0);outer.setSpacing(17)
            self.detail_local=self.mode_button('本机运行','两个账号使用各自的 Windows 定时任务','laptop','local');outer.addWidget(self.detail_local)
            frame,box=card();box.addWidget(text('VPS 云端运行','Section'));box.addWidget(text('将在后续付费版开放。普通版的两个账号均在本机执行。','Muted',True))
            self.detail_cloud=button('暂未开放','cloud');self.detail_cloud.setCheckable(True);self.detail_cloud.setEnabled(False);box.addWidget(self.detail_cloud,alignment=Qt.AlignmentFlag.AlignLeft);outer.addWidget(frame)
            self.task_details=text('','Small',True);outer.addWidget(self.task_details);outer.addWidget(text('电脑需开机、联网，并保持 Windows 用户登录。退出界面不影响已启用的系统计划。','Notice',True));outer.addStretch();return page
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(17)
        row = QHBoxLayout(); self.detail_local = self.mode_button('本机运行', '使用 Windows 系统任务计划', 'laptop', 'local'); self.detail_cloud = self.mode_button('VPS 运行', '使用 Ubuntu 系统定时器', 'cloud', 'cloud'); row.addWidget(self.detail_local); row.addWidget(self.detail_cloud); outer.addLayout(row)
        frame, box = card(); box.addWidget(text('切换与预检', 'Section')); box.addWidget(text('检查账号与连接 → 停用原运行端 → 同步配置和成功记录 → 启用目标端', 'Muted', True)); self.connection_status = text('尚未检查 VPS 连接。', 'Notice', True); box.addWidget(self.connection_status)
        actions = QHBoxLayout(); self.check_button = self.add_control(button('检查 VPS 连接', 'cloud')); self.check_button.clicked.connect(self.check_vps); self.install_button = self.add_control(button('安装 / 更新备用端', 'settings')); self.install_button.clicked.connect(lambda: self.job('正在安装 VPS 备用服务，可能需要几分钟…', self.service.deploy_remote, self.connection_result)); actions.addWidget(self.check_button); actions.addWidget(self.install_button); actions.addStretch(); box.addLayout(actions); outer.addWidget(frame)
        outer.addWidget(text('连接中断或状态未知时，本机会保持停用。恢复连接后，可重试切换或切回本机。\n首次运行请先接管本机计划，再安装或更新备用端。', 'Warning', True)); self.task_details = text('', 'Small', True); outer.addWidget(self.task_details); outer.addStretch(); return page

    def history_page(self):
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(14)
        toolbar = QHBoxLayout(); self.log_filter = QLineEdit(); self.log_filter.setPlaceholderText('搜索执行记录或失败说明'); self.log_filter.textChanged.connect(self.render_history); toolbar.addWidget(self.log_filter, 1); refresh = button('刷新', 'logs'); refresh.clicked.connect(self.render_history); toolbar.addWidget(refresh); folder = button('打开日志目录'); folder.clicked.connect(self.open_data); toolbar.addWidget(folder); outer.addLayout(toolbar)
        self.history_table = QTableWidget(0, 4); self.history_table.setHorizontalHeaderLabels(['北京时间', '事件', '运行端', '说明']); self.history_table.verticalHeader().hide(); self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.history_table.setAlternatingRowColors(True); self.history_table.setShowGrid(False); self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch); self.history_table.setColumnWidth(0, 157); self.history_table.setColumnWidth(1, 90); self.history_table.setColumnWidth(2, 75); outer.addWidget(self.history_table, 1)
        self.empty_history = text('没有匹配的记录。首次执行后将显示学校确认的结果。', 'Muted'); outer.addWidget(self.empty_history)
        remote = self.add_control(button('读取 VPS 运行记录', 'cloud')); remote.clicked.connect(lambda: self.job('正在读取 VPS 记录…', lambda: self.service.rpc('history'), self.remote_history)); remote.setVisible(not self.standard);outer.addWidget(remote, alignment=Qt.AlignmentFlag.AlignLeft); return page

    def settings_page(self):
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(15)
        if self.standard:
            frame,box=card();box.addWidget(text('普通版 · 双账号','Section'));box.addWidget(text('最多同时保存两个学校账号。新增账号验证成功后，默认暂停计划。','Muted',True))
            self.account_management=text('','Muted',True);box.addWidget(self.account_management)
            actions=QHBoxLayout();self.add_account_button=self.add_control(button('添加账号','user',True));self.add_account_button.clicked.connect(lambda:self.show_login(add=True));actions.addWidget(self.add_account_button)
            verify=self.add_control(button('重新验证当前账号','check'));verify.clicked.connect(lambda:self.show_login());actions.addWidget(verify)
            self.remove_account_button=self.add_control(button('移除当前账号'));self.remove_account_button.clicked.connect(self.remove_current_account);actions.addWidget(self.remove_account_button);actions.addStretch();box.addLayout(actions);outer.addWidget(frame)
            frame,box=card();box.addWidget(text('本机加密保存','Section'));box.addWidget(text('两个账号的凭据、每日计划和成功记录分别保存。切换查看不会暂停任何账号，也不会立即提交签到。','Muted',True));outer.addWidget(frame)
            self.settings_account=text('','Small');outer.addWidget(self.settings_account);outer.addStretch();return page
        account, av = card(); av.addWidget(text('学校考勤账号', 'Section')); self.settings_account = text('', 'Muted'); av.addWidget(self.settings_account); relogin = button('重新验证 / 更换账号', 'user'); relogin.clicked.connect(self.show_login); av.addWidget(relogin, alignment=Qt.AlignmentFlag.AlignLeft); outer.addWidget(account)
        connection, cv = card(); cv.addWidget(text('备用 VPS 连接', 'Section')); grid = QGridLayout(); grid.setHorizontalSpacing(14); grid.setVerticalSpacing(10)
        self.host_edit = QLineEdit(); self.port_edit = QSpinBox(); self.port_edit.setRange(1, 65535); self.user_edit = QLineEdit('root'); self.key_edit = QLineEdit()
        grid.addWidget(text('SSH 地址', 'Muted'), 0, 0); grid.addWidget(text('端口', 'Muted'), 0, 1); grid.addWidget(self.host_edit, 1, 0); grid.addWidget(self.port_edit, 1, 1); grid.addWidget(text('用户名', 'Muted'), 2, 0); grid.addWidget(self.user_edit, 3, 0); grid.addWidget(text('SSH 私钥文件', 'Muted'), 4, 0, 1, 2); grid.addWidget(self.key_edit, 5, 0)
        choose = button('选择文件'); choose.clicked.connect(self.choose_key); grid.addWidget(choose, 5, 1); cv.addLayout(grid)
        save = self.add_control(button('保存连接', 'check', True)); save.clicked.connect(self.save_connection); cv.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft); cv.addWidget(text('请填写自己的 SSH 地址；切换或修改远端计划时需保持连接可用。\n凭据仅通过验证服务器身份的 SSH 连接同步，不会上传到 GitHub。', 'Small', True)); outer.addWidget(connection); outer.addStretch()
        try:
            value = self.service.connection(); self.host_edit.setText(value['host']); self.port_edit.setValue(int(value['port'])); self.user_edit.setText(value['user']); self.key_edit.setText(value['key'])
        except Exception: self.port_edit.setValue(22)
        return page

    def theme_combo(self):
        combo=ThemeCombo(); combo.setAccessibleName('界面主题'); combo.setToolTip('切换界面主题')
        for key,label in THEMES.items(): combo.addItem(label,key)
        combo.setCurrentIndex(list(THEMES).index(self.preferences.value['theme']))
        combo.currentIndexChanged.connect(lambda index:self.set_theme(combo.itemData(index)))
        self.theme_combos.append(combo); return combo

    def appearance_page(self):
        page=QWidget(); outer=QVBoxLayout(page); outer.setContentsMargins(0,0,0,0); outer.setSpacing(16)
        frame,box=card(); box.addWidget(text('让界面，贴合你的桌面。','Section'))
        box.addWidget(text('主题即时生效，重新打开后保留选择。','Muted')); box.addWidget(self.theme_combo(),alignment=Qt.AlignmentFlag.AlignLeft)
        transparency_row=QHBoxLayout(); transparency_row.addWidget(text('卡片与侧栏透明度','Section')); transparency_row.addStretch()
        self.transparency_value=text(str(self.transparency_preview)+'%','Muted'); transparency_row.addWidget(self.transparency_value); box.addLayout(transparency_row)
        self.transparency_slider=QSlider(Qt.Orientation.Horizontal); self.transparency_slider.setAccessibleName('壁纸模式卡片与侧栏透明度')
        self.transparency_slider.setRange(0,100); self.transparency_slider.setSingleStep(1); self.transparency_slider.setPageStep(10)
        self.transparency_slider.setValue(self.transparency_preview); self.transparency_slider.setMinimumHeight(28)
        self.transparency_slider.valueChanged.connect(self.preview_transparency); self.transparency_slider.sliderReleased.connect(self.flush_transparency)
        box.addWidget(self.transparency_slider)
        ends=QHBoxLayout(); ends.addWidget(text('0% · 不透明','Small')); ends.addStretch(); ends.addWidget(text('100% · 背景透明','Small')); box.addLayout(ends)
        self.transparency_hint=text('','Small',True); box.addWidget(self.transparency_hint)
        self.transparency_reset=button('恢复默认 · 14%'); self.transparency_reset.clicked.connect(self.reset_transparency); box.addWidget(self.transparency_reset,alignment=Qt.AlignmentFlag.AlignLeft)
        self.wallpaper_info=text(self.wallpaper_source,'Notice',True); box.addWidget(self.wallpaper_info)
        box.addWidget(text('跟随 Wallpaper Engine 主显示器选择同一项目，在程序背景独立动态播放，动画进度可能不同。关闭、最小化或切到其他主题时释放播放器；不截取其他应用，不上传画面。','Small',True))
        engine_row=QHBoxLayout(); self.engine_edit=QLineEdit(self.preferences.value['engine_path']); self.engine_edit.setPlaceholderText('Wallpaper Engine 安装目录（留空自动查找）'); self.engine_edit.setReadOnly(True); engine_row.addWidget(self.engine_edit,1)
        choose=button('选择目录'); choose.clicked.connect(self.choose_engine); engine_row.addWidget(choose)
        reset=button('自动查找'); reset.clicked.connect(lambda:self.save_engine('')); engine_row.addWidget(reset); box.addLayout(engine_row)
        reread=button('重新加载当前动态壁纸','moon'); reread.clicked.connect(self.reload_live_wallpaper); box.addWidget(reread,alignment=Qt.AlignmentFlag.AlignLeft); outer.addWidget(frame)
        frame,box=card(); box.addWidget(text('启动与托盘','Section'))
        self.preference_checks={}
        for key,label in [('startup_animation','开启动画 · 约 0.8 秒月亮淡入'),('close_to_tray','关闭窗口时收进系统托盘')]:
            check=QCheckBox(label); check.setChecked(self.preferences.value[key]); check.toggled.connect(lambda checked,k=key:self.save_preference(k,checked)); box.addWidget(check); self.preference_checks[key]=check
        box.addWidget(text('从托盘选择“退出界面”后，系统定时计划仍继续保留。','Small',True)); outer.addWidget(frame)
        frame,box=card(); box.addWidget(text('桌面通知','Section'))
        for key,label in [('notifications','启用桌面通知'),('notify_success','签到成功'),('notify_failed','签到失败'),('notify_mode','本机 / VPS 执行端切换')]:
            check=QCheckBox(label); check.setChecked(self.preferences.value[key]); check.toggled.connect(lambda checked,k=key:self.save_preference(k,checked)); box.addWidget(check); self.preference_checks[key]=check
        test=button('发送测试通知','check'); test.clicked.connect(self.test_notification); box.addWidget(test,alignment=Qt.AlignmentFlag.AlignLeft)
        box.addWidget(text('通知仅在托盘程序运行时有效；VPS 结果约每分钟检查。通知显示遵循 Windows 通知设置和免打扰。','Small',True)); outer.addWidget(frame)
        frame,box=card(); box.addWidget(text('软件更新 · 当前版本 '+updates.VERSION,'Section'))
        check=QCheckBox('自动检查新版本'); check.setChecked(self.preferences.value['auto_check_updates'])
        check.toggled.connect(lambda checked:self.save_preference('auto_check_updates',checked))
        self.preference_checks['auto_check_updates']=check; box.addWidget(check)
        box.addWidget(text('启动 8 秒后及运行期间每 4 小时检查 GitHub 正式版。退出程序后停止检查；不会自动下载或安装，不影响定时签到。','Small',True))
        self.update_status=text('尚未检查更新。','Muted',True); box.addWidget(self.update_status)
        row=QHBoxLayout(); self.update_button=button('检查更新'); self.update_button.clicked.connect(lambda:self.check_update(manual=True)); row.addWidget(self.update_button)
        self.update_download=button('打开新版下载页',primary=True); self.update_download.clicked.connect(self.open_update); self.update_download.hide(); row.addWidget(self.update_download); row.addStretch(); box.addLayout(row)
        outer.addWidget(frame); outer.addStretch(); return page

    def auto_check_update(self):
        if self.preferences.value['auto_check_updates']: self.check_update()

    def check_update(self,manual=False):
        if self._quitting or self.update_checking: return
        self.update_checking=True; self.update_button.setEnabled(False)
        self.update_status.setText('正在连接 GitHub 检查正式发布版…')
        self.title_bar.sync()
        if manual:self.login_update_status.setText('正在检查更新…'); self.login_update_status.show()
        self.tray_update.setEnabled(False)
        task=Job(updates.check_latest); key=id(task)
        def finish(value=None,error=None):
            release_job(self,key); self.update_checking=False
            if self._quitting: return
            self.update_button.setEnabled(True); self.tray_update.setEnabled(True)
            checked=now().strftime('%m-%d %H:%M')
            if error:
                self.title_bar.sync()
                self.update_status.setText('检查未完成：'+error+'（'+checked+'）')
                if manual:
                    self.notify('更新检查未完成：'+error,True)
                    self.login_update_status.setText('更新检查未完成：'+error)
                return
            self.update_release=value
            self.title_bar.sync()
            self.update_download.setVisible(value.available)
            message=('发现新版本 '+value.version+'，可打开下载页下载安装包。' if value.available else '当前版本 '+updates.VERSION+' 已是最新可用版本。')
            self.update_status.setText(message+'（检查于 '+checked+'）')
            self.login_update_status.setText(message)
            if value.available:self.login_update_status.show()
            self.tray_download.setVisible(value.available)
            if value.available:
                self.tray_download.setText('下载新版本 '+value.version)
                if value.version!=self.update_notified_version:
                    self.update_notified_version=value.version
                    self.desktop_notification('发现新版本 '+value.version,'请从托盘“下载新版本”或“外观与通知”打开下载页。')
            if manual: self.notify(message)
        connect_job(self,task,lambda value:finish(value),lambda error:finish(error=error)); self.update_pool.start(task)
        if manual:
            self.restore()
            if self.root_stack.currentIndex()==1: self.go(5)

    def open_update(self):
        if not self.update_release or not self.update_release.available: return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(self.update_release.page))

    def save_preference(self,key,value):
        try: self.preferences.set(**{key:value})
        except OSError:
            self.notify('外观设置未能保存，请检查用户数据目录权限。',True)
        # Restore controls if disk persistence fails, without emitting more writes.
        if key in getattr(self,'preference_checks',{}):
            with QSignalBlocker(self.preference_checks[key]): self.preference_checks[key].setChecked(self.preferences.value[key])
        if hasattr(self,'tray_notify'):
            with QSignalBlocker(self.tray_notify): self.tray_notify.setChecked(self.preferences.value['notifications'])

    def set_theme(self,mode):
        if mode not in THEMES: return
        self.save_preference('theme',mode); self.apply_theme()
        if self.preferences.value['theme']=='wallpaper': self.refresh_wallpaper()

    def preview_transparency(self,value):
        self.transparency_preview=value; self.transparency_value.setText(str(value)+'%')
        # Coalesce painting while dragging and write once after a short pause.
        if not self.transparency_render_timer.isActive(): self.transparency_render_timer.start(16)
        self.transparency_save_timer.start(350)

    def flush_transparency(self):
        self.transparency_save_timer.stop()
        try: self.preferences.set(surface_transparency=self.transparency_preview)
        except OSError:
            self.transparency_preview=self.preferences.value['surface_transparency']
            with QSignalBlocker(self.transparency_slider): self.transparency_slider.setValue(self.transparency_preview)
            self.transparency_value.setText(str(self.transparency_preview)+'%')
            self.notify('透明度未能保存，已恢复上次设置，请检查用户数据目录权限。',True)
        self.transparency_render_timer.stop(); self.apply_theme()

    def reset_transparency(self):
        self.transparency_slider.setValue(14); self.flush_transparency()

    def apply_theme(self):
        value=self.preferences.value; p=palette(value['theme'],value['accent'],value['wallpaper_dark']); self.theme_colors=p
        app=QApplication.instance(); apply_native_palette(app,p)
        theme_style=stylesheet(STYLES,p,value['theme'],self.transparency_preview)
        wallpaper=value['theme']=='wallpaper'
        self.wallpaper_canvas.enabled=wallpaper;self.wallpaper_canvas.update()
        if wallpaper:
            rgb=QColor(p['surface']).getRgb()[:3]
            theme_style+='QWidget#Main { background:transparent; } QWidget#LoginRight { background:rgba(%d,%d,%d,215); }'%rgb
        app.setStyleSheet(theme_style)
        self.transparency_slider.setEnabled(wallpaper); self.transparency_reset.setEnabled(wallpaper)
        self.transparency_hint.setText('仅调节卡片与侧栏背景；文字和按钮保持清晰，透出动态壁纸。' if wallpaper else '此滑块仅在动态壁纸模式生效；已保存的数值会保留。')
        for combo in self.theme_combos:
            with QSignalBlocker(combo): combo.setCurrentIndex(list(THEMES).index(value['theme']))
        for item in self.findChildren(QPushButton):
            glyph=item.property('glyph')
            if glyph: item.setIcon(icon(glyph,'#ffffff' if item.objectName()=='Primary' else p['accent_text'],27 if item.objectName()=='Mode' else 19))
        for item in self.findChildren(QLabel):
            glyph=item.property('glyph')
            if glyph:
                size=item.property('glyphSize'); item.setPixmap(icon(glyph,p['accent_text'],size).pixmap(size,size))
        for item in self.findChildren(Brand): item.update()
        self.setWindowIcon(icon('moon',p['accent_text']))
        if hasattr(self,'tray'):
            self.tray.setIcon(icon('moon',p['accent_text'])); self.tray_menu.setStyleSheet(theme_style)
            for key,action in self.tray_themes.items():
                with QSignalBlocker(action): action.setChecked(key==value['theme'])
        self.title_bar.menu.setStyleSheet(theme_style)
        if self.pages.currentIndex()==3: self.render_history()
        from .window_chrome import apply_chrome
        apply_chrome(self,p,value['theme'])
        self.sync_live_wallpaper()

    def sync_live_wallpaper(self):
        if hasattr(self,'live_wallpaper'):
            self.live_wallpaper.enable(self.preferences.value['theme']=='wallpaper' and self.isVisible() and not self.isMinimized() and not self._quitting)

    def reload_live_wallpaper(self):
        self.live_wallpaper.failed_until=0;self.live_wallpaper.signature=None;self.live_wallpaper.discover()
        self.refresh_wallpaper(force=True)

    def showEvent(self,event):
        from .window_chrome import apply_chrome,enable_custom_frame
        enable_custom_frame(self)
        apply_chrome(self,self.theme_colors,self.preferences.value['theme'])
        super().showEvent(event);self.sync_live_wallpaper()

    def hideEvent(self,event):
        super().hideEvent(event)
        if hasattr(self,'live_wallpaper'):self.live_wallpaper.enable(False)

    def changeEvent(self,event):
        super().changeEvent(event)
        from PySide6.QtCore import QEvent
        if event.type()==QEvent.Type.WindowStateChange:
            if hasattr(self,'title_bar'):self.title_bar.sync()
            QTimer.singleShot(0,self.sync_live_wallpaper)

    def nativeEvent(self,event_type,message):
        from .window_chrome import frame_event
        result=frame_event(self,message)
        return result if result is not None else super().nativeEvent(event_type,message)

    @Slot()
    def system_theme_changed(self,*args):
        if self.preferences.value['theme']=='system': self.apply_theme()

    def choose_engine(self):
        name=QFileDialog.getExistingDirectory(self,'选择 Wallpaper Engine 安装目录',self.preferences.value['engine_path'] or str(Path.home()))
        if name: self.save_engine(name)

    def save_engine(self,name):
        self.save_preference('engine_path',name); self.engine_edit.setText(self.preferences.value['engine_path']); self.refresh_wallpaper(force=True)

    def refresh_wallpaper(self,force=False):
        if self.wallpaper_reading or self._quitting: return
        if self.preferences.value['theme']=='system' and self.theme_colors['dark']!=system_dark(): self.apply_theme()
        if self.preferences.value['theme']!='wallpaper' and not force: return
        self.wallpaper_reading=True
        if force: self.wallpaper_reader.cached_signature=None
        path=self.preferences.value['engine_path']; task=Job(lambda:self.wallpaper_reader.resolve(path)); key=id(task)
        def finish(value):
            self.wallpaper_reading=False; release_job(self,key)
            if 'accent' in value:
                try: self.preferences.set(accent=value['accent'],wallpaper_dark=value['dark'])
                except OSError: pass
                if self.preferences.value['theme']=='wallpaper': self.apply_theme()
            self.wallpaper_source=value['source']
        connect_job(self,task,finish,lambda message:finish({'source':'壁纸读取暂不可用 · 保留上次配色','detail':'可检查安装目录后重新读取。'})); self.appearance_pool.start(task)

    def play_startup(self):
        if self.preferences.value['startup_animation']:
            self.startup_overlay=StartupOverlay(self)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'live_wallpaper'):self.live_wallpaper.reposition()
        overlay=getattr(self,'startup_overlay',None)
        if overlay:
            import shiboken6
            if shiboken6.isValid(overlay): overlay.setGeometry(self.rect())

    def moveEvent(self,event):
        super().moveEvent(event)
        if hasattr(self,'live_wallpaper'):self.live_wallpaper.reposition()

    def build_tray(self):
        self.tray = QSystemTrayIcon(icon('moon',self.theme_colors['accent_text']), self)
        self.tray_menu=QMenu(self); menu=self.tray_menu
        self.tray_status=menu.addAction(''); self.tray_status.setEnabled(False)
        show = menu.addAction('显示主窗口'); show.triggered.connect(self.restore)
        self.tray_pause = menu.addAction(''); self.tray_pause.triggered.connect(lambda:self.toggle_enabled(not self.state['enabled']))
        history=menu.addAction('查看运行记录'); history.triggered.connect(self.show_history)
        themes=menu.addMenu('界面主题'); self.tray_theme_group=QActionGroup(self); self.tray_themes={}
        for key,label in THEMES.items():
            action=themes.addAction(label); action.setCheckable(True); action.setChecked(key==self.preferences.value['theme'])
            self.tray_theme_group.addAction(action); action.triggered.connect(lambda checked,k=key:self.set_theme(k)); self.tray_themes[key]=action
        self.tray_notify=menu.addAction('桌面通知'); self.tray_notify.setCheckable(True); self.tray_notify.setChecked(self.preferences.value['notifications'])
        self.tray_notify.triggered.connect(lambda checked:self.set_notification_preference(checked))
        menu.addSeparator(); self.tray_update=menu.addAction('检查更新'); self.tray_update.triggered.connect(lambda:self.check_update(manual=True))
        self.tray_download=menu.addAction('下载新版本'); self.tray_download.setVisible(False); self.tray_download.triggered.connect(self.open_update)
        menu.addSeparator(); leave = menu.addAction('退出界面（系统计划保留）'); leave.triggered.connect(self.quit_ui); self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore() if reason in (QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger) else None)
        self.tray.messageClicked.connect(self.show_history)
        if QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()
        self.update_tray()

    def set_notification_preference(self,checked):
        self.save_preference('notifications',checked)
        with QSignalBlocker(self.preference_checks['notifications']): self.preference_checks['notifications'].setChecked(self.preferences.value['notifications'])

    def update_tray(self):
        if not hasattr(self,'tray'): return
        label={'local':'本机','cloud':'VPS','unknown':'待确认'}.get(self.state['mode'],'待确认')+' · 每天 '+self.state['time']+' · '+('已启用' if self.state['enabled'] else '已暂停')
        self.tray.setToolTip('晚安助手 · '+label); self.tray_status.setText(label)
        self.tray_pause.setText('暂停自动签到' if self.state['enabled'] else '恢复自动签到'); self.tray_pause.setEnabled(not self.busy)
        if self.standard:
            count=len(self.state['accounts']);active=sum(a['enabled'] for a in self.state['accounts'])
            label=f'普通版 · {count}/2 个账号 · {active} 个计划启用'
            self.tray.setToolTip('晚安助手 · '+label);self.tray_status.setText(label)
            self.tray_pause.setText(('暂停' if self.state['enabled'] else '恢复')+'当前账号计划 '+self.state['masked_id']);self.tray_pause.setEnabled(not self.busy and self.state['configured'])

    def show_history(self):
        if self.root_stack.currentIndex()==1: self.go(3)
        self.restore()

    def desktop_notification(self,title,body,error=False):
        if not self.preferences.value['notifications'] or not self.tray.isVisible(): return False
        self.tray.showMessage('晚安助手 · '+title,body,QSystemTrayIcon.MessageIcon.Warning if error else QSystemTrayIcon.MessageIcon.Information,6000)
        return True

    def test_notification(self):
        if not self.preferences.value['notifications']:
            self.notify('请先启用桌面通知。'); return
        sent=self.desktop_notification('通知已就绪','托盘运行时，将通知签到结果和执行端切换。')
        self.notify('测试通知已交给 Windows；显示遵循系统通知与免打扰设置。' if sent else '当前系统托盘不可用，请检查桌面环境。')

    def poll_notifications(self,remote=None):
        if self._quitting: return
        for title,body,error in self.event_notifications.consume(self.service.history(),self.preferences.value): self.desktop_notification(title,body,error)
        if remote is not None:
            for title,body,error in self.event_notifications.consume(remote,self.preferences.value,'cloud'): self.desktop_notification(title,body,error)

    def restore(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def quit_ui(self):
        if self.busy:
            self.notify('操作仍在进行，请等待完成后退出。', error=True); return
        if self.transparency_save_timer.isActive(): self.flush_transparency()
        self._quitting = True;self.live_wallpaper.enable(False); self.tray.hide(); QApplication.instance().quit()

    def closeEvent(self, event):
        if self._quitting: event.accept(); return
        if self.tray.isVisible() and self.preferences.value['close_to_tray']: self.hide(); event.ignore()
        elif self.busy: event.ignore()
        else: self.quit_ui(); event.accept()

    def go(self, index):
        if not hasattr(self, 'pages'): return
        self.pages.setCurrentIndex(index)
        headings = [('签到概览', '今日计划，一目了然。'), ('定时设置', '为每天留出一个固定时间。'), ('执行端', '普通版使用本机执行。' if self.standard else '按需要切换，状态始终清楚。'), ('运行记录', '每一次执行，都有迹可循。'), ('账号管理' if self.standard else '账号与连接', '两个账号，分别安排。' if self.standard else '账号、设备与备用服务器。'), ('外观与通知', '选择喜欢的配色，把结果留给通知。')]
        self.page_heading.setText(headings[index][0]); self.page_subtitle.setText(headings[index][1])
        if self.standard and index in (0,1):self.page_subtitle.setText('当前账号 '+self.state['masked_id']+' · 本机独立计划')
        for i, item in enumerate(self.nav_buttons): item.setChecked(i == index)
        if index == 3 and hasattr(self, 'history_table'): self.render_history()

    def notify(self, message, error=False):
        self.notice.setObjectName('Error' if error else 'Notice'); self.notice.style().unpolish(self.notice); self.notice.style().polish(self.notice); self.notice.setText(message); self.notice.show()

    def job(self, label, operation, done=None, *, plan_job=False):
        if self.busy: return
        self.busy = True; self.update_tray(); self.status_text.setText(label); self.progress.show(); self.login_progress.show()
        for control in self.controls: control.setEnabled(False)
        self.login_error.hide(); task = Job(operation); key = id(task)
        def finish(value=None, error=None):
            self.busy = False; release_job(self, key); self.progress.hide(); self.login_progress.hide()
            if isinstance(value, dict) and 'task' in value: self.task_state = value['task'] or {};self.task_probe_error=''
            if plan_job:self.configuration_error=error or ''
            for control in self.controls: control.setEnabled(True)
            self.status_text.setText('本机界面可关闭，系统计划继续保留。')
            self.refresh()
            self.poll_notifications()
            if error:
                self.notify(error, True)
                if self.root_stack.currentIndex() == 0:
                    self.login_error.setText(error); self.login_error.show(); self.password_edit.setFocus()
                    self.service.event('login_failed', '登录验证未完成，已保留原有账号和计划。')
            elif done: done(value)
            else: self.notify('操作已完成，状态已更新。')
        connect_job(self, task, lambda value: finish(value), lambda message: finish(error=message)); self.pool.start(task)

    @Slot(str)
    def recover_error(self, message):
        if not self.busy:
            self.progress.hide(); self.login_progress.hide()
            for control in self.controls: control.setEnabled(True)
        self.notify(message, True)
        if self.root_stack.currentIndex() == 0:
            self.login_error.setText(message); self.login_error.show(); self.password_edit.setFocus()

    def login_saved(self):
        if self.busy: return
        self.job('正在验证已保存的学校账号…', lambda: self.service.login(auto_login=self.auto_check.isChecked()), self.login_done)

    def login(self):
        student, password, remember = self.student_edit.text().strip(), self.password_edit.text(), self.auto_check.isChecked()
        self.password_edit.clear()
        if self.standard:
            target=None if self.login_adding else self.state['selected_profile']
            self.job('正在验证学校账号…', lambda: self.service.login(student,password,remember,profile_id=target), self.login_done)
        else:self.job('正在验证学校账号…', lambda: self.service.login(student, password, remember), self.login_done)

    def login_done(self, state):
        self.login_adding=False;self.login_button.setText('验证并进入');self.task_state=None
        self.authenticated = True; self.root_stack.setCurrentIndex(1); self.refresh(); self.notify('学校账号验证通过。登录过程没有提交签到。')

    def enter_offline(self):
        self.login_adding=False
        self.authenticated = False; self.root_stack.setCurrentIndex(1); self.refresh(); self.notify('当前为离线查看，学校账号尚未联网验证。')

    def saved_student(self):
        if self.standard:return self.service.saved_student()
        return legacy.load_account()['student_id'] if legacy.ACCOUNT.exists() else ''

    def show_login(self, add=False):
        if self.busy: return
        if self.standard and add and len(self.state['accounts'])>=2:
            self.notify('普通版最多同时保存两个账号。',True);return
        self.login_adding=bool(self.standard and add)
        self.authenticated = False; self.password_edit.clear(); self.login_error.hide(); self.root_stack.setCurrentIndex(0)
        self.student_edit.setText('' if self.login_adding else self.saved_student())
        self.password_edit.setPlaceholderText('请输入新账号的考勤密码' if self.login_adding else '已保存时可留空使用原密码')
        self.login_button.setText('验证并添加账号' if self.login_adding else '验证并进入')
        self.offline_button.setVisible(self.state['configured']);self.offline_button.setText('返回已保存的账号' if self.login_adding else '离线查看已保存的配置')

    def select_account(self,index):
        if self.rendering or self.busy:return
        slot=self.account_combo.itemData(index)
        if not slot or slot==self.state['selected_profile']:return
        self.authenticated=False;self.task_state=None;self.configuration_error='';self.task_probe_error=''
        self.job('正在切换当前账号…',lambda:self.service.select_account(slot),lambda result:self.notify('已切换当前账号；两个账号的计划各自保留，未保存的时间不会应用。'))

    def remove_current_account(self):
        slot=self.state['selected_profile']
        if not slot or self.busy:return
        answer=QMessageBox.question(self,'移除当前账号','将停用并移除 '+self.state['masked_id']+' 的本机计划和加密凭据。另一个账号不受影响。是否继续？',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes:
            self.authenticated=False;self.task_state=None;self.configuration_error='';self.task_probe_error=''
            self.job('正在移除当前账号及其本机计划…',lambda:self.service.remove_account(slot))

    def switch(self, mode):
        if self.standard:
            self.job('正在启用或修复当前账号的本机计划…',self.service.activate_local,plan_job=True) if mode=='local' else self.notify('VPS 将在后续付费版开放。',True)
            return
        if mode == 'local': self.job('正在确认 VPS 停用并切回本机…', self.service.activate_local)
        else: self.job('正在检查连接、停用本机并启用 VPS…', self.service.switch_cloud)

    def toggle_enabled(self, enabled):
        if self.rendering: return
        self.job('正在恢复计划…' if enabled else '正在暂停计划…', self.service.resume if enabled else self.service.pause,plan_job=True)

    def schedule_dirty(self):
        if self.rendering: return
        value = self.time_edit.time().toString('HH:mm')
        self.schedule_saved.setText(('有未保存的更改：' + value) if value != self.state['time'] else self.saved_text())

    def saved_text(self):
        if self.standard:return '当前账号已保存：每天 '+self.state['time']+' · 北京时间 · 本机运行'
        return '已保存：每天 ' + self.state['time'] + ' · 北京时间' + (' · 备用端待同步' if self.state['pending_sync'] else ' · 两端配置已同步')

    def apply_time(self):
        value = self.time_edit.time().toString('HH:mm')
        self.job('正在保存并校验系统计划…', lambda: self.service.save_schedule(value), lambda result: self.notify('每日时间已保存，系统任务已校验。' if self.standard else '每日时间已保存。'),plan_job=True)

    def repair_records(self):
        if self.standard:self.job('正在核对本机成功日志与账号归属…',self.service.recover_record,lambda result:self.notify('已核对并恢复可验证的本地记录，未重新提交签到。'))

    def check_vps(self): self.job('正在检查 VPS 连接与服务…', self.service.check_connection, self.connection_result)

    def connection_result(self, result):
        self.connection_status.setText(result['message']); self.notify(result['message'])

    def save_connection(self):
        value = {'host': self.host_edit.text().strip(), 'port': self.port_edit.value(), 'user': self.user_edit.text().strip(), 'key': self.key_edit.text().strip()}
        self.job('正在保存连接…', lambda: self.service.save_connection(value))

    def choose_key(self):
        name, _ = QFileDialog.getOpenFileName(self, '选择已有 SSH 私钥', str(Path.home()))
        if name: self.key_edit.setText(name)

    def open_data(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.service.data)))

    def remote_history(self, entries):
        self.extra_history = entries; self.render_history(); self.notify('已读取 VPS 记录。')

    def render_history(self):
        entries = self.service.history() + getattr(self, 'extra_history', [])
        entries.sort(key=lambda entry: entry.get('at', ''), reverse=True)
        term = self.log_filter.text().strip().lower()
        entries = [entry for entry in entries if term in json.dumps(entry, ensure_ascii=False).lower()]
        self.history_table.setRowCount(len(entries)); self.empty_history.setVisible(not entries)
        kinds = {'login':'账号验证','migration':'配置迁移','mode':'模式切换','schedule':'时间设置','running':'开始执行','success':'签到成功','failed':'签到失败','record_failed':'回执保存失败','record_recovered':'记录恢复','error':'需要处理','pause':'暂停计划','skipped':'跳过执行','deploy':'备用部署','connection':'连接设置'}
        for row, entry in enumerate(entries):
            timestamp = entry.get('at', '')[:19].replace('T', ' ')
            values = [timestamp, kinds.get(entry.get('kind'), '配置更新'), {'local':'本机','cloud':'VPS'}.get(entry.get('mode'), '—'), (entry.get('account_label','')+'  ' if entry.get('account_label') else '')+entry.get('message', '')]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if entry.get('kind') in ('failed','error','record_failed'): item.setForeground(QColor(self.theme_colors['error']))
                elif entry.get('kind') == 'success': item.setForeground(QColor(self.theme_colors['success']))
                self.history_table.setItem(row, column, item)
        self.history_table.resizeRowsToContents()

    def refresh(self):
        if self.busy: return
        previous = self.state
        edited = self.time_edit.time().toString('HH:mm')
        try: self.state = self.service.status()
        except Exception: return
        self.rendering = True
        self.account_badge.setText('考勤账号 ' + self.state['masked_id']); self.settings_account.setText('学号 ' + self.state['masked_id'] + ' · 本机加密保存')
        self.auth_badge.setText('学校账号已验证' if self.authenticated else '尚未联网验证')
        self.auth_badge.setObjectName('Pill' if self.authenticated else 'Unverified'); self.auth_badge.style().unpolish(self.auth_badge); self.auth_badge.style().polish(self.auth_badge)
        self.migration_frame.setVisible(not self.state['managed']); self.plan_pill.setText('尚未接管' if not self.state['managed'] else '待确认' if self.state['mode']=='unknown' else '已启用' if self.state['enabled'] else '已暂停')
        self.big_time.setText(self.state['time']); self.executor_label.setText({'local':'由本机执行','cloud':'由 VPS 执行','unknown':'运行端需要确认'}.get(self.state['mode'], '需要处理'))
        following = datetime.fromisoformat(self.state['next_run']); self.next_label.setText(('今天 ' if following.date() == now().date() else '明天 ') + self.state['time'] + ' · 北京时间')
        success = self.state['last_success'] == now().date().isoformat()
        self.today_status.setText('今日已完成' if success else '尚未接管' if not self.state['managed'] else '运行端待确认' if self.state['mode']=='unknown' else '计划已暂停' if not self.state['enabled'] else '等待执行')
        self.today_detail.setText('学校系统已有今日成功记录。' if success else '旧版安排保留，接管后由新版管理。' if not self.state['managed'] else '计划会在设定时间由系统触发。' if self.state['enabled'] else '恢复计划后继续每日执行。')
        if success and self.state.get('success_source')=='log_recovery':self.today_detail.setText('已从当次成功执行日志恢复本地记录；本次未重新提交签到，也未重新联网核验。')
        selected_history=[e for e in self.service.history() if not self.standard or
            (e.get('account_tag') and e.get('account_tag')==self.state['account_tag']) or
            (e.get('credential_tag') and e.get('credential_tag')==self.state.get('credential_tag') and e.get('profile_id')==self.state.get('selected_profile')) or
            (not e.get('account_tag') and self.state.get('legacy_history',False) and e.get('profile_id') in (None,'primary'))]
        latest = next((entry for entry in selected_history if entry.get('at','')[:10] == now().date().isoformat() and entry.get('kind') in ('failed','running','skipped','record_failed')), None)
        self.latest_execution=latest
        if not success and latest and self.state['mode']=='local' and self.state['enabled']:
            self.today_status.setText({'failed':'签到未确认','running':'正在执行','skipped':'本次未执行','record_failed':'结果保存失败'}[latest['kind']])
            self.today_detail.setText(latest['message'])
        for item in [self.quick_local,self.detail_local]: item.setChecked(self.state['mode'] == 'local')
        for item in [self.quick_cloud,self.detail_cloud]: item.setChecked(self.state['mode'] == 'cloud')
        self.mode_hint.setText('VPS 已启用，本机任务停用。' if self.state['mode']=='cloud' else '状态未确认，本机保持停用，请检查连接后恢复。' if self.state['mode']=='unknown' else '日常使用本机；切换到云端时会先停用本机计划。')
        with QSignalBlocker(self.enabled_check):
            self.enabled_check.setChecked(self.state['enabled'])
        if edited == previous['time'] or previous['time'] != self.state['time'] or previous.get('selected_profile')!=self.state.get('selected_profile') or previous.get('account_tag')!=self.state.get('account_tag'):
            self.time_edit.setTime(QTime.fromString(self.state['time'],'HH:mm'))
        self.schedule_saved.setText(('有未保存的更改：' + edited) if self.time_edit.time().toString('HH:mm') != self.state['time'] else self.saved_text())
        entries = selected_history; last = next((entry for entry in entries if entry['kind'] in ('success','failed','running','skipped','record_failed','record_recovered')), None)
        self.recent_label.setText((last['at'][:19].replace('T',' ') + '  ' + last['message']) if last else '暂时没有签到执行记录。首次执行后将在这里显示结果。')
        if success and (not last or last.get('at','')[:10]!=now().date().isoformat() or last.get('kind') not in ('success','record_recovered','skipped')):
            stamp=(self.state.get('success_confirmed_at') or self.state['last_success'])[:19].replace('T',' ')
            self.recent_label.setText(stamp+'  '+('已从成功日志恢复本地记录，未重新提交签到。' if self.state.get('success_source')=='log_recovery' else '本地成功回执已保存。'))
        self.task_details.setText('当前计划：每天北京时间 ' + self.state['time'] + '\n执行窗口随配置调整，不再固定为 22:00。')
        if self.state['mode'] == 'local' and self.state['managed']:
            actual = (self.task_state or {}).get('state')
            detail = {'Ready':'系统任务已就绪','Running':'系统任务正在执行','Disabled':'系统任务已停用'}.get(actual, '系统任务状态待确认')
            self.task_details.setText('当前计划：每天北京时间 ' + self.state['time'] + '\n' + detail + ' · 每分钟重新检查')
            if self.task_state is not None and self.state['enabled'] and actual not in ('Ready','Running'):
                self.plan_pill.setText('需要修复')
                self.today_detail.setText('系统任务未就绪，请在执行端点击“本机”修复。')
        elif self.state['mode'] == 'cloud' and self.remote_state is not None:
            active = self.remote_state.get('task',{}).get('ActiveState') == 'active'
            self.task_details.setText('VPS 定时器：' + ('已就绪' if active else '未就绪或连接待确认') + '\n每分钟读取远端状态与今日成功记录。')
            if self.state['enabled'] and not active: self.plan_pill.setText('待确认')
        if self.standard:
            with QSignalBlocker(self.account_combo):
                self.account_combo.clear()
                for account in self.state['accounts']:self.account_combo.addItem(account['label'],account['profile_id'])
                if self.state['selected_profile']:self.account_combo.setCurrentIndex(self.account_combo.findData(self.state['selected_profile']))
            summary='\n'.join(a['label']+'    每天 '+a['time']+'    '+('已启用' if a['enabled'] else '已暂停')+('    ← 当前账号' if a['profile_id']==self.state['selected_profile'] else '') for a in self.state['accounts']) or '尚未添加账号。'
            self.account_summary.setText(summary);self.account_management.setText(summary)
            can_add=len(self.state['accounts'])<2
            for item in (self.sidebar_add,self.add_account_button):item.setEnabled(can_add);item.setText(f'添加账号（{len(self.state["accounts"])}/2）')
            self.remove_account_button.setEnabled(self.state['configured']);self.enabled_check.setEnabled(self.state['configured'] and self.state.get('credential_ok',True));self.save_time.setEnabled(self.state['configured'] and self.state.get('credential_ok',True))
            self.quick_cloud.setEnabled(False);self.detail_cloud.setEnabled(False)
            self.mode_hint.setText('普通版：两个账号均由本机执行。VPS 将在后续付费版开放。')
            self.page_subtitle.setText(('当前账号 '+self.state['masked_id']+' · 本机独立计划') if self.pages.currentIndex() in (0,1) else self.page_subtitle.text())
        self.rendering = False; self.render_plan_health(); self.update_tray()
        if self.pages.currentIndex() == 3: self.render_history()

    def probe_task(self):
        if self.busy or self.probing: return
        self.probing = True
        cloud = self.state['mode']=='cloud'
        token=(self.state.get('selected_profile'),self.state['time'],self.state['enabled'])
        def operation():
            value=self.service.monitor()
            if cloud:
                try: value={**value,'events':self.service.rpc('history')}
                except Exception: pass
            return value
        task = Job(operation); key = id(task)
        def finish(value):
            self.probing = False
            if token!=(self.state.get('selected_profile'),self.state['time'],self.state['enabled']):
                release_job(self,key);QTimer.singleShot(100,self.probe_task);return
            if cloud:
                self.remote_state = value or {}; self.poll_notifications((value or {}).get('events'))
            else: self.task_state = (value or {}).get('task') or {};self.task_probe_error=(value or {}).get('error','')
            release_job(self, key); self.refresh()
        connect_job(self, task, finish, lambda message: finish({'error':message})); self.pool.start(task)

    def configuration_problem(self):
        if not self.state['configured']:return '尚未添加并验证学校账号。'
        if not self.state.get('credential_ok',True):return '当前账号的加密凭据无法读取，请移除后重新验证。'
        if not self.state.get('time_valid',True):return '当前时间不在 21:30–23:30 范围，请重新设置并保存。'
        if self.configuration_error:return self.configuration_error
        if not self.state['managed']:return '尚未接管系统任务，请先接管本机计划。'
        if self.task_probe_error:return '无法读取 Windows 计划：'+self.task_probe_error
        if self.state['mode']=='local' and self.state['enabled'] and self.task_state is not None:
            task=self.task_state
            if not task:return 'Windows 定时任务不存在，请点击本机运行修复。'
            if task.get('state') not in ('Ready','Running'):return 'Windows 定时任务未启用，请点击本机运行修复。'
            if task.get('schedule_time') and task['schedule_time']!=self.state['time']:return 'Windows 任务时间为 '+task['schedule_time']+'，与已保存的 '+self.state['time']+' 不一致，请重新保存。'
            if task.get('description') and task['description']!=TASK_DESCRIPTION:return '同名任务来源不匹配，无法确认本机计划。'
            if task.get('worker') and self.standard:
                scheduler=self.service.schedulers.get(self.state.get('selected_profile'))
                if hasattr(scheduler,'expected_action'):
                    expected,args=scheduler.expected_action()
                    if Path(task['worker']).resolve()!=Path(expected).resolve() or task.get('arguments')!=args:return '系统任务指向其他程序或账号，请点击本机运行修复。'
        return ''

    def render_plan_health(self):
        problem=self.configuration_problem()
        checking=self.state['enabled'] and self.task_state is None and self.state['mode']=='local'
        self.configuration_notice.setVisible(bool(problem))
        self.configuration_notice.setText('计划尚未配置成功：'+problem if problem else '')
        status='error' if problem else 'checking' if checking else 'ok' if self.state['enabled'] else 'paused'
        self.plan_pill.setProperty('health',status)
        self.plan_pill.setText('! 需要修复' if problem else '正在校验' if checking else '已启用' if self.state['enabled'] else '已暂停')
        self.plan_pill.style().unpolish(self.plan_pill);self.plan_pill.style().polish(self.plan_pill)
        if problem:
            self.today_detail.setText(problem)
            if self.state.get('last_success')!=now().date().isoformat():self.today_status.setText('计划需要修复')
        task=self.task_state or {};last_run=task.get('last_run','');feedback=''
        if last_run[:10]==now().date().isoformat() and self.state.get('last_success')!=now().date().isoformat():
            code=task.get('last_result')
            if code==0:
                skipped=getattr(self,'latest_execution',None)
                if skipped and skipped.get('skip_reason') and skipped.get('at','')[:16]==last_run[:16]:feedback=skipped['message']
                else:feedback='系统任务已结束，但本地尚无今日签到成功记录。请查看运行记录，并以学校系统结果为准。'
            elif code is not None and code not in (267008,267009,267010,267011,267013):feedback='上次系统任务未成功完成（退出码 '+str(code)+'），请查看运行记录。'
        self.execution_feedback.setText(feedback);self.execution_feedback.setVisible(bool(feedback))
        latest=getattr(self,'latest_execution',None) or {}
        can_repair=(task.get('last_result')==0 and not latest.get('skip_reason')) or (task.get('last_result')==1 and (latest.get('kind')=='record_failed' or latest.get('skip_reason')=='record_pending'))
        self.repair_record_button.setVisible(bool(feedback) and self.standard and self.state.get('credential_ok',False) and can_repair)
        self.countdown()

    def countdown(self):
        if not hasattr(self,'count_label'):return
        if self.configuration_problem():self.count_label.setText('计划待修复 · 原因见下方提示');return
        if not self.state['enabled']:self.count_label.setText('自动签到已暂停');return
        if self.state['mode']=='local' and self.task_state is None:self.count_label.setText('正在校验系统任务…');return
        current=now();hour,minute=map(int,self.state['time'].split(':'))
        following=current.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if following<=current:following+=timedelta(days=1)
        remaining=max(0,int((following-current).total_seconds()))
        self.count_label.setText(f'距离下次执行  {remaining//3600:02d}:{remaining%3600//60:02d}:{remaining%60:02d}')


def run(service=None):
    app = QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName('AHUTSignIn'); app.setOrganizationName('AHUTTools'); app.setStyle('Fusion'); app.setFont(QFont('Microsoft YaHei UI', 9)); app.setStyleSheet(STYLES)
    try:
        service = service or StandardService()
    except Exception:
        QMessageBox.critical(None, '晚安助手', '无法读取程序配置。请检查用户数据目录的文件与访问权限，保留原文件后再修复。\n用户数据目录：%LOCALAPPDATA%\\AHUTSignIn')
        return 1
    lock = QLockFile(str(service.data / 'desktop-ui.lock')); lock.setStaleLockTime(0)
    import hashlib
    server_name = 'AHUTSignIn-' + hashlib.sha256(str(service.data).encode()).hexdigest()[:18]
    if not lock.tryLock(100):
        client = QLocalSocket(); client.connectToServer(server_name)
        if client.waitForConnected(1500):
            client.write(b'show'); client.waitForBytesWritten(500); client.disconnectFromServer()
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer(); server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption); server.listen(server_name)
    app.setQuitOnLastWindowClosed(False)
    window = Window(service); window.show(); window.play_startup()
    # GUI callbacks are outside the entry point's try/except. Keep a private
    # traceback without exception values, account fields, or request payloads.
    import faulthandler, os
    diagnostic = (service.data / 'ui-diagnostics.log').open('a', encoding='utf-8', buffering=1)
    diagnostic.write(f'{now().isoformat()} ui-start pid={os.getpid()} parent={os.getppid()}\n')
    window.live_wallpaper.status_changed.connect(lambda message:diagnostic.write(f'{now().isoformat()} wallpaper {message}\n'))
    faulthandler.enable(file=diagnostic, all_threads=True)
    original_hook = sys.excepthook
    def callback_error(kind, value, trace):
        diagnostic.write(f'{now().isoformat()} callback-error {kind.__name__}\n')
        diagnostic.write(''.join(traceback.format_list(traceback.extract_tb(trace))))
        window.runtime_error.emit('操作未完成，请重新输入并重试。诊断记录已保存。')
    sys.excepthook = callback_error
    app.aboutToQuit.connect(lambda: diagnostic.write(f'{now().isoformat()} ui-exit\n'))
    def restore():
        connection = server.nextPendingConnection()
        if connection:
            connection.readAll(); connection.disconnectFromServer(); connection.deleteLater()
            window.restore()
    server.newConnection.connect(restore)
    try:
        return app.exec()
    finally:
        sys.excepthook = original_hook; faulthandler.disable(); diagnostic.close(); server.close(); lock.unlock()
