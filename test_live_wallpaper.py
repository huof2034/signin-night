"""Offline live-background protocol, dependency adapter and Qt rendering checks."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,mmap,struct,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtCore import QObject
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from desktop import live_wallpaper as live
import test_appearance as fixtures


class AdapterTests(unittest.TestCase):
    def test_actual_github_adapter_reads_project_not_preview(self):
        with tempfile.TemporaryDirectory(prefix='ahut-live-adapter-') as folder:
            root=Path(folder);engine=root/'engine';engine.mkdir();(engine/'wallpaper64.exe').write_bytes(b'not executable')
            project=root/'project';project.mkdir();(project/'project.json').write_text(json.dumps({'type':'scene','preview':'not-the-background.gif','general':{'properties':{'music':{'type':'bool'}}}}),encoding='utf-8')
            file=str(project/'scene.pkg');config={'user':{'general':{'wallpaperconfig':{'selectedwallpapers':{'Monitor0':{'file':file}}}}}}
            config['user']['wproperties']={file:{'Monitor0':{'volume':70,'music':True,'accent':0.7}}}
            (engine/'config.json').write_text(json.dumps(config),encoding='utf-8')
            value=live.bridge({'action':'current','engine':str(engine)},timeout=45)
            self.assertEqual(Path(value['project']),project/'project.json');self.assertEqual(value['type'],'scene');self.assertIs(value['properties']['music'],False)
            self.assertEqual(config,json.loads((engine/'config.json').read_text(encoding='utf-8')))

    def test_music_sliders_and_ambient_sounds_are_silent_without_disabling_visuals(self):
        with tempfile.TemporaryDirectory(prefix='ahut-live-silent-') as folder:
            root=Path(folder);(root/'wallpaper64.exe').write_bytes(b'not executable')
            properties={'music':{'type':'slider','min':0,'max':1,'value':.5},'windsound':{'type':'slider','min':0,'max':1,'value':.8},'thunderstormsound':{'type':'bool','value':True},'audioresponsive':{'type':'bool','value':True},'musicvisualizer':{'type':'bool','value':True}}
            (root/'project.json').write_text(json.dumps({'type':'scene','general':{'properties':properties}}),encoding='utf-8')
            file=str(root/'scene.pkg');saved={'volume':70,'music':.5,'audioresponsive':True,'musicvisualizer':True}
            config={'user':{'general':{'wallpaperconfig':{'selectedwallpapers':{'Monitor0':{'file':file}}}},'wproperties':{file:{'Monitor0':saved}}}}
            (root/'config.json').write_text(json.dumps(config),encoding='utf-8')
            result=live.bridge({'action':'current','engine':str(root)})['properties']
            self.assertEqual([result[k] for k in ('volume','music','windsound','thunderstormsound')],[0,0,0,False])
            self.assertTrue(result['audioresponsive']);self.assertTrue(result['musicvisualizer'])
            self.assertEqual(config,json.loads((root/'config.json').read_text(encoding='utf-8')))

    def test_adapter_refuses_application_wallpapers(self):
        with tempfile.TemporaryDirectory(prefix='ahut-live-reject-') as folder:
            root=Path(folder);(root/'wallpaper64.exe').write_bytes(b'not executable')
            (root/'project.json').write_text('{"type":"application"}',encoding='utf-8')
            config={'user':{'general':{'wallpaperconfig':{'selectedwallpapers':{'Monitor0':{'file':str(root/'untrusted.exe')}}}}}}
            (root/'config.json').write_text(json.dumps(config),encoding='utf-8')
            with self.assertRaises(RuntimeError):live.bridge({'action':'current','engine':str(root)})


class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.owner=QObject();self.reader=live.LiveWallpaper(self.owner)
        self.memory=mmap.mmap(-1,live.CAPACITY,tagname='Local\\AHUTLive-test-'+uuid.uuid4().hex)
        self.reader.shared=self.memory;self.reader.process=Mock();self.reader.process.poll.return_value=None;self.reader.started=time.monotonic()
        self.frames=[];self.reader.frame_ready.connect(self.frames.append)
        struct.pack_into('<I',self.memory,0,live.MAGIC)
    def tearDown(self):
        self.reader.process=None;self.reader.stop_player();self.owner.deleteLater();self.app.processEvents()
    def publish(self,sequence=2,width=4,height=3,stride=16):
        struct.pack_into('<Q',self.memory,8,sequence);struct.pack_into('<IIII',self.memory,16,width,height,stride,1)
        struct.pack_into('<Q',self.memory,32,int(time.monotonic()*1000))
        self.memory[64:112]=b'\x30\x60\xa0\xff'*12
    def test_latest_complete_frame_is_copied_and_not_replayed(self):
        self.publish();self.reader.read_frame()
        self.assertEqual(len(self.frames),1);self.assertEqual(self.frames[0].pixelColor(0,0),QColor('#a06030'))
        self.reader.read_frame();self.assertEqual(len(self.frames),1)
        self.memory[64:68]=b'\0\0\0\xff';self.assertEqual(self.frames[0].pixelColor(0,0),QColor('#a06030'))
    def test_incomplete_and_oversized_frames_are_ignored(self):
        self.publish(sequence=1);self.reader.read_frame();self.assertFalse(self.frames)
        self.publish(width=99999);self.reader.read_frame();self.assertFalse(self.frames)
    def test_stalled_player_is_reported_without_fabricating_animation(self):
        self.publish();self.reader.read_frame()
        struct.pack_into('<Q',self.memory,32,0);self.reader.read_frame()
        self.assertIn('暂未更新',self.reader.message);self.assertEqual(len(self.frames),1)
    def test_offscreen_test_ui_never_launches_a_real_player(self):
        with patch.object(self.reader,'discover') as discover:self.reader.enable(True);discover.assert_not_called()


class CanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.AppearanceUiTests.setUpClass()
    def setUp(self):self.fixture=fixtures.AppearanceUiTests();self.fixture.setUp();self.window=self.fixture.window
    def tearDown(self):self.fixture.tearDown()
    def paint(self,color):
        image=QImage(160,90,QImage.Format.Format_RGB32);image.fill(QColor(color));self.window.wallpaper_canvas.set_frame(image);QTest.qWait(50)
        return self.window.grab().toImage().pixelColor(210,100)
    def test_real_frames_show_behind_the_interface_only_in_wallpaper_mode(self):
        w=self.window;w.enter_offline();w.set_theme('wallpaper')
        self.assertNotEqual(self.paint('#ff0000'),self.paint('#0000ff'))
        w.set_theme('light');self.assertEqual(self.paint('#ff0000'),self.paint('#0000ff'))
        self.assertEqual(w.windowOpacity(),1.0)
    def test_visibility_and_theme_control_background_lifecycle(self):
        w=self.window
        with patch.object(w.live_wallpaper,'enable') as enable:
            w.set_theme('wallpaper');self.assertTrue(enable.call_args.args[0])
            w.hide();self.assertFalse(enable.call_args.args[0])
            w.show();self.assertTrue(enable.call_args.args[0])
            w.set_theme('dark');self.assertFalse(enable.call_args.args[0])


if __name__=='__main__':unittest.main()
