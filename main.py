# main.py — Clean UI (white), grid with borders & zebra, sticky header, center Scan, 3-dots menu (Filters/Settings)
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.factory import Factory
from kivy.clock import Clock, mainthread
from kivy.properties import ListProperty
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.utils import get_color_from_hex

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton, MDIconButton, MDFlatButton
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.bottomsheet import MDCustomBottomSheet
from kivymd.uix.card import MDCard
from kivymd.uix.selectioncontrol import MDCheckbox, MDSwitch
from kivymd.uix.textfield import MDTextField
from kivymd.uix.list import OneLineListItem  # ensure viewclass is registered

import threading, time, requests

KV = '''
<ThinDivider@Widget>:
    size_hint_y: None
    height: 1
    canvas:
        Color:
            rgba: app.cline
        Rectangle:
            pos: self.pos
            size: self.size

<TableCell@MDLabel>:
    padding: dp(10), dp(8)
    halign: 'left'
    valign: 'middle'
    shorten: True
    shorten_from: 'right'
    theme_text_color: 'Custom'
    text_color: app.ctext
    font_size: app.font_px
    canvas.before:
        Color:
            rgba: self.bg if hasattr(self, 'bg') else 1,1,1,1
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: app.cline
        Line:
            rectangle: (*self.pos, *self.size)
            width: app.line_px

<HeaderCell@TableCell>:
    bold: True
    canvas.before:
        Color:
            rgba: app.chead_bg
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: app.cline
        Line:
            rectangle: (*self.pos, *self.size)
            width: app.line_px

<TopBar@MDBoxLayout>:
    md_bg_color: 1,1,1,1
    size_hint_y: None
    height: dp(56)
    padding: dp(8)
    spacing: dp(8)

Root:
    orientation: 'vertical'
    md_bg_color: 1,1,1,1

    TopBar:
        # left spacer
        MDBoxLayout:
            size_hint_x: .2
        # Scan at center
        MDBoxLayout:
            size_hint_x: .6
            MDRaisedButton:
                id: scan_btn
                text: "Scan"
                on_release: app.start_scan()
                pos_hint: {'center_x': .5, 'center_y': .5}
        # 3-dots menu at right
        MDBoxLayout:
            size_hint_x: .2
            MDIconButton:
                icon: "dots-vertical"
                pos_hint: {'center_x': .5, 'center_y': .5}
                on_release: app.open_overflow(self)

    # Sticky header (horizontal) with synced scroll
    ScrollView:
        id: header_sv
        bar_width: 0
        do_scroll_y: False
        MDBoxLayout:
            size_hint_x: None
            width: app.table_width
            HeaderCell:
                text: "Symbol"
                size_hint_x: None
                width: app.col_w[0]
            HeaderCell:
                text: "Buy(Ask)"
                size_hint_x: None
                width: app.col_w[1]
            HeaderCell:
                text: "Sell(Bid)"
                size_hint_x: None
                width: app.col_w[2]
            HeaderCell:
                text: "Net %"
                size_hint_x: None
                width: app.col_w[3]
                halign: 'right'
            HeaderCell:
                text: "Abs Profit"
                size_hint_x: None
                width: app.col_w[4]
                halign: 'right'
            HeaderCell:
                text: "Transfer Fee"
                size_hint_x: None
                width: app.col_w[5]
                halign: 'right'
            HeaderCell:
                text: "Network"
                size_hint_x: None
                width: app.col_w[6]
            HeaderCell:
                text: "Canon"
                size_hint_x: None
                width: app.col_w[7]
            HeaderCell:
                text: "Vol(k$)"
                size_hint_x: None
                width: app.col_w[8]
                halign: 'right'

    # Body (both directions)
    ScrollView:
        id: body_sv
        do_scroll_x: True
        do_scroll_y: True
        on_scroll_x: app.sync_header()
        MDBoxLayout:
            id: table_holder
            size_hint_x: None
            width: app.table_width
            orientation: 'vertical'
            spacing: 0

    ThinDivider:

    # Status bar
    MDBoxLayout:
        size_hint_y: None
        height: dp(28)
        padding: dp(8), 0
        md_bg_color: 1,1,1,1
        MDLabel:
            id: status_lbl
            text: ""
            theme_text_color: 'Custom'
            text_color: app.cmuted
            font_size: sp(12)
            halign: 'left'
'''

class Root(MDBoxLayout):
    pass

# ---------------------- HTTP fetchers (public endpoints only) ----------------------
UA = {"User-Agent": "Mozilla/5.0 (KivyMD/ArbTracker)"}

def http_get(url, headers=None, timeout=15):
    try:
        r = requests.get(url, headers=headers or UA, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def fetch_okx(quote):
    url = 'https://www.okx.com/api/v5/market/tickers?instType=SPOT'
    js = http_get(url)
    out = {}
    if js and js.get('data'):
        for it in js['data']:
            inst = it.get('instId','')   # e.g. BTC-USDT
            if not inst.endswith(f'-{quote}'): continue
            base = inst.split('-')[0]
            sym = f'{base}/{quote}'
            try:
                ask = float(it.get('askPx') or 0)
                bid = float(it.get('bidPx') or 0)
                qv  = float(it.get('volCcy24h') or 0.0)  # quote volume
            except Exception:
                ask=bid=qv=0.0
            if ask>0 and bid>0:
                out[sym] = {'ask':ask,'bid':bid,'qvol':qv}
    return out

def fetch_kucoin(quote):
    url = 'https://api.kucoin.com/api/v1/market/allTickers'
    js = http_get(url)
    out = {}
    if js and js.get('data') and js['data'].get('ticker'):
        for it in js['data']['ticker']:
            sym = it.get('symbol','')   # e.g. BTC-USDT
            if not sym.endswith(f'-{quote}'): continue
            base = sym.split('-')[0]
            ksym = f'{base}/{quote}'
            try:
                ask = float(it.get('sell') or 0)
                bid = float(it.get('buy') or 0)
                qv  = float(it.get('volValue') or 0.0)
            except Exception:
                ask=bid=qv=0.0
            if ask>0 and bid>0:
                out[ksym] = {'ask':ask,'bid':bid,'qvol':qv}
    return out

def fetch_gate(quote):
    url = 'https://api.gateio.ws/api/v4/spot/tickers'
    js = http_get(url, headers={"Accept":"application/json"})
    out = {}
    if isinstance(js, list):
        for it in js:
            pair = it.get('currency_pair','')  # BTC_USDT
            if not pair.endswith(f'_{quote}'): continue
            base = pair.split('_')[0]
            gsym = f'{base}/{quote}'
            try:
                ask = float(it.get('lowest_ask') or 0)
                bid = float(it.get('highest_bid') or 0)
                qv  = float(it.get('quote_volume') or 0.0)
            except Exception:
                ask=bid=qv=0.0
            if ask>0 and bid>0:
                out[gsym] = {'ask':ask,'bid':bid,'qvol':qv}
    return out

EX_FETCH = {'okx': fetch_okx, 'kucoin': fetch_kucoin, 'gate': fetch_gate}

# ---------------------- App ----------------------
class ArbApp(MDApp):
    # colors
    ctext    = get_color_from_hex("#1F2937")  # text dark
    cmuted   = get_color_from_hex("#6B7280")  # muted
    cline    = get_color_from_hex("#E5E7EB")  # grid lines
    chead_bg = get_color_from_hex("#F3F4F6")  # header bg

    # layout metrics
    line_px = 1.0
    font_px = sp(14)

    # column widths
    col_w = ListProperty([dp(150), dp(180), dp(180), dp(100), dp(130), dp(130), dp(120), dp(100), dp(110)])

    @property
    def table_width(self):
        return sum(self.col_w)

    def build(self):
        self.title = ""      # no app bar title
        self.theme_cls.theme_style = "Light"
        self.root = Builder.load_string(KV)

        # default state
        self.filters = {
            'notional': 1000.0,
            'min_pct': 0.05,
            'min_abs': 0.5,
            'min_volk': 0.0,
            'quote': 'USDT',
            'strict_name': False,
            'exchanges': ['okx','kucoin','gate'],
        }
        self.settings = {
            'auto_refresh_s': 0,      # 0 = Off
            'line_weight': 'thin',    # thin/med/bold
            'font_size': 'M',         # S/M/L
            'theme': 'Light',
        }
        self._auto_event = None

        self.build_table([])  # empty state
        self.set_status("Ready.")
        Clock.schedule_once(lambda *_: self.start_scan(), 0.2)
        return self.root

    # --------------- UI helpers ---------------
    def set_status(self, txt):
        self.root.ids.status_lbl.text = txt

    def sync_header(self, *_):
        self.root.ids.header_sv.scroll_x = self.root.ids.body_sv.scroll_x

    def build_table(self, rows):
        holder = self.root.ids.table_holder
        holder.clear_widgets()

        if not rows:
            card = MDCard(md_bg_color=(1,1,1,1), padding=(dp(12), dp(18)), radius=[dp(8), dp(8), dp(8), dp(8)])
            card.add_widget(MDLabel(
                text="No opportunities above thresholds right now.",
                theme_text_color='Custom', text_color=self.cmuted,
                font_size=sp(14)))
            holder.add_widget(card)
            return

        grid = GridLayout(cols=9, spacing=0, size_hint_x=None)
        grid.bind(minimum_height=grid.setter('height'))
        grid.width = self.table_width

        zebra1 = (1,1,1,1)
        zebra2 = get_color_from_hex("#F8FAFC")

        for i, r in enumerate(rows):
            bg = zebra1 if i % 2 == 0 else zebra2
            # r = [symbol, buy, sell, net_pct, abs_profit, fee, network, canon, volk]
            cells = [
                ('left',  self.col_w[0], str(r[0])),
                ('left',  self.col_w[1], str(r[1])),
                ('left',  self.col_w[2], str(r[2])),
                ('right', self.col_w[3], f"{r[3]:.3f}"),
                ('right', self.col_w[4], f"{r[4]:.2f}"),
                ('right', self.col_w[5], f"{r[5]:.2f}"),
                ('left',  self.col_w[6], str(r[6])),
                ('left',  self.col_w[7], str(r[7])),
                ('right', self.col_w[8], f"{r[8]:.0f}"),
            ]
            for hal, w, txt in cells:
                lbl = Factory.TableCell()
                lbl.halign = hal
                lbl.text = txt
                lbl.size_hint_x = None
                lbl.width = w
                lbl.bg = bg
                grid.add_widget(lbl)

        holder.add_widget(grid)

    # --------------- Overflow (3-dots) ---------------
    def open_overflow(self, caller):
        menu = None
        def do_filters(*_):
            nonlocal menu
            if menu: menu.dismiss()
            self._open_filters(caller)
        def do_settings(*_):
            nonlocal menu
            if menu: menu.dismiss()
            self._open_settings(caller)

        items = [
            {"viewclass": "OneLineListItem", "text": "Filters",  "on_release": do_filters},
            {"viewclass": "OneLineListItem", "text": "Settings", "on_release": do_settings},
        ]
        menu = MDDropdownMenu(caller=caller, items=items, width_mult=3)
        menu.open()

    # ---- Filters sheet
    def _open_filters(self, _caller):
        content = MDBoxLayout(orientation='vertical', padding=dp(12), spacing=dp(12))

        tf_notional = MDTextField(text=str(self.filters['notional']), hint_text="Notional", input_filter="float")
        tf_minpct   = MDTextField(text=str(self.filters['min_pct']),   hint_text="Min %",  input_filter="float")
        tf_minabs   = MDTextField(text=str(self.filters['min_abs']),   hint_text="Min Abs",input_filter="float")
        tf_minvol   = MDTextField(text=str(self.filters['min_volk']),  hint_text="Min 24h Vol (k$)", input_filter="float")

        # Quote picker
        quote_lbl = MDLabel(text=f"Quote: {self.filters['quote']}", theme_text_color='Custom', text_color=self.ctext)
        qmenu = None
        def set_quote(q):
            self.filters['quote'] = q
            quote_lbl.text = f"Quote: {q}"
        def open_quote(btn):
            nonlocal qmenu
            qitems = [
                {"viewclass":"OneLineListItem","text":"USDT","on_release": lambda *_:(set_quote('USDT'), qmenu.dismiss())},
                {"viewclass":"OneLineListItem","text":"USDC","on_release": lambda *_:(set_quote('USDC'), qmenu.dismiss())},
            ]
            qmenu = MDDropdownMenu(caller=btn, items=qitems, width_mult=2)
            qmenu.open()
        quote_btn = MDRaisedButton(text="Change Quote", on_release=open_quote)

        # Exchanges
        ex_row = MDBoxLayout(adaptive_height=True, spacing=dp(10))
        ex_all = ['okx','kucoin','gate']
        ex_checks = {}
        for ex in ex_all:
            row = MDBoxLayout(adaptive_height=True, spacing=dp(6))
            chk = MDCheckbox(active=ex in self.filters['exchanges'])
            ex_checks[ex] = chk
            row.add_widget(chk)
            row.add_widget(MDLabel(text=ex.upper(), theme_text_color='Custom', text_color=self.ctext))
            ex_row.add_widget(row)

        strict_sw = MDSwitch(active=self.filters['strict_name'])
        strict_row = MDBoxLayout(adaptive_height=True, spacing=dp(8))
        strict_row.add_widget(MDLabel(text="Strict name", theme_text_color='Custom', text_color=self.ctext))
        strict_row.add_widget(strict_sw)

        # Buttons
        btns = MDBoxLayout(spacing=dp(8), adaptive_height=True)
        # Sheet must be created before binding Apply to close it:
        content.add_widget(tf_notional); content.add_widget(tf_minpct)
        content.add_widget(tf_minabs);   content.add_widget(tf_minvol)
        content.add_widget(quote_lbl);   content.add_widget(quote_btn)
        content.add_widget(MDLabel(text="Exchanges:", theme_text_color='Custom', text_color=self.ctext))
        content.add_widget(ex_row)
        content.add_widget(strict_row)
        sheet = MDCustomBottomSheet(screen=content)
        btns.add_widget(MDFlatButton(text="Reset", on_release=lambda *_: self._filters_reset(tf_notional, tf_minpct, tf_minabs, tf_minvol, ex_checks, strict_sw)))
        btns.add_widget(MDRaisedButton(text="Apply", on_release=lambda *_: self._filters_apply(tf_notional, tf_minpct, tf_minabs, tf_minvol, ex_checks, strict_sw, sheet)))
        content.add_widget(btns)
        sheet.open()

    def _filters_reset(self, t1, t2, t3, t4, ex_checks, strict_sw):
        t1.text, t2.text, t3.text, t4.text = "1000", "0.05", "0.5", "0"
        for ex in ex_checks.values():
            ex.active = True
        strict_sw.active = False

    def _filters_apply(self, t1, t2, t3, t4, ex_checks, strict_sw, sheet):
        try:
            self.filters['notional'] = float(t1.text or 0)
            self.filters['min_pct']  = float(t2.text or 0)
            self.filters['min_abs']  = float(t3.text or 0)
            self.filters['min_volk'] = float(t4.text or 0)
        except Exception:
            pass
        self.filters['exchanges'] = [k for k,v in ex_checks.items() if v.active]
        self.filters['strict_name'] = bool(strict_sw.active)
        sheet.dismiss()
        self.set_status("Filters applied.")

    # ---- Settings sheet
    def _open_settings(self, _caller):
        content = MDBoxLayout(orientation='vertical', padding=dp(12), spacing=dp(12))

        # Auto refresh
        content.add_widget(MDLabel(text="Auto-refresh (seconds):", theme_text_color='Custom', text_color=self.ctext))
        row = MDBoxLayout(spacing=dp(8), adaptive_height=True)
        for s in [0,15,30,60]:
            b = MDRaisedButton(text=str(s), md_bg_color=(0.9,0.9,0.9,1) if self.settings['auto_refresh_s']==s else (1,1,1,1))
            b.bind(on_release=lambda _btn, val=s: self._set_auto_refresh(val))
            row.add_widget(b)
        content.add_widget(row)

        # Line weight
        content.add_widget(MDLabel(text="Grid line weight:", theme_text_color='Custom', text_color=self.ctext))
        row2 = MDBoxLayout(spacing=dp(8), adaptive_height=True)
        for name, px in [('thin',1.0),('med',1.5),('bold',2.0)]:
            b = MDRaisedButton(text=name, md_bg_color=(0.9,0.9,0.9,1) if self.settings['line_weight']==name else (1,1,1,1))
            b.bind(on_release=lambda _b, nm=name, p=px: self._set_line(nm,p))
            row2.add_widget(b)
        content.add_widget(row2)

        # Font size
        content.add_widget(MDLabel(text="Font size:", theme_text_color='Custom', text_color=self.ctext))
        row3 = MDBoxLayout(spacing=dp(8), adaptive_height=True)
        for nm,px in [('S',sp(12)),('M',sp(14)),('L',sp(16))]:
            b = MDRaisedButton(text=nm, md_bg_color=(0.9,0.9,0.9,1) if self.settings['font_size']==nm else (1,1,1,1))
            b.bind(on_release=lambda _b, nm=nm, px=px: self._set_font(nm,px))
            row3.add_widget(b)
        content.add_widget(row3)

        # Theme
        content.add_widget(MDLabel(text="Theme:", theme_text_color='Custom', text_color=self.ctext))
        row4 = MDBoxLayout(spacing=dp(8), adaptive_height=True)
        for nm in ['Light','Dark']:
            b = MDRaisedButton(text=nm, md_bg_color=(0.9,0.9,0.9,1) if self.settings['theme']==nm else (1,1,1,1))
            b.bind(on_release=lambda _b, nm=nm: self._set_theme(nm))
            row4.add_widget(b)
        content.add_widget(row4)

        sheet = MDCustomBottomSheet(screen=content)
        sheet.open()

    def _set_auto_refresh(self, s):
        self.settings['auto_refresh_s'] = s
        if hasattr(self, "_auto_event") and self._auto_event:
            self._auto_event.cancel()
            self._auto_event = None
        if s > 0:
            self._auto_event = Clock.schedule_interval(lambda _dt: self.start_scan(), s)
        self.set_status(f"Auto-refresh: {s}s")

    def _set_line(self, name, px):
        self.settings['line_weight'] = name
        self.line_px = px
        self.build_table(getattr(self, "_last_rows", []))

    def _set_font(self, nm, px):
        self.settings['font_size'] = nm
        self.font_px = px
        self.build_table(getattr(self, "_last_rows", []))

    def _set_theme(self, nm):
        self.settings['theme'] = nm
        self.theme_cls.theme_style = nm

    # --------------- Scan ---------------
    def start_scan(self):
        btn = self.root.ids.scan_btn
        btn.disabled = True
        btn.text = "Scanning…"
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        t0 = time.time()
        rows = self._compute_opportunities()
        dt = time.time() - t0
        self._last_rows = rows
        self._update_table_from_thread(rows, dt)

    @mainthread
    def _update_table_from_thread(self, rows, dt):
        self.build_table(rows)
        self.root.ids.scan_btn.disabled = False
        self.root.ids.scan_btn.text = "Scan"
        now = time.strftime("%H:%M:%S")
        exs = ",".join(self.filters['exchanges'])
        self.set_status(f"Last update: {now}  |  exchanges: {exs}  |  quote: {self.filters['quote']}  |  {len(rows)} rows  | {dt:.1f}s")

    # ---------- core opportunity computation ----------
    def _compute_opportunities(self):
        quote = self.filters['quote']
        selected = self.filters['exchanges'][:]
        books = {}
        for ex in selected:
            fn = EX_FETCH.get(ex)
            if not fn:
                continue
            data = fn(quote)
            books[ex] = data

        # gather symbols present in ≥2 exchanges
        symbols = {}
        for ex, mp in books.items():
            for sym in mp.keys():
                symbols.setdefault(sym, set()).add(ex)
        syms = [s for s, exs in symbols.items() if len(exs) >= 2]

        notional = float(self.filters['notional'])
        min_pct  = float(self.filters['min_pct'])
        min_abs  = float(self.filters['min_abs'])
        min_volk = float(self.filters['min_volk'])

        out_rows = []
        for sym in syms:
            ex_data = []
            total_qvol = 0.0
            for ex in selected:
                b = books.get(ex, {}).get(sym)
                if b:
                    ex_data.append((ex, b['ask'], b['bid']))
                    total_qvol += b.get('qvol', 0.0)
            if len(ex_data) < 2:
                continue

            # min ask & max bid
            buy_ex, buy_ask = None, None
            sell_ex, sell_bid = None, None
            for ex, ask, bid in ex_data:
                if ask and (buy_ask is None or ask < buy_ask):
                    buy_ex, buy_ask = ex, ask
                if bid and (sell_bid is None or sell_bid < bid):
                    sell_ex, sell_bid = ex, bid
            if buy_ex == sell_ex or not buy_ask or not sell_bid:
                continue

            net_pct = (sell_bid / buy_ask - 1.0) * 100.0
            abs_profit = (sell_bid - buy_ask) * notional / buy_ask
            volk = total_qvol / 1000.0

            if net_pct >= min_pct and abs_profit >= min_abs and volk >= min_volk:
                out_rows.append([
                    sym,
                    f"{buy_ex}@{buy_ask:.8f}",
                    f"{sell_ex}@{sell_bid:.8f}",
                    net_pct,
                    abs_profit,
                    0.0,     # transfer fee placeholder
                    "-",     # network placeholder
                    "-",     # canon placeholder
                    volk,
                ])

        out_rows.sort(key=lambda r: r[3], reverse=True)
        return out_rows[:200]

if __name__ == "__main__":
    ArbApp().run()
