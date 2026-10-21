"""Theme-aware application caption and version menu, shared by both screens."""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton

from .updates import VERSION


class CaptionButton(QPushButton):
    def __init__(self, owner, kind, label):
        super().__init__(owner)
        self.owner=owner; self.kind=kind
        self.setObjectName('CaptionClose' if kind=='close' else 'CaptionButton')
        self.setFixedSize(46,40); self.setAccessibleName(label); self.setToolTip(label)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=self.palette().buttonText().color()
        if self.kind=='close' and self.underMouse():color=Qt.GlobalColor.white
        painter.setPen(QPen(color,1.2)); x=self.width()//2-5; y=self.height()//2-5
        if self.kind=='minimize':painter.drawLine(x,y+5,x+10,y+5)
        elif self.kind=='close':painter.drawLine(x,y,x+10,y+10);painter.drawLine(x+10,y,x,y+10)
        elif self.owner.isMaximized():
            painter.drawRect(x+3,y,8,8);painter.fillRect(x,y+3,8,8,self.palette().button())
            painter.drawRect(x,y+3,8,8)
        else:painter.drawRect(x,y,10,10)
        painter.end()


class TitleBar(QFrame):
    def __init__(self,owner):
        super().__init__(owner); self.owner=owner; self.setObjectName('TitleBar'); self.setFixedHeight(44)
        self.setAccessibleName('应用标题栏')
        row=QHBoxLayout(self);row.setContentsMargins(0,2,0,2);row.setSpacing(0)
        row.addSpacing(138); row.addStretch()
        self.name=QLabel('晚安助手',self);self.name.setObjectName('CaptionName')
        self.name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.name);row.addSpacing(10)
        self.version=QPushButton('v'+VERSION,self);self.version.setObjectName('CaptionVersion')
        self.version.setCursor(Qt.CursorShape.PointingHandCursor);self.version.setAccessibleName('版本与软件更新')
        self.version.setToolTip('点击查看版本和检查更新');self.version.setMinimumHeight(26)
        self.menu=QMenu(self)
        current=self.menu.addAction('当前版本 v'+VERSION);current.setEnabled(False)
        self.menu.addSeparator();self.check_action=self.menu.addAction('检查更新')
        self.check_action.triggered.connect(lambda:owner.check_update(manual=True))
        self.download_action=self.menu.addAction('打开新版下载页');self.download_action.setVisible(False)
        self.download_action.triggered.connect(owner.open_update)
        self.version.clicked.connect(self.show_version_menu);row.addWidget(self.version);row.addStretch()
        self.minimize=CaptionButton(owner,'minimize','最小化');self.minimize.clicked.connect(owner.showMinimized)
        self.maximize=CaptionButton(owner,'maximize','最大化');self.maximize.clicked.connect(self.toggle_maximized)
        self.close_button=CaptionButton(owner,'close','关闭窗口');self.close_button.clicked.connect(owner.close)
        for item in (self.minimize,self.maximize,self.close_button):row.addWidget(item)

    def sync(self):
        checking=self.owner.update_checking
        self.check_action.setEnabled(not checking)
        self.check_action.setText('正在检查更新…' if checking else '检查更新')
        release=self.owner.update_release;available=bool(release and release.available)
        self.download_action.setVisible(available)
        if available:self.download_action.setText('下载新版本 '+release.version)
        self.version.setToolTip('发现新版本 '+release.version+'，点击打开更新菜单' if available else '点击查看版本和检查更新')
        self.maximize.setToolTip('还原' if self.owner.isMaximized() else '最大化')
        self.maximize.setAccessibleName(self.maximize.toolTip());self.maximize.update()

    def show_version_menu(self):
        self.sync();self.menu.popup(self.version.mapToGlobal(QPoint(0,self.version.height()+4)))

    def toggle_maximized(self):
        if self.owner.isMaximized():self.owner.showNormal()
        else:self.owner.showMaximized()
        self.sync()

    def drag_at(self,point):
        """Version/menu and caption controls must receive ordinary Qt clicks."""
        local=self.mapFrom(self.owner,point)
        if not self.rect().contains(local):return False
        return not any(button.geometry().contains(local) for button in
                       (self.version,self.minimize,self.maximize,self.close_button))

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove();event.accept()
        else:super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.toggle_maximized();event.accept()
        else:super().mouseDoubleClickEvent(event)
