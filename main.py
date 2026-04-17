Gmail	Devansh Patel <devansh201144@gmail.com>
(no subject)
Devansh Patel <devansh201144@gmail.com>	Fri, Apr 17, 2026 at 1:18 PM
To: Devansh Patel <devansh201144@gmail.com>
import webbrowser
import itertools
import threading
import os
import time
from kivy.utils import platform

from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen, NoTransition
from kivy.clock import Clock
from kivy.properties import (
    NumericProperty, StringProperty, ListProperty,
    DictProperty, BooleanProperty
)
from kivymd.uix.textfield import MDTextField
from kivymd.uix.button import MDRaisedButton, MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivy.storage.jsonstore import JsonStore
from kivy.uix.image import Image as KivyImage
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Line
from kivy.graphics.texture import Texture
from camera4kivy import Preview

store = JsonStore('tournament_data.json')

# ── AdMob IDs — replace with your real IDs ───────────────────────────────
ADMOB_APP_ID      = "ca-app-pub-3940256099942544~3347511713"  # test
REWARDED_AD_ID    = "ca-app-pub-3940256099942544/5224354917"  # test
# ─────────────────────────────────────────────────────────────────────────

# ── Server URL ────────────────────────────────────────────────────────────
SERVER_URL = "https://lani-vapory-dryly.ngrok-free.dev/process"
# ─────────────────────────────────────────────────────────────────────────

VIDEO_W = 1280
VIDEO_H = 720

DEFAULT_STUMP = (
    int(VIDEO_W * 0.48), int(VIDEO_H * 0.35),
    int(VIDEO_W * 0.52), int(VIDEO_H * 0.46))

if platform == 'android':
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread

    PythonActivity   = autoclass('org.kivy.android.PythonActivity')
    AdRequestBuilder = autoclass('com.google.android.gms.ads.AdRequest$Builder')
    MobileAds        = autoclass('com.google.android.gms.ads.MobileAds')

    class PythonRewardedListener(PythonJavaClass):
        __javainterfaces__ = ['com/google/android/gms/ads/reward/RewardedVideoAdListener']
        __javacontext__ = 'app'

        def __init__(self, callbacks):
            super().__init__()
            self.callbacks = callbacks

        @java_method('(Lcom/google/android/gms/ads/reward/RewardItem;)V')
        def onRewarded(self, reward):
            t, a = reward.getType(), reward.getAmount()
            Clock.schedule_once(lambda dt: self.callbacks['on_reward'](t, a))

        @java_method('()V')
        def onRewardedVideoAdLoaded(self):
            Clock.schedule_once(lambda dt: self.callbacks['on_load']())

        @java_method('(I)V')
        def onRewardedVideoAdFailedToLoad(self, error_code):
            Clock.schedule_once(lambda dt: self.callbacks['on_fail'](error_code))

        @java_method('()V')
        def onRewardedVideoAdOpened(self): pass

        @java_method('()V')
        def onRewardedVideoAdClosed(self):
            Clock.schedule_once(lambda dt: self.callbacks['on_close']())

        @java_method('()V')
        def onRewardedVideoStarted(self): pass

        @java_method('()V')
        def onRewardedVideoAdLeftApplication(self): pass

        @java_method('()V')
        def onRewardedVideoCompleted(self): pass

# ── AdMob helper ─────────────────────────────────────────────────────────
class AdManager:
    def __init__(self, ad_unit_id, on_load=None, on_fail=None, on_reward=None, on_close=None, on_exhausted=None):
        self.ad_unit_id = ad_unit_id
        self.retry_count = 0
        self.max_retries = 5
        
        self.callbacks = {
            'on_load': on_load or (lambda: None),
            'on_fail': on_fail or (lambda code: None),
            'on_reward': on_reward or (lambda t, a: None),
            'on_close': on_close or (lambda: None),
            'on_exhausted': on_exhausted or (lambda: print("Max retries reached. No ads available."))
        }
        # Holds the one-shot upload callback set by show_rewarded()
        self._pending_reward_callback = None

        if platform == 'android':
            self._init_ads()

    def _init_ads(self):
        @run_on_ui_thread
        def _ui_init():
            MobileAds.initialize(PythonActivity.mActivity)
        _ui_init()

    def load_ad(self, *args):
        if platform != 'android': return
        print(f"Attempting to load ad... (Attempt {self.retry_count + 1})")
        run_on_ui_thread(self._load_ui)()

    def _load_ui(self):
        try:
            self.rewarded = MobileAds.getRewardedVideoAdInstance(PythonActivity.mActivity)
            # We pass 'self' so the listener can call internal methods
            self.listener = PythonRewardedListener(self._internal_callbacks())
            self.rewarded.setRewardedVideoAdListener(self.listener)
            
            req = AdRequestBuilder().build()
            self.rewarded.loadAd(self.ad_unit_id, req)
        except Exception as e:
            print(f"AdMob Load Error: {e}")

    def _internal_callbacks(self):
        """Wraps user callbacks with retry logic."""
        return {
            'on_load': self._handle_load_success,
            'on_fail': self._handle_load_fail,
            'on_reward': self._handle_reward,
            'on_close': self._handle_close,
        }

# ✅ FIX — schedule cb() on the Kivy main thread
    def _handle_reward(self, reward_type,reward_amount):
        print(f"[AdMob] Reward earned: {reward_amount} {reward_type}")
        Clock.schedule_once(lambda dt: self.callbacks['on_reward'](reward_type, reward_amount))
        cb = self._pending_reward_callback
        self._pending_reward_callback = None
        if cb:
            Clock.schedule_once(lambda dt: cb())
 
    def _handle_close(self):
        """Called by AdMob when the ad is dismissed.
        The ad slot is now empty — pre-load the next one immediately.
        """
        print("[AdMob] Ad closed — reloading next ad.")
        self.callbacks['on_close']()
        # Always reload so the next show_rewarded() call has an ad ready
        Clock.schedule_once(self.load_ad, 0)

    def _handle_load_success(self):
        self.retry_count = 0  # Reset counter on success
        self.callbacks['on_load']()

    def _handle_load_fail(self, error_code):
        # Error Code 3 is NO_FILL
        if error_code == 3:
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                print(f"Error 3: No Fill. Retrying {self.retry_count}/{self.max_retries}...")
                # Wait 3 seconds before retrying to give the server a breather
                Clock.schedule_once(self.load_ad, 3)
            else:
                print("Error 3: Max retries reached.")
                self.retry_count = 0 # Reset for next manual attempt
                self.callbacks['on_exhausted']()
        else:
            # For other errors (network, etc.), just trigger the standard fail
            self.callbacks['on_fail'](error_code)

    def show_ad(self):
        if platform != 'android': return
        run_on_ui_thread(self._show_ui)()

    def show_rewarded(self, on_complete=None):
        """Show the rewarded ad.
        on_complete() fires when the user EARNS the reward (onRewarded),
        not on close — upload starts as soon as reward is granted.
        After the ad closes, a fresh ad is pre-loaded automatically.
        """
        # Store one-shot reward callback for this single show
        self._pending_reward_callback = on_complete

        if platform != 'android':
            # Desktop/dev: call immediately so the flow can be tested
            if on_complete:
                on_complete()
            return
        run_on_ui_thread(self._show_ui)()

    def init(self):
        """Call after app start to initialise AdMob and pre-load an ad."""
        if platform == 'android':
            self._init_ads()
        self.load_ad()

    def _show_ui(self):
        if self.rewarded and self.rewarded.isLoaded():
            self.rewarded.show()
        else:
            print("Ad not ready.")
# Global ad manager instance — created lazily in CricketApp.on_start()
ad_manager = None


def get_save_dir():
    try:
        from jnius import autoclass                                # type: ignore
        PA = autoclass('org.kivy.android.PythonActivity')
        p  = PA.mActivity.getFilesDir().getAbsolutePath()
        os.makedirs(p, exist_ok=True)
        return p
    except Exception:
        p = os.path.join(os.path.expanduser('~'), 'CricketArena')
        os.makedirs(p, exist_ok=True)
        return p


def request_cam_permission(callback):
    try:
        from android.permissions import (                          # type: ignore
            request_permissions, check_permission, Permission)
        if check_permission(Permission.CAMERA):
            callback(True)
        else:
            request_permissions(
                [Permission.CAMERA, Permission.RECORD_AUDIO],
                lambda p, g: callback(all(g)))
    except ImportError:
        callback(True)


def get_video_dimensions(filepath):
    """Read actual width/height from a saved video file.
    Must be called from a background thread (blocking I/O).
    Falls back to VIDEO_W/VIDEO_H if the file can't be opened."""
    cap = None
    try:
        import cv2
        if not filepath or not os.path.exists(filepath):
            return VIDEO_W, VIDEO_H
        cap = cv2.VideoCapture(filepath)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w > 0 and h > 0:
                return w, h
    except Exception as e:
        print(f"[get_video_dimensions] {e}")
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
    return VIDEO_W, VIDEO_H


def do_upload(filepath, zone_xyxy, stump_xyxy,
              status_setter, label, on_done=None):
    """Upload video + coords. Calls on_done(result_path) when complete."""
    def _run():
        try:
            import requests as req
            if not os.path.exists(filepath):
                Clock.schedule_once(
                    lambda dt: status_setter('File not found'), 0)
                return
            zx1,zy1,zx2,zy2 = zone_xyxy
            sx1,sy1,sx2,sy2 = stump_xyxy
            size_kb = os.path.getsize(filepath) // 1024
            Clock.schedule_once(
                lambda dt: status_setter(
                    f'Uploading {size_kb}KB...'), 0)
            with open(filepath, 'rb') as f:
                resp = req.post(
                    SERVER_URL,
                    files={'video': (
                        os.path.basename(filepath),
                        f, 'video/mp4')},
                    data={
                        'x1':       str(zx1), 'y1': str(zy1),
                        'x2':       str(zx2), 'y2': str(zy2),
                        'zone_x1':  str(zx1), 'zone_y1': str(zy1),
                        'zone_x2':  str(zx2), 'zone_y2': str(zy2),
                        'stump_x1': str(sx1), 'stump_y1': str(sy1),
                        'stump_x2': str(sx2), 'stump_y2': str(sy2),
                    },
                    timeout=300)
            if resp.status_code != 200:
                raise Exception(f"Server {resp.status_code}")
            save_dir    = get_save_dir()
            result_path = os.path.join(
                save_dir,
                f"{label}_result_{int(time.time())}.mp4")
            with open(result_path, 'wb') as f:
                f.write(resp.content)
            Clock.schedule_once(
                lambda dt: status_setter('Result ready ✓'), 0)
            if on_done:
                Clock.schedule_once(
                    lambda dt: on_done(result_path), 0)
        except Exception as e:
            err = str(e)
            print(f"[{label}] error: {err}")
            Clock.schedule_once(
                lambda dt: status_setter(f'Error: {err[:60]}'), 0)
    threading.Thread(target=_run, daemon=True).start()


# ── Region selector ───────────────────────────────────────────────────────
class RegionSelector(Widget):
    selecting  = BooleanProperty(False)
    has_region = BooleanProperty(False)
    _start = _end = None
    on_region_selected = None

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos): return False
        if not self.selecting: return False
        self._start = self._end = touch.pos
        self._draw(); return True

    def on_touch_move(self, touch):
        if not self.selecting or not self._start: return False
        self._end = touch.pos
        self._draw(); return True

    def on_touch_up(self, touch):
        if not self.selecting or not self._start: return False
        self._end = touch.pos
        self.selecting = False; self.has_region = True
        self._draw()
        if self.on_region_selected:
            x1=min(self._start[0],self._end[0])
            y1=min(self._start[1],self._end[1])
            x2=max(self._start[0],self._end[0])
            y2=max(self._start[1],self._end[1])
            self.on_region_selected(x1,y1,x2,y2)
        return True

    def _draw(self):
        self.canvas.clear()
        if not self._start or not self._end: return
        x1=min(self._start[0],self._end[0])
        y1=min(self._start[1],self._end[1])
        x2=max(self._start[0],self._end[0])
        y2=max(self._start[1],self._end[1])
        with self.canvas:
            Color(1,1,0,0.15)
            Rectangle(pos=(x1,y1),size=(x2-x1,y2-y1))
            Color(1,1,0,1)
            Line(rectangle=(x1,y1,x2-x1,y2-y1),width=2)

    def start_selection(self):
        self.selecting=True; self.has_region=False
        self._start=self._end=None; self.canvas.clear()

    def get_video_coords(self, vid_w, vid_h,
                         preview_w=None, preview_h=None):
        if not self.has_region or not self._start:
            return (0,0,vid_w,vid_h)
        pw=preview_w or self.width; ph=preview_h or self.height
        if pw/ph > vid_w/vid_h:
            rh=ph; rw=ph*(vid_w/vid_h); ox=(pw-rw)/2; oy=0
        else:
            rw=pw; rh=pw/(vid_w/vid_h); ox=0; oy=(ph-rh)/2
        sx=vid_w/rw; sy=vid_h/rh
        rx1=min(self._start[0],self._end[0])-ox
        ry1=min(self._start[1],self._end[1])-oy
        rx2=max(self._start[0],self._end[0])-ox
        ry2=max(self._start[1],self._end[1])-oy
        vx1=int(max(0,rx1*sx)); vy1=int(max(0,ry1*sy))
        vx2=int(min(vid_w,rx2*sx)); vy2=int(min(vid_h,ry2*sy))
        return (vx1,vid_h-vy2,vx2,vid_h-vy1)


# ── Stump selector ────────────────────────────────────────────────────────
class StumpSelector(Widget):
    has_stump    = BooleanProperty(False)
    _p1=_p2      = None
    _waiting_tap = False
    on_stump_set = None

    def start_selection(self):
        self._p1=self._p2=None
        self.has_stump=False
        self._waiting_tap=True
        self.canvas.clear()

    def on_touch_down(self, touch):
        if not self._waiting_tap: return False
        if not self.collide_point(*touch.pos): return False
        if self._p1 is None:
            self._p1=touch.pos; self._draw_dot(touch.pos); return True
        else:
            self._p2=touch.pos
            self._waiting_tap=False; self.has_stump=True
            self._draw_rect()
            if self.on_stump_set:
                x1=min(self._p1[0],self._p2[0])
                y1=min(self._p1[1],self._p2[1])
                x2=max(self._p1[0],self._p2[0])
                y2=max(self._p1[1],self._p2[1])
                self.on_stump_set(x1,y1,x2,y2)
            return True

    def _draw_dot(self, pos):
        with self.canvas:
            Color(0,0.5,1,1)
            Line(circle=(pos[0],pos[1],8),width=2)

    def _draw_rect(self):
        self.canvas.clear()
        if not self._p1 or not self._p2: return
        x1=min(self._p1[0],self._p2[0]); y1=min(self._p1[1],self._p2[1])
        x2=max(self._p1[0],self._p2[0]); y2=max(self._p1[1],self._p2[1])
        with self.canvas:
            Color(0,0.5,1,0.2)
            Rectangle(pos=(x1,y1),size=(x2-x1,y2-y1))
            Color(0,0.5,1,1)
            Line(rectangle=(x1,y1,x2-x1,y2-y1),width=2.5)

    def get_video_coords(self, vid_w, vid_h,
                         preview_w=None, preview_h=None):
        if not self.has_stump or not self._p1: return DEFAULT_STUMP
        pw=preview_w or self.width; ph=preview_h or self.height
        if pw/ph > vid_w/vid_h:
            rh=ph; rw=ph*(vid_w/vid_h); ox=(pw-rw)/2; oy=0
        else:
            rw=pw; rh=pw/(vid_w/vid_h); ox=0; oy=(ph-rh)/2
        sx=vid_w/rw; sy=vid_h/rh
        rx1=min(self._p1[0],self._p2[0])-ox
        ry1=min(self._p1[1],self._p2[1])-oy
        rx2=max(self._p1[0],self._p2[0])-ox
        ry2=max(self._p1[1],self._p2[1])-oy
        vx1=int(max(0,rx1*sx)); vy1=int(max(0,ry1*sy))
        vx2=int(min(vid_w,rx2*sx)); vy2=int(min(vid_h,ry2*sy))
        return (vx1,vid_h-vy2,vx2,vid_h-vy1)


class CricketPreview(Preview):
    filepath_callback_fn = None
    def got_filepath(self, path):
        if self.filepath_callback_fn:
            self.filepath_callback_fn(path)


KV = """
#:import NoTransition kivy.uix.screenmanager.NoTransition
#:import Clock kivy.clock.Clock

ScreenManager:
    transition: NoTransition()
    MainTabsScreen:
    MatchDetailsScreen:
    SecondaryCameraScreen:
    PracticeScreen:

<MainTabsScreen>:
    name: 'main_tabs'
    on_enter: root.on_screen_enter()
    on_leave: root.on_screen_leave()
    MDBoxLayout:
        orientation: "vertical"
        MDTopAppBar:
            title: "Cricket Arena"
            md_bg_color: 0.04, 0.25, 0.1, 1
            elevation: 4
            size_hint_y: None
            height: "56dp"
        MDBottomNavigation:
            panel_color: 0.04, 0.25, 0.1, 1
            selected_color_background: 0, 0, 0, .2
            text_color_active: 1, 0.84, 0, 1

            MDBottomNavigationItem:
                name: 'home'
                text: 'Home'
                icon: 'home'
                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.08, 0.08, 0.08, 1
                        Rectangle:
                            pos: self.pos
                            size: self.size
                    ScrollView:
                        BoxLayout:
                            orientation: 'vertical'
                            padding: "15dp"
                            spacing: "20dp"
                            size_hint_y: None
                            height: self.minimum_height
                            MDCard:
                                size_hint: 1, None
                                height: "140dp"
                                radius: [20]
                                md_bg_color: 0.12, 0.12, 0.12, 1
                                ripple_behavior: True
                                on_release: root.manager.current = 'match_details'
                                MDBoxLayout:
                                    orientation: 'vertical'
                                    padding: "20dp"
                                    MDLabel:
                                        text: "PLAY MATCH"
                                        theme_text_color: "Custom"
                                        text_color: 0.04, 0.7, 0.2, 1
                                        bold: True
                                    MDLabel:
                                        text: "Live Scoring Dashboard"
                                        theme_text_color: "Custom"
                                        text_color: 1, 1, 1, 1
                            MDCard:
                                size_hint: 1, None
                                height: "100dp"
                                radius: [20]
                                md_bg_color: 0.12, 0.12, 0.12, 1
                                on_release: root.manager.current = 'secondary_camera'
                                MDBoxLayout:
                                    padding: "15dp"
                                    spacing: "15dp"
                                    MDIcon:
                                        icon: "video-outline"
                                        theme_text_color: "Custom"
                                        text_color: 1, 0.84, 0, 1
                                        size_hint_x: None
                                        width: "40dp"
                                    MDLabel:
                                        text: "SECONDARY CAMERA"
                            MDCard:
                                size_hint: 1, None
                                height: "100dp"
                                radius: [20]
                                md_bg_color: 0.12, 0.12, 0.12, 1
                                on_release: root.manager.current = 'practice'
                                MDBoxLayout:
                                    padding: "15dp"
                                    spacing: "15dp"
                                    MDIcon:
                                        icon: "run-fast"
                                        theme_text_color: "Custom"
                                        text_color: 0.04, 0.7, 0.2, 1
                                        size_hint_x: None
                                        width: "40dp"
                                    MDLabel:
                                        text: "NET PRACTICE"

            MDBottomNavigationItem:
                name: 'tournament'
                text: 'Tournament'
                icon: 'trophy'
                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.08, 0.08, 0.08, 1
                        Rectangle:
                            pos: self.pos
                            size: self.size
                    ScrollView:
                        BoxLayout:
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height
                            padding: "10dp"
                            spacing: "15dp"
                            MDBoxLayout:
                                adaptive_height: True
                                spacing: "10dp"
                                MDLabel:
                                    text: root.tournament_name if root.tournament_name else "TOURNAMENT SETUP"
                                    halign: "center"
                                    font_style: "H6"
                                    theme_text_color: "Custom"
                                    text_color: 1, 0.84, 0, 1
                                MDIconButton:
                                    icon: "delete-forever"
                                    theme_text_color: "Error"
                                    size_hint_x: None
                                    width: "48dp"
                                    on_release: root.confirm_delete_tournament()
                            MDBoxLayout:
                                id: setup_box
                                orientation: "vertical"
                                adaptive_height: True
                                spacing: "10dp"
                                MDTextField:
                                    id: t_name_in
                                    hint_text: "Tournament Name"
                                    mode: "rectangle"
                                MDTextField:
                                    id: t_count_in
                                    hint_text: "Number of Teams"
                                    mode: "rectangle"
                                    input_filter: "int"
                                MDRaisedButton:
                                    text: "INITIALIZE TEAMS"
                                    size_hint_x: 1
                                    on_release: root.create_team_inputs(t_name_in.text, t_count_in.text)
                                MDBoxLayout:
                                    id: team_inputs_box
                                    orientation: "vertical"
                                    adaptive_height: True
                                MDRaisedButton:
                                    id: start_tourney_btn
                                    text: "START TOURNAMENT"
                                    disabled: True
                                    size_hint_x: 1
                                    on_release: root.start_league()
                            MDLabel:
                                text: root.phase_title
                                theme_text_color: "Custom"
                                text_color: 0.04, 0.7, 0.2, 1
                                halign: "center"
                                size_hint_y: None
                                height: "30dp"
                            MDBoxLayout:
                                id: match_list_box
                                orientation: "vertical"
                                adaptive_height: True
                                spacing: "10dp"
                            MDLabel:
                                text: "STANDINGS"
                                font_style: "Overline"
                                size_hint_y: None
                                height: "24dp"
                            MDBoxLayout:
                                size_hint_y: None
                                height: "220dp"
                                MDCard:
                                    padding: "5dp"
                                    md_bg_color: 0.12, 0.12, 0.12, 1
                                    ScrollView:
                                        MDGridLayout:
                                            id: points_grid
                                            cols: 6
                                            adaptive_height: True
                                            row_default_height: '40dp'
                                            row_force_default: True
                                            size_hint_x: None
                                            width: "480dp"

            MDBottomNavigationItem:
                name: 'no_ball'
                text: 'No Ball'
                icon: 'alert-circle'
                FloatLayout:
                    MDBoxLayout:
                        id: noball_cam_box
                        size_hint: 1, 1
                        pos_hint: {"x": 0, "y": 0}
                    RegionSelector:
                        id: noball_region
                        size_hint: 1, 1
                        pos_hint: {"x": 0, "y": 0}
                    StumpSelector:
                        id: noball_stump
                        size_hint: 1, 1
                        pos_hint: {"x": 0, "y": 0}
                    MDBoxLayout:
                        size_hint: 1, 1
                        pos_hint: {"x": 0, "y": 0}
                        canvas.before:
                            Color:
                                rgba: 0, 0, 0, 0.35
                            Rectangle:
                                pos: self.pos
                                size: self.size
                    MDBoxLayout:
                        orientation: 'vertical'
                        padding: "12dp"
                        spacing: "8dp"
                        size_hint: 1, 1
                        pos_hint: {"x": 0, "y": 0}
                        MDLabel:
                            text: "NO BALL REPLAY"
                            font_style: "H6"
                            theme_text_color: "Custom"
                            text_color: 1, 0.84, 0, 1
                            halign: "center"
                            size_hint_y: None
                            height: "44dp"
                        Widget:
                            size_hint_y: 1
                        MDLabel:
                            text: root.noball_rec_status
                            halign: "center"
                            theme_text_color: "Custom"
                            text_color: 0.04, 0.9, 0.3, 1
                            size_hint_y: None
                            height: "30dp"
                        MDBoxLayout:
                            size_hint_y: None
                            height: "48dp"
                            spacing: "6dp"
                            MDRaisedButton:
                                text: "START REC"
                                size_hint_x: 0.5
                                md_bg_color: 0.04, 0.7, 0.2, 1
                                on_release: root.noball_start_rec()
                            MDRaisedButton:
                                text: "STOP REC"
                                size_hint_x: 0.5
                                md_bg_color: 0.7, 0.1, 0.1, 1
                                on_release: root.noball_stop_rec()
                        MDBoxLayout:
                            size_hint_y: None
                            height: "48dp"
                            spacing: "6dp"
                            MDRaisedButton:
                                text: "SELECT ZONE"
                                size_hint_x: 0.34
                                md_bg_color: 0.2, 0.4, 0.8, 1
                                on_release: root.noball_select_zone()
                            MDRaisedButton:
                                text: "SET STUMPS"
                                size_hint_x: 0.33
                                md_bg_color: 0.1, 0.5, 0.9, 1
                                on_release: root.noball_select_stumps()
                            MDRaisedButton:
                                text: "SEND"
                                size_hint_x: 0.33
                                md_bg_color: 0.8, 0.4, 0.0, 1
                                on_release: root.noball_send()
                        MDRaisedButton:
                            text: "REPLAY RESULT"
                            size_hint: 1, None
                            height: "48dp"
                            md_bg_color: 1, 0.84, 0, 1
                            on_release: root.replay_noball()
                        MDRaisedButton:
                            text: "LIVE CAM"
                            size_hint: 1, None
                            height: "48dp"
                            md_bg_color: 0.2, 0.2, 0.8, 1
                            on_release: root.show_live_noball_camera()

            MDBottomNavigationItem:
                name: 'contact'
                text: 'Contact Us'
                icon: 'account-box'
                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: 0.08, 0.08, 0.08, 1
                        Rectangle:
                            pos: self.pos
                            size: self.size
                    ScrollView:
                        BoxLayout:
                            orientation: "vertical"
                            size_hint_y: None
                            height: self.minimum_height
                            padding: "20dp"
                            spacing: "15dp"
                            MDLabel:
                                text: "USER PROFILE"
                                font_style: "Overline"
                                theme_text_color: "Custom"
                                text_color: 0.04, 0.7, 0.2, 1
                                size_hint_y: None
                                height: "24dp"
                            MDCard:
                                adaptive_height: True
                                padding: "15dp"
                                md_bg_color: 0.12, 0.12, 0.12, 1
                                radius: [15]
                                MDBoxLayout:
                                    orientation: "vertical"
                                    adaptive_height: True
                                    MDLabel:
                                        text: "Cricket Arena"
                                        font_style: "H6"
                                        size_hint_y: None
                                        height: "36dp"
                                    MDLabel:
                                        text: "Active User"
                                        font_style: "Caption"
                                        theme_text_color: "Hint"
                                        size_hint_y: None
                                        height: "24dp"
                            MDLabel:
                                text: "SUPPORT & SOCIALS"
                                font_style: "Overline"
                                size_hint_y: None
                                height: "24dp"
                            MDRaisedButton:
                                text: "YouTube Channel"
                                size_hint_x: 1
                                md_bg_color: 0.8, 0, 0, 1
                                on_release: root.open_youtube()
                            MDRaisedButton:
                                text: "WhatsApp +91 1234567890"
                                size_hint_x: 1
                                md_bg_color: 0.15, 0.65, 0.15, 1
                                on_release: root.open_whatsapp()

<MatchDetailsScreen>:
    name: 'match_details'
    on_enter: root.on_screen_enter()
    on_leave: root.on_screen_leave()
    FloatLayout:
        MDBoxLayout:
            id: match_cam_box
            size_hint: 1, 1
            pos_hint: {"x": 0, "y": 0}
        RegionSelector:
            id: match_region
            size_hint: 1, 1
            pos_hint: {"x": 0, "y": 0}
        StumpSelector:
            id: match_stump
            size_hint: 1, 1
            pos_hint: {"x": 0, "y": 0}
        MDBoxLayout:
            size_hint: 1, 1
            pos_hint: {"x": 0, "y": 0}
            canvas.before:
                Color:
                    rgba: 0, 0, 0, 0.45
                Rectangle:
                    pos: self.pos
                    size: self.size
        MDBoxLayout:
            orientation: 'vertical'
            size_hint: 1, 1
            pos_hint: {"x": 0, "y": 0}
            MDTopAppBar:
                title: "Live Scorer"
                left_action_items: [["arrow-left", lambda x: setattr(root.manager, 'current', 'main_tabs')]]
                md_bg_color: 0.04, 0.25, 0.1, 0.9
                size_hint_y: None
                height: "56dp"
            MDBoxLayout:
                orientation: 'vertical'
                padding: "10dp"
                spacing: "5dp"
                MDBoxLayout:
                    size_hint_y: None
                    height: "80dp"
                    orientation: 'vertical'
                    MDBoxLayout:
                        size_hint_y: None
                        height: "44dp"
                        spacing: "4dp"
                        MDLabel:
                            text: "Over:"
                            size_hint_x: None
                            width: "45dp"
                            bold: True
                            color: 1,1,1,1
                        MDCard:
                            radius: [15]
                            md_bg_color: 0.1,0.1,0.1,0.85
                            MDLabel:
                                id: b1
                                halign: "center"
                        MDCard:
                            radius: [15]
                            md_bg_color: 0.1,0.1,0.1,0.85
                            MDLabel:
                                id: b2
                                halign: "center"
                        MDCard:
                            radius: [15]
                            md_bg_color: 0.1,0.1,0.1,0.85
                            MDLabel:
                                id: b3
                                halign: "center"
                        MDCard:
                            radius: [15]
                            md_bg_color: 0.1,0.1,0.1,0.85
                            MDLabel:
                                id: b4
                                halign: "center"
                        MDCard:
                            radius: [15]
                            md_bg_color: 0.1,0.1,0.1,0.85
                            MDLabel:
                                id: b5
                                halign: "center"
                        MDCard:
                            radius: [15]
                            md_bg_color: 0.1,0.1,0.1,0.85
                            MDLabel:
                                id: b6
                                halign: "center"
                    MDBoxLayout:
                        size_hint_y: None
                        height: "36dp"
                        MDLabel:
                            text: str(root.score) + "/" + str(root.wickets)
                            font_style: "H5"
                            bold: True
                            color: 1,1,1,1
                        MDLabel:
                            text: "Prev: " + root.previous_score
                            font_style: "Caption"
                            color: 0.8,0.8,0.8,1
                        MDLabel:
                            text: "Over: " + root.over_text
                            halign: "right"
                            font_style: "H6"
                            color: 1,1,1,1
                MDBoxLayout:
                    size_hint_y: None
                    height: "60dp"
                    spacing: "10dp"
                    MDIconButton:
                        icon: "minus-box"
                        on_release: root.prev_ball()
                    MDCard:
                        size_hint: None, 1
                        width: "60dp"
                        radius: [30]
                        md_bg_color: 0.04, 0.5, 0.15, 1
                        on_release: root.add_run()
                        MDLabel:
                            text: str(root.ball_number)
                            halign: "center"
                            bold: True
                    MDIconButton:
                        icon: "plus-box"
                        on_release: root.next_ball()
                MDBoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: "130dp"
                    spacing: "8dp"
                    MDTextField:
                        hint_text: "Update Striker Name"
                        mode: "rectangle"
                        size_hint_y: None
                        height: "48dp"
                        on_text_validate: root.change_striker_name(self.text); self.text = ""
                    MDBoxLayout:
                        spacing: "10dp"
                        MDCard:
                            size_hint_x: 0.65
                            radius: [15]
                            md_bg_color: 0.05,0.05,0.05,0.88
                            padding: "10dp"
                            MDBoxLayout:
                                orientation: "vertical"
                                MDLabel:
                                    text: root.striker
                                    bold: True
                                MDLabel:
                                    text: root.non_striker
                                    theme_text_color: "Hint"
                        MDBoxLayout:
                            orientation: 'vertical'
                            size_hint_x: 0.35
                            spacing: "5dp"
                            MDCard:
                                size_hint_y: None
                                height: "36dp"
                                radius: [15]
                                md_bg_color: 1, 0.84, 0, 1
                                MDLabel:
                                    text: "DRS"
                                    halign: "center"
                                    bold: True
                                    color: 0,0,0,1
                            MDRaisedButton:
                                text: "TRACKING"
                                font_size: "10sp"
                                size_hint_x: 1
                                md_bg_color: 0.04, 0.7, 0.2, 1
                MDGridLayout:
                    cols: 3
                    size_hint_y: None
                    height: "46dp"
                    spacing: "6dp"
                    MDRaisedButton:
                        text: "WIDE"
                        on_release: root.wide_ball()
                    MDRaisedButton:
                        text: "ROTATE"
                        on_release: root.rotate_strike()
                    MDRaisedButton:
                        text: "WICKET"
                        md_bg_color: 0.8, 0.1, 0.1, 1
                        on_release: root.wicket()
                MDBoxLayout:
                    size_hint_y: None
                    height: "46dp"
                    spacing: "6dp"
                    MDRaisedButton:
                        text: "OVER RESET"
                        md_bg_color: 0.4, 0.4, 0.4, 1
                        on_release: root.reset_game()
                    MDRaisedButton:
                        text: "NEXT MATCH"
                        md_bg_color: 0.8, 0.1, 0.1, 1
                        size_hint_x: 1
                        on_release: root.next_match()
                MDBoxLayout:
                    size_hint_y: None
                    height: "46dp"
                    spacing: "6dp"
                    MDRaisedButton:
                        text: "START REC"
                        size_hint_x: 0.5
                        md_bg_color: 0.04, 0.7, 0.2, 1
                        on_release: root.start_rec()
                    MDRaisedButton:
                        text: "STOP REC"
                        size_hint_x: 0.5
                        md_bg_color: 0.7, 0.1, 0.1, 1
                        on_release: root.stop_rec()
                MDBoxLayout:
                    size_hint_y: None
                    height: "46dp"
                    spacing: "6dp"
                    MDRaisedButton:
                        text: "SELECT ZONE"
                        size_hint_x: 0.34
                        md_bg_color: 0.2, 0.4, 0.8, 1
                        on_release: root.select_zone()
                    MDRaisedButton:
                        text: "SET STUMPS"
                        size_hint_x: 0.33
                        md_bg_color: 0.1, 0.5, 0.9, 1
                        on_release: root.select_stumps()
                    MDRaisedButton:
                        text: "SEND"
                        size_hint_x: 0.33
                        md_bg_color: 0.8, 0.4, 0.0, 1
                        on_release: root.send_rec()
                MDRaisedButton:
                    text: "LIVE CAM"
                    size_hint: 1, None
                    height: "46dp"
                    md_bg_color: 0.2, 0.2, 0.8, 1
                    on_release: root.show_live_match_camera()
                MDLabel:
                    text: root.match_rec_status
                    halign: "center"
                    theme_text_color: "Custom"
                    text_color: 0.04, 0.9, 0.3, 1
                    size_hint_y: None
                    height: "26dp"

<SecondaryCameraScreen>:
    name: 'secondary_camera'
    on_enter: root.on_screen_enter()
    on_leave: root.on_screen_leave()
    MDBoxLayout:
        orientation: 'vertical'
        md_bg_color: 0.05, 0.05, 0.05, 1
        MDTopAppBar:
            title: "Secondary Camera"
            left_action_items: [["arrow-left", lambda x: root.on_screen_leave() or setattr(root.manager, 'current', 'main_tabs')]]
            md_bg_color: 0.04, 0.25, 0.1, 1
            size_hint_y: None
            height: "56dp"
        FloatLayout:
            size_hint: 1, 1
            MDBoxLayout:
                id: preview_box
                size_hint: 1, 1
                pos_hint: {"x": 0, "y": 0}
            RegionSelector:
                id: sec_region
                size_hint: 1, 1
                pos_hint: {"x": 0, "y": 0}
            StumpSelector:
                id: sec_stump
                size_hint: 1, 1
                pos_hint: {"x": 0, "y": 0}
        MDLabel:
            text: root.rec_status_text
            halign: "center"
            theme_text_color: "Custom"
            text_color: 0.04, 0.9, 0.3, 1
            size_hint_y: None
            height: "34dp"
        MDBoxLayout:
            size_hint_y: None
            height: "50dp"
            spacing: "6dp"
            padding: "6dp", 0
            MDRaisedButton:
                text: "START REC"
                size_hint_x: 0.5
                md_bg_color: 0.04, 0.7, 0.2, 1
                on_release: root.start_recording()
            MDRaisedButton:
                text: "STOP REC"
                size_hint_x: 0.5
                md_bg_color: 0.7, 0.1, 0.1, 1
                on_release: root.stop_recording()
        MDBoxLayout:
            size_hint_y: None
            height: "50dp"
            spacing: "6dp"
            padding: "6dp", 0
            MDRaisedButton:
                text: "SELECT ZONE"
                size_hint_x: 0.25
                md_bg_color: 0.2, 0.4, 0.8, 1
                on_release: root.select_zone()
            MDRaisedButton:
                text: "SET STUMPS"
                size_hint_x: 0.25
                md_bg_color: 0.1, 0.5, 0.9, 1
                on_release: root.select_stumps()
            MDRaisedButton:
                text: "SEND"
                size_hint_x: 0.25
                md_bg_color: 0.8, 0.4, 0.0, 1
                on_release: root.send_to_server()
            MDRaisedButton:
                text: "LIVE CAM"
                size_hint_x: 0.25
                md_bg_color: 0.2, 0.2, 0.8, 1
                on_release: root.show_live_camera()

<PracticeScreen>:
    name: 'practice'
    on_enter: root.on_screen_enter()
    on_leave: root.on_screen_leave()
    FloatLayout:
        MDBoxLayout:
            id: practice_cam_box
            size_hint: 1, 1
            pos_hint: {"x": 0, "y": 0}
        MDBoxLayout:
            size_hint: 1, 1
            pos_hint: {"x": 0, "y": 0}
            canvas.before:
                Color:
                    rgba: 0, 0, 0, 0.42
                Rectangle:
                    pos: self.pos
                    size: self.size
        MDBoxLayout:
            orientation: 'vertical'
            size_hint: 1, 1
            pos_hint: {"x": 0, "y": 0}
            MDTopAppBar:
                title: "Net Practice"
                left_action_items: [["arrow-left", lambda x: setattr(root.manager, 'current', 'main_tabs')]]
                md_bg_color: 0.04, 0.25, 0.1, 0.88
                size_hint_y: None
                height: "56dp"
            MDBoxLayout:
                orientation: 'vertical'
                padding: "12dp"
                spacing: "10dp"
                MDLabel:
                    text: "PRACTICE TRACKER"
                    font_style: "H6"
                    theme_text_color: "Custom"
                    text_color: 0.04, 0.95, 0.3, 1
                    halign: "center"
                    size_hint_y: None
                    height: "44dp"
                Widget:
                    size_hint_y: 1
                MDLabel:
                    text: root.practice_status
                    halign: "center"
                    theme_text_color: "Custom"
                    text_color: 1, 0.84, 0, 1
                    size_hint_y: None
                    height: "36dp"
                MDBoxLayout:
                    size_hint_y: None
                    height: "56dp"
                    spacing: "10dp"
                    padding: 0, 0, 0, "6dp"
                    MDCard:
                        size_hint: None, 1
                        width: "60dp"
                        radius: [15]
                        md_bg_color: 1, 0.84, 0, 1
                        MDLabel:
                            text: "DRS"
                            halign: "center"
                            bold: True
                            color: 0, 0, 0, 1
                    MDRaisedButton:
                        text: "START TRACKING"
                        size_hint_x: 1
                        md_bg_color: 0.04, 0.7, 0.2, 1
                        on_release: root.start_tracking()
"""


# ── Camera4Kivy mixin ─────────────────────────────────────────────────────
class C4KMixin:
    _preview = None

    def _attach_preview(self, box_id, enable_video=True,
                        filepath_cb=None):
        try:
            if self._preview is not None: return
            p = CricketPreview(aspect_ratio='16:9')
            p.filepath_callback_fn = filepath_cb
            self.ids[box_id].add_widget(p)
            Clock.schedule_once(
                lambda dt: p.connect_camera(
                    camera_id='back',
                    enable_video=enable_video,
                    filepath_callback=p.got_filepath,
                    location='private'), 0.5)
            self._preview = p
        except Exception as e:
            print(f"[C4K] {e}")

    def _detach_preview(self, box_id):
        try:
            if self._preview:
                self._preview.disconnect_camera()
                self.ids[box_id].remove_widget(self._preview)
                self._preview = None
        except Exception as e:
            print(f"[C4K] detach: {e}")


# ─────────────────────────────────────────────────────────────────────────────
class MainTabsScreen(Screen):
    tournament_name   = StringProperty("")
    phase_title       = StringProperty("LEAGUE STAGE")
    active_matches    = ListProperty([])
    points_data       = DictProperty({})
    current_phase     = StringProperty("league")
    noball_rec_status = StringProperty("Ready to record")
    dialog            = None
    _noball_preview   = None
    _noball_recording = False
    _noball_saved_path= ""
    _noball_xyxy      = (0, 0, VIDEO_W, VIDEO_H)
    _noball_stump     = DEFAULT_STUMP
    _noball_result    = ""
    _noball_vid_w     = VIDEO_W
    _noball_vid_h     = VIDEO_H

    def on_screen_enter(self):
        Clock.schedule_once(lambda dt: self.load_tournament_data(), 0)
        request_cam_permission(
            lambda ok: Clock.schedule_once(
                lambda dt: self._start_noball_cam(), 0.5) if ok else None)
        self.ids.noball_region.on_region_selected = \
            self._on_noball_zone
        self.ids.noball_stump.on_stump_set = \
            self._on_noball_stump

    def on_screen_leave(self):
        self._stop_noball_playback()
        self._stop_noball_cam()

    def _start_noball_cam(self):
        try:
            if self._noball_preview is not None: return
            p = CricketPreview(aspect_ratio='16:9')
            p.filepath_callback_fn = self._on_noball_saved
            self.ids.noball_cam_box.add_widget(p)
            Clock.schedule_once(
                lambda dt: p.connect_camera(
                    camera_id='back', enable_video=True,
                    filepath_callback=p.got_filepath,
                    location='private'), 0.5)
            self._noball_preview = p
        except Exception as e:
            print(f"[NoBall] {e}")

    def _stop_noball_cam(self):
        try:
            if self._noball_preview:
                self._noball_preview.disconnect_camera()
                self.ids.noball_cam_box.remove_widget(
                    self._noball_preview)
                self._noball_preview = None
        except Exception as e:
            print(f"[NoBall stop] {e}")

    def noball_start_rec(self):
        if self._noball_recording:
            self.noball_rec_status = "Already recording..."; return
        if self._noball_preview is None:
            self.noball_rec_status = "Camera not ready."; return
        try:
            self._noball_preview.capture_video(
                location='private',
                name=f"noball_{int(time.time())}")
            self._noball_recording = True
            self.noball_rec_status = "● REC..."
        except Exception as e:
            self.noball_rec_status = f"Error: {e}"

    def noball_stop_rec(self):
        if not self._noball_recording:
            self.noball_rec_status = "Not recording."; return
        try:
            self._noball_preview.stop_capture_video()
            self._noball_recording = False
            self.noball_rec_status = "Stopped. Set zone/stumps & SEND."
        except Exception as e:
            self.noball_rec_status = f"Stop error: {e}"

    def _on_noball_saved(self, path):
        self._noball_saved_path = path
        self._noball_recording  = False
        Clock.schedule_once(lambda dt: self._read_noball_dims(path), 0)
        Clock.schedule_once(lambda dt: setattr(
            self, 'noball_rec_status',
            'Saved. Set zone/stumps & SEND.'), 0)

    def _read_noball_dims(self, path):
        """Read video dimensions off the main thread to avoid ANR/freeze."""
        def _worker():
            w, h = VIDEO_W, VIDEO_H
            try:
                prev_size = -1
                for _ in range(5):
                    if not os.path.exists(path):
                        time.sleep(1.0); continue
                    cur_size = os.path.getsize(path)
                    if cur_size > 0 and cur_size == prev_size:
                        break
                    prev_size = cur_size
                    time.sleep(1.0)
                w, h = get_video_dimensions(path)
            except Exception as e:
                print(f"[NoBall] _read_noball_dims error: {e}")
            def _apply(dt):
                try:
                    self._noball_vid_w, self._noball_vid_h = w, h
                    print(f"[NoBall] Video dims set: {w}x{h}")
                except Exception as ae:
                    print(f"[NoBall] _apply dims error: {ae}")
            Clock.schedule_once(_apply, 0)
        threading.Thread(target=_worker, daemon=True).start()

    def noball_select_zone(self):
        self.ids.noball_region.start_selection()
        self.noball_rec_status = "Drag to select tracking zone..."

    def _on_noball_zone(self, x1, y1, x2, y2):
        rs = self.ids.noball_region
        vc = rs.get_video_coords(self._noball_vid_w, self._noball_vid_h, rs.width, rs.height)
        self._noball_xyxy = vc
        self.noball_rec_status = (
            f"Zone set. Now set stumps.")

    def noball_select_stumps(self):
        self.ids.noball_stump.start_selection()
        self.noball_rec_status = \
            "Tap top-left then bottom-right of stumps..."

    def _on_noball_stump(self, x1, y1, x2, y2):
        rs = self.ids.noball_stump
        vc = rs.get_video_coords(self._noball_vid_w, self._noball_vid_h, rs.width, rs.height)
        self._noball_stump = vc
        self.noball_rec_status = "Stumps set. Tap SEND."

    def noball_send(self):
        if not self._noball_saved_path:
            self.noball_rec_status = "No file. Record first."; return
        if not os.path.exists(self._noball_saved_path):
            self.noball_rec_status = "File missing. Record again."; return
        self.noball_rec_status = "Showing ad..."
        # ── Show rewarded ad THEN upload ──────────────────────────────
        if ad_manager:
            ad_manager.show_rewarded(self._do_noball_upload)  # Bug 4 fix: use global, not new instance
        else:
            self._do_noball_upload()

    def _do_noball_upload(self):
        """Called after ad closes."""
        self.noball_rec_status = "Uploading..."
        do_upload(
            self._noball_saved_path,
            self._noball_xyxy,
            self._noball_stump,
            lambda msg: setattr(self, 'noball_rec_status', msg),
            'noball',
            on_done=self._on_noball_result)

    _noball_play_event = None
    _noball_play_cap   = None
    _noball_result_img = None

    def _on_noball_result(self, result_path):
        self._noball_result = result_path
        self.noball_rec_status = "Result ready! Tap REPLAY."

    def replay_noball(self):
        if not self._noball_result or \
                not os.path.exists(self._noball_result):
            self.noball_rec_status = "No result yet. Send first."
            return
        try:
            import cv2
            # Stop any existing playback
            self._stop_noball_playback()
            # Pause live camera
            if self._noball_preview:
                try: self._noball_preview.disconnect_camera()
                except Exception: pass
                self._noball_preview = None
            img = KivyImage(
                size_hint=(1, 1),
                allow_stretch=True,
                keep_ratio=True)
            self.ids.noball_cam_box.clear_widgets()
            self.ids.noball_cam_box.add_widget(img)
            self._noball_result_img = img
            cap = cv2.VideoCapture(self._noball_result)
            if not cap.isOpened():
                self.noball_rec_status = "Cannot open result."; return
            fps = cap.get(cv2.CAP_PROP_FPS) or 24
            self._noball_play_cap   = cap
            self.noball_rec_status  = "▶ Playing result..."
            self._noball_play_event = Clock.schedule_interval(
                self._noball_next_frame, 1.0 / fps)
        except Exception as e:
            self.noball_rec_status = f"Playback error: {e}"

    def _noball_next_frame(self, dt):
        try:
            import cv2
            if self._noball_play_cap is None: return
            ret, frame = self._noball_play_cap.read()
            if not ret:
                self._noball_play_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._noball_play_cap.read()
                if not ret: return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb = cv2.flip(rgb, 0)
            h, w = rgb.shape[:2]
            tex = Texture.create(size=(w, h), colorfmt='rgb')
            tex.blit_buffer(rgb.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
            if self._noball_result_img:
                self._noball_result_img.texture = tex
        except Exception as e:
            print(f"[NoBallPlay] {e}")

    def _stop_noball_playback(self):
        if self._noball_play_event:
            self._noball_play_event.cancel()
            self._noball_play_event = None
        if self._noball_play_cap:
            self._noball_play_cap.release()
            self._noball_play_cap = None
        self._noball_result_img = None

    def show_live_noball_camera(self):
        """Restore live camera in No Ball tab after result playback."""
        self._stop_noball_playback()
        self.ids.noball_cam_box.clear_widgets()
        self._noball_preview = None
        Clock.schedule_once(lambda dt: self._start_noball_cam(), 0.2)

    def open_youtube(self):
        webbrowser.open("https://www.youtube.com/@YourChannelName")

    def open_whatsapp(self):
        webbrowser.open("https://wa.me/911234567890")

    def load_tournament_data(self):
        try:
            if store.exists('active_tournament'):
                data = store.get('active_tournament')
                self.tournament_name = data['name']
                self.active_matches  = data['matches']
                self.points_data     = data['points']
                self.current_phase   = data['phase']
                self.phase_title     = data['phase_title']
                self.ids.setup_box.opacity  = 0
                self.ids.setup_box.disabled = True
                self.refresh_ui()
        except Exception as e:
            print(f"[load] {e}")

    def save_tournament_data(self):
        store.put('active_tournament',
                  name=self.tournament_name,
                  matches=self.active_matches,
                  points=self.points_data,
                  phase=self.current_phase,
                  phase_title=self.phase_title)

    def confirm_delete_tournament(self):
        self.dialog = MDDialog(
            title="Delete Tournament?",
            text="This will wipe all standings and match history.",
            buttons=[
                MDFlatButton(text="CANCEL",
                    on_release=lambda x: self.dialog.dismiss()),
                MDRaisedButton(text="DELETE",
                    md_bg_color=(1,0,0,1),
                    on_release=self.delete_tournament)])
        self.dialog.open()

    def delete_tournament(self, *args):
        if store.exists('active_tournament'):
            store.delete('active_tournament')
        self.tournament_name=""
        self.active_matches=[]
        self.points_data={}
        self.current_phase="league"
        self.phase_title="LEAGUE STAGE"
        self.ids.setup_box.opacity=1
        self.ids.setup_box.disabled=False
        self.ids.match_list_box.clear_widgets()
        self.ids.points_grid.clear_widgets()
        self.dialog.dismiss()

    def create_team_inputs(self, name, count):
        if not name or not count: return
        self.tournament_name = name
        self.ids.team_inputs_box.clear_widgets()
        for i in range(int(count)):
            self.ids.team_inputs_box.add_widget(
                MDTextField(hint_text=f"Team {i+1} Name"))
        self.ids.start_tourney_btn.disabled = False

    def start_league(self):
        teams = [c.text if c.text else f"T{i+1}"
                 for i, c in enumerate(
                     self.ids.team_inputs_box.children[::-1])]
        self.points_data = {t: [0,0,0,0,0.0] for t in teams}
        self.ids.setup_box.opacity=0
        self.ids.setup_box.disabled=True
        self.active_matches = [
            [p[0],p[1],"Pending"]
            for p in itertools.combinations(teams, 2)]
        self.save_tournament_data()
        self.refresh_ui()

    def refresh_ui(self):
        self.ids.match_list_box.clear_widgets()
        for i, m in enumerate(self.active_matches):
            row = MDBoxLayout(adaptive_height=True, spacing="10dp")
            row.add_widget(MDLabel(
                text=f"{m[0]} vs {m[1]}", font_style="Caption"))
            if m[2] == "Pending":
                row.add_widget(MDRaisedButton(
                    text="SET WIN",
                    on_release=lambda x, idx=i:
                        self.open_result_dialog(idx)))
            else:
                row.add_widget(MDLabel(
                    text=f"Winner: {m[2]}",
                    theme_text_color="Custom",
                    text_color=(1,0.8,0,1)))
            self.ids.match_list_box.add_widget(row)
        self.ids.points_grid.clear_widgets()
        for h in ["Team","P","W","L","Pts","NRR"]:
            self.ids.points_grid.add_widget(MDLabel(
                text=h, bold=True, halign="center",
                font_style="Caption"))
        for team, s in sorted(
                self.points_data.items(),
                key=lambda x: (x[1][3], x[1][4]), reverse=True):
            self.ids.points_grid.add_widget(MDLabel(
                text=team[:10], halign="center",
                font_style="Caption"))
            for val in s:
                self.ids.points_grid.add_widget(MDLabel(
                    text=f"{val:.2f}" if isinstance(val, float)
                         else str(val),
                    halign="center", font_style="Caption"))

    def open_result_dialog(self, idx):
        m = self.active_matches[idx]
        content = MDBoxLayout(orientation="vertical",
                              spacing="10dp", adaptive_height=True)
        self.win_field    = MDTextField(
            hint_text=f"Winner ({m[0]}/{m[1]})")
        self.margin_field = MDTextField(
            hint_text="Margin Number", input_filter="int")
        self.type_field   = MDTextField(
            hint_text="'runs' or 'wickets'")
        for w in [self.win_field, self.margin_field, self.type_field]:
            content.add_widget(w)
        self.dialog = MDDialog(
            title="Enter Match Result", type="custom",
            content_cls=content,
            buttons=[MDFlatButton(
                text="SUBMIT",
                on_release=lambda x: self.process_result(idx))])
        self.dialog.open()

    def process_result(self, idx):
        winner = self.win_field.text.strip()
        m = self.active_matches[idx]
        if winner not in [m[0], m[1]]: return
        loser = m[0] if winner == m[1] else m[1]
        try:
            margin   = int(self.margin_field.text)
            m_type   = self.type_field.text.lower()
            nrr_gain = margin/10.0 if "run" in m_type else float(margin)
            self.active_matches[idx][2] = winner
            if self.current_phase == "league":
                self.points_data[winner][0]+=1
                self.points_data[winner][1]+=1
                self.points_data[winner][3]+=2
                self.points_data[loser][0]+=1
                self.points_data[loser][2]+=1
                self.points_data[winner][4]+=nrr_gain
                self.points_data[loser][4]-=nrr_gain
            self.save_tournament_data()
            self.dialog.dismiss()
            self.refresh_ui()
            self.check_progression()
        except Exception as e:
            print(f"[result] {e}")

    def check_progression(self):
        if all(m[2] != "Pending" for m in self.active_matches):
            if self.current_phase == "league": self.setup_semis()
            elif self.current_phase == "semis": self.setup_final()
            self.save_tournament_data()

    def setup_semis(self):
        t = [x[0] for x in sorted(
            self.points_data.items(),
            key=lambda x: (x[1][3], x[1][4]), reverse=True)[:4]]
        if len(t) < 4: self.setup_final(); return
        self.active_matches = [
            [t[0],t[3],"Pending"],[t[1],t[2],"Pending"]]
        self.current_phase="semis"
        self.phase_title="SEMI-FINALS"
        self.refresh_ui()

    def setup_final(self):
        winners = ([m[2] for m in self.active_matches]
                   if self.current_phase == "semis"
                   else list(self.points_data.keys())[:2])
        self.active_matches = [[winners[0],winners[1],"Pending"]]
        self.current_phase="final"
        self.phase_title="GRAND FINAL"
        self.refresh_ui()


# ─────────────────────────────────────────────────────────────────────────────
class MatchDetailsScreen(C4KMixin, Screen):
    score             = NumericProperty(0)
    wickets           = NumericProperty(0)
    previous_score    = StringProperty("N/A")
    over              = NumericProperty(0)
    ball_in_over      = NumericProperty(0)
    over_text         = StringProperty("0.0")
    ball_number       = NumericProperty(0)
    striker_name      = StringProperty("Batsman 1")
    non_striker_name  = StringProperty("Batsman 2")
    striker_runs      = NumericProperty(0)
    non_striker_runs  = NumericProperty(0)
    striker_balls     = NumericProperty(0)
    non_striker_balls = NumericProperty(0)
    striker           = StringProperty("Batsman 1 - 0 (0)")
    non_striker       = StringProperty("Batsman 2 - 0 (0)")
    match_rec_status  = StringProperty("Ready to record")
    _match_recording  = False
    _match_saved_path = ""
    _match_xyxy       = (0, 0, VIDEO_W, VIDEO_H)
    _match_stump_xyxy = DEFAULT_STUMP
    # Ad tracking — show ad every 6 balls
    _balls_since_ad    = 0
    # Result playback state
    _match_result_path = ""
    _match_play_event  = None
    _match_play_cap    = None
    _match_result_img  = None
    _match_vid_w       = VIDEO_W
    _match_vid_h       = VIDEO_H

    def on_screen_enter(self):
        request_cam_permission(
            lambda ok: Clock.schedule_once(
                lambda dt: self._attach_preview(
                    'match_cam_box',
                    enable_video=True,
                    filepath_cb=self._on_match_saved), 0.3)
            if ok else None)
        self.ids.match_region.on_region_selected = \
            self._on_zone_selected
        self.ids.match_stump.on_stump_set = \
            self._on_stump_selected

    def on_screen_leave(self):
        self._stop_match_playback()
        self._detach_preview('match_cam_box')

    def select_zone(self):
        self.ids.match_region.start_selection()
        self.match_rec_status = "Drag to select tracking zone..."

    def _on_zone_selected(self, x1, y1, x2, y2):
        rs = self.ids.match_region
        vc = rs.get_video_coords(self._match_vid_w, self._match_vid_h, rs.width, rs.height)
        self._match_xyxy = vc
        self.match_rec_status = "Zone set. Set stumps."

    def select_stumps(self):
        self.ids.match_stump.start_selection()
        self.match_rec_status = \
            "Tap top-left then bottom-right of stumps..."

    def _on_stump_selected(self, x1, y1, x2, y2):
        rs = self.ids.match_stump
        vc = rs.get_video_coords(self._match_vid_w, self._match_vid_h, rs.width, rs.height)
        self._match_stump_xyxy = vc
        self.match_rec_status  = "Stumps set. Tap SEND."

    def start_rec(self):
        if self._match_recording:
            self.match_rec_status = "Already recording..."; return
        if self._preview is None:
            self.match_rec_status = "Camera not ready."; return
        try:
            self._preview.capture_video(
                location='private',
                name=f"match_{int(time.time())}")
            self._match_recording = True
            self.match_rec_status = "● REC..."
        except Exception as e:
            self.match_rec_status = f"Error: {e}"

    def stop_rec(self):
        if not self._match_recording:
            self.match_rec_status = "Not recording."; return
        try:
            self._preview.stop_capture_video()
            self._match_recording = False
            self.match_rec_status = "Stopped. Tap SEND."
        except Exception as e:
            self.match_rec_status = f"Stop error: {e}"
    def _on_match_saved(self, path):
        self._match_saved_path = path
        self._match_recording  = False
        Clock.schedule_once(lambda dt: self._read_match_dims(path), 0)
        Clock.schedule_once(lambda dt: setattr(
            self, 'match_rec_status',
            'Saved. Set zone/stumps & SEND.'), 0)

    def _read_match_dims(self, path):
        """Read video dimensions off the main thread to avoid ANR/freeze."""
        def _worker():
            w, h = VIDEO_W, VIDEO_H
            try:
                prev_size = -1
                for _ in range(5):
                    if not os.path.exists(path):
                        time.sleep(1.0); continue
                    cur_size = os.path.getsize(path)
                    if cur_size > 0 and cur_size == prev_size:
                        break
                    prev_size = cur_size
                    time.sleep(1.0)
                w, h = get_video_dimensions(path)
            except Exception as e:
                print(f"[Match] _read_match_dims error: {e}")
            def _apply(dt):
                try:
                    self._match_vid_w, self._match_vid_h = w, h
                    print(f"[Match] Video dims set: {w}x{h}")
                except Exception as ae:
                    print(f"[Match] _apply dims error: {ae}")
            Clock.schedule_once(_apply, 0)
        threading.Thread(target=_worker, daemon=True).start()

    def send_rec(self):
        if not self._match_saved_path or not os.path.exists(self._match_saved_path):
            self.match_rec_status = "No recording found. Record first."
            return

        def start_upload():
            do_upload(
                self._match_saved_path,
                self._match_xyxy,
                self._match_stump_xyxy,
                lambda t: setattr(self, 'match_rec_status', t),  # Bug 2 fix: correct property name
                "MATCH_CAM",
                on_done=self._play_match_result           # Bug 3 fix: pass reference, don't call ()
            )

        self.match_rec_status = "Watch ad to upload..."   # Bug 2 fix: correct property name
        if ad_manager:
            ad_manager.show_rewarded(on_complete=start_upload)
        else:
            start_upload()


    def on_upload_done(self, result_path):
        self.match_rec_status = "Upload Complete!"
    def _play_match_result(self, path):
        """Download complete — play result video in the match_cam_box."""
        self._match_result_path = path
        try:
            import cv2
            # Stop and detach the live camera
            self._stop_match_playback()
            if self._preview:
                try: self._preview.disconnect_camera()
                except Exception: pass
                self._preview = None
            img = KivyImage(
                size_hint=(1, 1),
                allow_stretch=True,
                keep_ratio=True)
            self.ids.match_cam_box.clear_widgets()
            self.ids.match_cam_box.add_widget(img)
            self._match_result_img = img
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                self.match_rec_status = "Cannot open result."; return
            fps = cap.get(cv2.CAP_PROP_FPS) or 24
            self._match_play_cap   = cap
            self.match_rec_status  = "▶ Playing result..."
            self._match_play_event = Clock.schedule_interval(
                self._match_next_frame, 1.0 / fps)
        except Exception as e:
            self.match_rec_status = f"Playback error: {e}"

    def _match_next_frame(self, dt):
        try:
            import cv2, numpy as np
            if self._match_play_cap is None: return
            ret, frame = self._match_play_cap.read()
            if not ret:
                self._match_play_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._match_play_cap.read()
                if not ret: return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb = cv2.flip(rgb, 0)
            h, w = rgb.shape[:2]
            tex = Texture.create(size=(w, h), colorfmt='rgb')
            tex.blit_buffer(rgb.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
            if self._match_result_img:
                self._match_result_img.texture = tex
        except Exception as e:
            print(f"[MatchPlay] {e}")

    def _stop_match_playback(self):
        if self._match_play_event:
            self._match_play_event.cancel()
            self._match_play_event = None
        if self._match_play_cap:
            self._match_play_cap.release()
            self._match_play_cap = None
        self._match_result_img = None

    def show_live_match_camera(self):
        """Restore live camera after watching result."""
        self._stop_match_playback()
        self.ids.match_cam_box.clear_widgets()
        self._preview = None
        Clock.schedule_once(
            lambda dt: self._attach_preview(
                'match_cam_box',
                enable_video=True,
                filepath_cb=self._on_match_saved), 0.2)

    # ── Scoring with 6-ball ad trigger ───────────────────────────────
    def _increment_ball(self, val):
        bid = f"b{self.ball_in_over+1}"
        if bid in self.ids: self.ids[bid].text = val
        if self.ball_in_over < 5:
            self.ball_in_over += 1
        else:
            self.over+=1; self.ball_in_over=0
            Clock.schedule_once(self.clear_over_boxes, 1.0)
            # ── Show ad every over (6 balls) ──────────────────────────
            self._balls_since_ad += 6
            if self._balls_since_ad >= 6:
                self._balls_since_ad = 0
                if ad_manager:
                    Clock.schedule_once(
                        lambda dt: ad_manager.show_rewarded(None), 1.2)  # Bug 4 fix: use global
        self.over_text = f"{self.over}.{self.ball_in_over}"

    def update_batsman_text(self):
        self.striker = (f"{self.striker_name} - "
                        f"{self.striker_runs} ({self.striker_balls})")
        self.non_striker = (f"{self.non_striker_name} - "
                            f"{self.non_striker_runs} "
                            f"({self.non_striker_balls})")

    def change_striker_name(self, name):
        if name.strip():
            self.striker_name=name; self.update_batsman_text()

    def add_run(self):
        run = self.ball_number
        self.score+=run; self.striker_runs+=run; self.striker_balls+=1
        self.update_batsman_text(); self._increment_ball(str(run))

    def clear_over_boxes(self, dt):
        for i in range(1,7): self.ids[f"b{i}"].text = ""

    def wide_ball(self): self.score += 1

    def wicket(self):
        self.wickets+=1; self.striker_balls+=1
        self._increment_ball("W"); self.update_batsman_text()

    def rotate_strike(self):
        (self.striker_name, self.non_striker_name) = \
            (self.non_striker_name, self.striker_name)
        (self.striker_runs, self.non_striker_runs) = \
            (self.non_striker_runs, self.striker_runs)
        (self.striker_balls, self.non_striker_balls) = \
            (self.non_striker_balls, self.striker_balls)
        self.update_batsman_text()

    def next_ball(self):
        if self.ball_number < 6: self.ball_number += 1

    def prev_ball(self):
        if self.ball_number > 0: self.ball_number -= 1

    def reset_game(self):
        self.previous_score = (f"{self.score}/{self.wickets} "
                               f"({self.over_text})")
        self.score=self.wickets=self.over=\
            self.ball_in_over=self.ball_number=0
        self.striker_runs=self.non_striker_runs=\
            self.striker_balls=self.non_striker_balls=0
        self.over_text="0.0"; self.update_batsman_text()
        self.clear_over_boxes(0)

    def next_match(self):
        self.reset_game(); self.previous_score="N/A"


# ─────────────────────────────────────────────────────────────────────────────
class SecondaryCameraScreen(Screen):

    rec_status_text  = StringProperty("Initializing...")
    _preview         = None
    _recording       = False
    _saved_path      = ""
    _rec_name        = ""
    _waiting_for_save = False
    _xyxy            = (0, 0, VIDEO_W, VIDEO_H)
    _stump_xyxy      = DEFAULT_STUMP
    _result_path     = ""
    _play_event      = None
    _play_cap        = None
    _result_image    = None
    _balls_recorded  = 0
    _vid_w           = VIDEO_W
    _vid_h           = VIDEO_H
    _active          = False
    

    def on_screen_enter(self):
        self._active = True
        request_cam_permission(
            lambda ok: Clock.schedule_once(
                lambda dt: self._start_preview(), 0.5)
            if ok else setattr(
                self, 'rec_status_text', 'Permission denied.'))
        self.ids.sec_region.on_region_selected = \
            self._on_zone_selected
        self.ids.sec_stump.on_stump_set = \
            self._on_stump_selected

    def _start_preview(self):
        try:
            if self._preview is not None: return
            p = CricketPreview(aspect_ratio='16:9')
            p.filepath_callback_fn = self._on_video_saved
            self.ids.preview_box.add_widget(p)
            Clock.schedule_once(
                lambda dt: p.connect_camera(
                    camera_id='back', enable_video=True,
                    filepath_callback=p.got_filepath,
                    location='private'), 0.5)
            self._preview = p
            self.rec_status_text = "Preview ready."
        except Exception as e:
            self.rec_status_text = f"Error: {e}"

    def select_zone(self):
        self.ids.sec_region.start_selection()
        self.rec_status_text = "Drag to select tracking zone..."

    def _on_zone_selected(self, x1, y1, x2, y2):
        rs = self.ids.sec_region
        vc = rs.get_video_coords(self._vid_w, self._vid_h, rs.width, rs.height)
        self._xyxy = vc
        self.rec_status_text = "Zone set."

    def select_stumps(self):
        self.ids.sec_stump.start_selection()
        self.rec_status_text = \
            "Tap top-left then bottom-right of stumps..."

    def _on_stump_selected(self, x1, y1, x2, y2):
        rs = self.ids.sec_stump
        vc = rs.get_video_coords(self._vid_w, self._vid_h, rs.width, rs.height)
        self._stump_xyxy = vc
        self.rec_status_text = "Stumps set."

    def start_recording(self):
        if self._recording:
            self.rec_status_text = "Already recording..."; return
        if self._preview is None:
            self.rec_status_text = "Camera not ready."; return
        try:
            self._rec_name = f"rec_{int(time.time())}"
            self._saved_path = ""
            self._waiting_for_save = False
            self._preview.capture_video(
                location='private',
                name=self._rec_name)
            self._recording      = True
            self._balls_recorded = 0
            self.rec_status_text = "● REC..."
            self._start_six_ball_timer()
        except Exception as e:
            self.rec_status_text = f"Error: {e}"

    def _start_six_ball_timer(self):
        """Schedule ad check every ~5s (approx 1 ball interval)."""
        if hasattr(self, '_ball_timer') and self._ball_timer:
            self._ball_timer.cancel()
        self._ball_timer = Clock.schedule_interval(
            self._count_ball, 5.0)

    def _count_ball(self, dt):
        if not self._recording:
            if hasattr(self, '_ball_timer') and self._ball_timer:
                self._ball_timer.cancel()
            return
        self._balls_recorded += 1
        if self._balls_recorded >= 6:
            self._balls_recorded = 0
            if ad_manager:
                ad_manager.show_rewarded(None)  # Bug 4 fix: use global ad_manager, not new AdManager()

    def stop_recording(self):
        if not self._recording:
            self.rec_status_text = "Not recording."; return
        try:
            if hasattr(self, '_ball_timer') and self._ball_timer:
                self._ball_timer.cancel()
                self._ball_timer = None
            self._preview.stop_capture_video()
            self._recording = False
            self._waiting_for_save = True
            self.rec_status_text = "Saving... please wait before sending."
        except Exception as e:
            self.rec_status_text = f"Stop error: {e}"

    def _on_video_saved(self, path):
        def _main_thread_handler(dt):
            self._waiting_for_save = False
            if not path:
                self._recording = False
                self.rec_status_text = 'Save failed: camera returned no path.'
                return
            self._saved_path = path
            self._recording  = False
            if self._active:
                self.rec_status_text = 'Saved. Set zone/stumps & SEND.'
                self._read_vid_dims(path)
        Clock.schedule_once(_main_thread_handler, 0)

    def _read_vid_dims(self, path):
        """Read video dimensions OFF the main thread to avoid ANR/freeze.
        Retries up to 5 times (1 s apart) waiting for the file to be
        fully written before handing the result back to the main thread."""
        def _worker():
            w, h = VIDEO_W, VIDEO_H          # safe fallback
            try:
                # Wait until the file exists and has a stable size
                prev_size = -1
                for attempt in range(5):
                    if not os.path.exists(path):
                        time.sleep(1.0)
                        continue
                    cur_size = os.path.getsize(path)
                    if cur_size > 0 and cur_size == prev_size:
                        break          # file is no longer growing — safe to read
                    prev_size = cur_size
                    time.sleep(1.0)

                # Now try to read dims with cv2
                try:
                    import cv2
                    cap = cv2.VideoCapture(path)
                    if cap.isOpened():
                        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        cap.release()
                        if fw > 0 and fh > 0:
                            w, h = fw, fh
                except Exception as cv_err:
                    print(f"[SecCam] cv2 dims error: {cv_err}")
            except Exception as e:
                print(f"[SecCam] _read_vid_dims worker error: {e}")

            # Marshal result back to main thread safely
            def _apply(dt):
                try:
                    if self._active:
                        self._vid_w, self._vid_h = w, h
                        print(f"[SecCam] Video dims set: {w}x{h}")
                except Exception as apply_err:
                    print(f"[SecCam] _apply dims error: {apply_err}")
            Clock.schedule_once(_apply, 0)

        threading.Thread(target=_worker, daemon=True).start()

    def _find_latest_video(self):
        """Search all known private storage directories for the most recent
        video file matching our recording name or any recent video."""
        import glob as _glob
        search_dirs = set()

        search_dirs.add(get_save_dir())

        try:
            from jnius import autoclass
            PA = autoclass('org.kivy.android.PythonActivity')
            activity = PA.mActivity
            for d in [
                activity.getFilesDir(),
                activity.getCacheDir(),
                activity.getExternalFilesDir(None),
            ]:
                if d is not None:
                    search_dirs.add(d.getAbsolutePath())
                    for sub in ('private', 'videos', 'mov', ''):
                        p = os.path.join(d.getAbsolutePath(), sub)
                        if os.path.isdir(p):
                            search_dirs.add(p)
        except Exception:
            pass

        home = os.path.expanduser('~')
        for sub in ('CricketArena', 'private', ''):
            p = os.path.join(home, sub)
            if os.path.isdir(p):
                search_dirs.add(p)

        candidates = []
        for d in search_dirs:
            for ext in ('*.mp4', '*.mov', '*.3gp', '*.mkv', '*.avi'):
                candidates.extend(_glob.glob(os.path.join(d, ext)))

        if not candidates:
            return None

        rec_name = getattr(self, '_rec_name', '')
        if rec_name:
            name_matches = [f for f in candidates
                            if rec_name in os.path.basename(f)]
            if name_matches:
                return max(name_matches, key=os.path.getmtime)

        return max(candidates, key=os.path.getmtime)

    def send_to_server(self):
        if getattr(self, '_waiting_for_save', False):
            self.rec_status_text = "Still saving... please wait a moment."
            return

        if not self._saved_path or not os.path.exists(self._saved_path):
            found = self._find_latest_video()
            if found:
                self._saved_path = found
                self.rec_status_text = f"Using: {os.path.basename(found)}"
            else:
                save_dir = get_save_dir()
                self.rec_status_text = (
                    "No recording found. Record and stop first. "
                    f"(Searched: {save_dir})"
                )
                return

        final_path = self._saved_path

        def start_upload():
            do_upload(
                final_path,
                self._xyxy,
                self._stump_xyxy,
                lambda t: setattr(self, 'rec_status_text', t),
                "SEC_CAM",
                on_done=self._play_result
            )

        self.rec_status_text = "Watch ad to upload..."
        if ad_manager:
            ad_manager.show_rewarded(on_complete=start_upload)
        else:
            start_upload()

    def _do_upload(self):
        self.rec_status_text = "Uploading..."
        do_upload(
            self._saved_path,
            self._xyxy,
            self._stump_xyxy,
            lambda msg: setattr(self, 'rec_status_text', msg),
            'secondary',
            on_done=self._play_result)

    def _play_result(self, path):
        try:
            import cv2
            if self._preview:
                self._preview.disconnect_camera()
            img = KivyImage(
                size_hint=(1,1),
                allow_stretch=True,
                keep_ratio=True)
            self.ids.preview_box.clear_widgets()
            self.ids.preview_box.add_widget(img)
            self._result_image = img
            self._preview = None
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                self.rec_status_text = "Cannot open result."; return
            fps = cap.get(cv2.CAP_PROP_FPS) or 24
            self._play_cap       = cap
            self.rec_status_text = "▶ Playing result..."
            self._play_event     = Clock.schedule_interval(
                self._next_frame, 1.0/fps)
        except Exception as e:
            self.rec_status_text = f"Playback error: {e}"

    def _next_frame(self, dt):
        try:
            import cv2, numpy as np
            if self._play_cap is None: return
            ret, frame = self._play_cap.read()
            if not ret:
                self._play_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._play_cap.read()
                if not ret: return
            rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb  = cv2.flip(rgb, 0)
            h, w = rgb.shape[:2]
            tex  = Texture.create(size=(w,h), colorfmt='rgb')
            tex.blit_buffer(rgb.tobytes(),
                            colorfmt='rgb', bufferfmt='ubyte')
            if self._result_image:
                self._result_image.texture = tex
        except Exception as e:
            print(f"[Play] {e}")

    def show_live_camera(self):
        if self._play_event:
            self._play_event.cancel(); self._play_event = None
        if self._play_cap:
            self._play_cap.release(); self._play_cap = None
        self.ids.preview_box.clear_widgets()
        self._preview = None
        Clock.schedule_once(lambda dt: self._start_preview(), 0.2)

    def on_screen_leave(self):
        self._active = False
        self._recording = False
        self._waiting_for_save = False
        if hasattr(self, '_ball_timer') and self._ball_timer:
            self._ball_timer.cancel()
        if self._play_event:
            self._play_event.cancel(); self._play_event = None
        if self._play_cap:
            self._play_cap.release(); self._play_cap = None
        if self._preview:
            try: self._preview.disconnect_camera()
            except Exception: pass
            self._preview = None
        self.ids.preview_box.clear_widgets()
        self.rec_status_text = "Initializing..."


# ─────────────────────────────────────────────────────────────────────────────
class PracticeScreen(C4KMixin, Screen):
    practice_status = StringProperty("Press START TRACKING")

    def on_screen_enter(self):
        request_cam_permission(
            lambda ok: Clock.schedule_once(
                lambda dt: self._attach_preview(
                    'practice_cam_box',
                    enable_video=False), 0.3)
            if ok else None)

    def on_screen_leave(self):
        self._detach_preview('practice_cam_box')

    def start_tracking(self):
        self.practice_status = "● Tracking active..."


# ─────────────────────────────────────────────────────────────────────────────
class CricketApp(MDApp):
    def build(self):
        self.theme_cls.theme_style     = "Dark"
        self.theme_cls.primary_palette = "Green"
        return Builder.load_string(KV)

    def on_start(self):
        global ad_manager
        request_cam_permission(lambda ok: None)
        # Create and init AdMob after app starts
        ad_manager = AdManager(
            ad_unit_id=REWARDED_AD_ID,
            on_reward=lambda t, a: print(f"User rewarded: {a} {t}"),
        )
        Clock.schedule_once(lambda dt: ad_manager.init(), 1)


if __name__ == '__main__':
    CricketApp().run()
