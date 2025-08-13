# -*- coding: utf-8 -*-
# Arbitrage Tracker — Mobile UI (sticky+linked header, FABs, more public exchanges)

import time, threading, requests
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, StringProperty, NumericProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.switch import Switch
from kivy.uix.modalview import ModalView

# ---------------- HTTP helper ----------------
def http_get(url, headers=None, timeout=12):
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# ---------------- Public fetchers ----------------
def fetch_binance():
    data = http_get("https://api.binance.com/api/v3/ticker/bookTicker")
    books = {}
    if not data: return books
    for it in data:
        s = it["symbol"]
        if s.endswith("USDT"): base, q = s[:-4], "USDT"
        elif s.endswith("USDC"): base, q = s[:-4], "USDC"
        else: continue
        books[f"{base}/{q}"] = {"ask": float(it["askPrice"]), "bid": float(it["bidPrice"])}
    return books

def fetch_okx():
    data = http_get("https://www.okx.com/api/v5/market/tickers?instType=SPOT")
    books = {}
    if not data or str(data.get("code"))!="0": return books
    for it in data.get("data", []):
        inst = it["instId"]  # ALT-USDT
        if "-USDT" in inst or "-USDC" in inst:
            base, q = inst.split("-")
            books[f"{base}/{q}"] = {"ask": float(it["askPx"]), "bid": float(it["bidPx"])}
    return books

def fetch_kucoin():
    data = http_get("https://api.kucoin.com/api/v1/market/allTickers")
    books = {}
    if not data or data.get("code")!="200000": return books
    for it in data["data"]["ticker"]:
        sym = it["symbol"]  # ALT-USDT
        if sym.endswith("-USDT") or sym.endswith("-USDC"):
            base, q = sym.split("-")
            ask = it.get("sell") or it.get("bestAskPrice") or "0"
            bid = it.get("buy")  or it.get("bestBidPrice") or "0"
            books[f"{base}/{q}"] = {"ask": float(ask or 0), "bid": float(bid or 0)}
    return books

def fetch_gate():
    data = http_get("https://api.gateio.ws/api/v4/spot/tickers",
                    headers={"Accept":"application/json"})
    books = {}
    if not data: return books
    for it in data:
        pair = it["currency_pair"]  # ALT_USDT
        if pair.endswith("_USDT") or pair.endswith("_USDC"):
            base, q = pair.split("_")
            books[f"{base}/{q}"] = {
                "ask": float(it.get("lowest_ask") or 0),
                "bid": float(it.get("highest_bid") or 0),
            }
    return books

def fetch_mexc():
    data = http_get("https://api.mexc.com/api/v3/ticker/bookTicker")
    books = {}
    if not data: return books
    for it in data:
        s = it["symbol"]
        if s.endswith("USDT"): base, q = s[:-4], "USDT"
        elif s.endswith("USDC"): base, q = s[:-4], "USDC"
        else: continue
        books[f"{base}/{q}"] = {"ask": float(it["askPrice"]), "bid": float(it["bidPrice"])}
    return books

def fetch_bybit():
    data = http_get("https://api.bybit.com/v5/market/tickers?category=spot")
    books = {}
    if not data or str(data.get("retCode"))!="0": return books
    for it in data["result"]["list"]:
        s = it["symbol"]
        if s.endswith("USDT"): base, q = s[:-4], "USDT"
        elif s.endswith("USDC"): base, q = s[:-4], "USDC"
        else: continue
        books[f"{base}/{q}"] = {"ask": float(it["ask1Price"]), "bid": float(it["bid1Price"])}
    return books

def fetch_huobi():  # HTX
    data = http_get("https://api.huobi.pro/market/tickers")
    books = {}
    if not data or data.get("status")!="ok": return books
    for it in data.get("data", []):
        sym = it.get("symbol","").upper()  # e.g. ALTUSDT
        if sym.endswith("USDT"): base, q = sym[:-4], "USDT"
        elif sym.endswith("USDC"): base, q = sym[:-4], "USDC"
        else: continue
        ask = it.get("ask") or it.get("askPrice") or it.get("close")
        bid = it.get("bid") or it.get("bidPrice") or it.get("close")
        if ask and bid:
            books[f"{base}/{q}"] = {"ask": float(ask), "bid": float(bid)}
    return books

def fetch_poloniex():
    data = http_get("https://api.poloniex.com/markets/ticker24h")
    books = {}
    if not data: return books
    for it in data:
        sym = it.get("symbol","")  # e.g. ALT_USDT
        if sym.endswith("_USDT") or sym.endswith("_USDC"):
            base, q = sym.split("_")
            ask = it.get("ask") or it.get("askPrice") or it.get("price")
            bid = it.get("bid") or it.get("bidPrice") or it.get("price")
            if ask and bid:
                books[f"{base}/{q}"] = {"ask": float(ask), "bid": float(bid)}
    return books

def fetch_hitbtc():
    data = http_get("https://api.hitbtc.com/api/3/public/ticker")
    books = {}
    if not data: return books
    for sym, it in data.items():  # e.g. ALTUSDT
        usdt = sym.endswith("USDT"); usdc = sym.endswith("USDC")
        if not (usdt or usdc): continue
        base = sym[:-4]; q = "USDT" if usdt else "USDC"
        ask = it.get("ask") or it.get("ask_price") or it.get("last")
        bid = it.get("bid") or it.get("bid_price") or it.get("last")
        if ask and bid:
            books[f"{base}/{q}"] = {"ask": float(ask), "bid": float(bid)}
    return books

def fetch_bitget():
    data = http_get("https://api.bitget.com/api/spot/v1/market/tickers")
    books = {}
    if not data or data.get("code") not in ("00000","0"): return books
    for it in data.get("data", []):
        s = it.get("symbol","")  # ALTUSDT
        if s.endswith("USDT"): base, q = s[:-4], "USDT"
        elif s.endswith("USDC"): base, q = s[:-4], "USDC"
        else: continue
        # try multiple key names
        ask = it.get("sellOne") or it.get("askPx") or it.get("bestAsk") or it.get("askPrice")
        bid = it.get("buyOne")  or it.get("bidPx") or it.get("bestBid") or it.get("bidPrice")
        if ask and bid:
            books[f"{base}/{q}"] = {"ask": float(ask), "bid": float(bid)}
    return books

def fetch_bitmart():
    data = http_get("https://api-cloud.bitmart.com/spot/v1/ticker")
    books = {}
    if not data or data.get("code") not in (1000, "1000"): return books
    for it in data.get("data", {}).get("tickers", []):
        s = it.get("symbol","")  # ALT_USDT
        if s.endswith("_USDT") or s.endswith("_USDC"):
            base, q = s.split("_")
            ask = it.get("best_ask") or it.get("ask_price")
            bid = it.get("best_bid") or it.get("bid_price")
            if ask and bid:
                books[f"{base}/{q}"] = {"ask": float(ask), "bid": float(bid)}
    return books

def fetch_bitrue():
    data = http_get("https://openapi.bitrue.com/api/v1/ticker/bookTicker")
    books = {}
    if not data: return books
    for it in data:
        s = it.get("symbol","")
        if s.endswith("USDT"): base, q = s[:-4], "USDT"
        elif s.endswith("USDC"): base, q = s[:-4], "USDC"
        else: continue
        ask = it.get("askPrice") or it.get("ask")
        bid = it.get("bidPrice") or it.get("bid")
        if ask and bid:
            books[f"{base}/{q}"] = {"ask": float(ask), "bid": float(bid)}
    return books

EXCH_FETCHERS = {
    "binance": fetch_binance,
    "okx": fetch_okx,
    "kucoin": fetch_kucoin,
    "gate": fetch_gate,
    "mexc": fetch_mexc,
    "bybit": fetch_bybit,
    "htx": fetch_huobi,        # Huobi/HTX
    "poloniex": fetch_poloniex,
    "hitbtc": fetch_hitbtc,
    "bitget": fetch_bitget,
    "bitmart": fetch_bitmart,
    "bitrue": fetch_bitrue,
    # TODO: kraken / xt / ascendex / bingx (نیاز به نگاشت نماد یا اندپوینت متفاوت)
}

# شبکه پایه (بدون API خصوصی معمولاً نامشخص است)
def guess_network(exchange: str, base: str):
    return None  # فعلاً برمی‌گردونیم نامشخص (—)

# ---------------- Core ----------------
def aggregate(exchs):
    out = {}
    for ex in exchs:
        try:
            data = EXCH_FETCHERS[ex]()
        except Exception:
            data = {}
        for sym, px in data.items():
            out.setdefault(sym, {})[ex] = px
    return out

def find_opps(books, selected, quote="USDT", notional=1000.0, min_pct=0.1, min_abs=0.05, strict_network=False):
    rows = []
    sel = set(selected)
    for sym, exmap in books.items():
        base, q = sym.split("/")
        if q != quote: continue
        for b_ex, b in exmap.items():
            if b_ex not in sel: continue
            ask = b.get("ask") or 0.0
            if ask <= 0: continue
            for s_ex, s in exmap.items():
                if s_ex == b_ex or s_ex not in sel: continue
                bid = s.get("bid") or 0.0
                if bid <= 0: continue
                pct = (bid-ask)/ask*100.0
                abs_profit = (bid-ask)*(notional/ask)
                nb = guess_network(b_ex, base)
                ns = guess_network(s_ex, base)
                if strict_network and (nb is None or ns is None or nb != ns):
                    continue
                if pct >= min_pct and abs_profit >= min_abs:
                    rows.append({
                        "sym": sym,
                        "buy": f"{b_ex}@{ask:.8f}",
                        "sell": f"{s_ex}@{bid:.8f}",
                        "pct": pct,
                        "abs": abs_profit,
                        "net": nb if nb else "—",
                        "canon": "✓" if (nb and ns and nb==ns) else "—",
                    })
    rows.sort(key=lambda r: (-r["pct"], -r["abs"]))
    return rows

# ---------------- UI bits ----------------
COLS = [
    ("Symbol",     dp(160)),
    ("Buy(Ask)",   dp(190)),
    ("Sell(Bid)",  dp(190)),
    ("Net %",      dp(90)),
    ("Abs Profit", dp(130)),
    ("Network",    dp(120)),
    ("Canon",      dp(80)),
]
TOTAL_W = sum(w for _, w in COLS)

def make_header():
    g = GridLayout(cols=len(COLS), size_hint=(None,None), height=dp(34), width=TOTAL_W, padding=[dp(6),0], spacing=dp(10))
    for title, w in COLS:
        g.add_widget(Label(text=f"[b]{title}[/b]", markup=True, size_hint=(None,1), width=w, font_size=sp(14)))
    return g

class DataGrid(GridLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cols = len(COLS)
        self.size_hint = (None,None)
        self.padding=[dp(6),0]
        self.spacing=dp(10)
        self.width = TOTAL_W
        self.bind(minimum_height=self.setter("height"))
    def set_rows(self, rows):
        self.clear_widgets()
        for r in rows:
            cells = [r["sym"], r["buy"], r["sell"], f"{r['pct']:.3f}%", f"{r['abs']:.2f}", r["net"], r["canon"]]
            for (title,w), val in zip(COLS, cells):
                self.add_widget(Label(text=val, size_hint=(None,None), width=w, height=dp(28), font_size=sp(13)))

class FiltersModal(ModalView):
    def __init__(self, init, on_apply, **kw):
        super().__init__(**kw); self.size_hint=(0.92,0.7); self.background_color=(0,0,0,0.7); self.auto_dismiss=False
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        row1 = GridLayout(cols=2, spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.in_notional = TextInput(text=str(int(init["notional"])), input_filter="int", hint_text="Notional")
        self.in_minpct  = TextInput(text=str(init["min_pct"]), input_filter="float", hint_text="Min %")
        row2 = GridLayout(cols=2, spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.in_minabs  = TextInput(text=str(init["min_abs"]), input_filter="float", hint_text="Min Abs")
        qrow = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.btn_usdt = ToggleButton(text="USDT", state="down" if init["quote"]=="USDT" else "normal")
        self.btn_usdc = ToggleButton(text="USDC", state="down" if init["quote"]=="USDC" else "normal")
        def setq(q): self.btn_usdt.state="down" if q=="USDT" else "normal"; self.btn_usdc.state="down" if q=="USDC" else "normal"
        self.btn_usdt.bind(on_release=lambda *_: setq("USDT")); self.btn_usdc.bind(on_release=lambda *_: setq("USDC"))
        row1.add_widget(self.in_notional); row1.add_widget(self.in_minpct)
        row2.add_widget(self.in_minabs);   qrow.add_widget(self.btn_usdt); qrow.add_widget(self.btn_usdc)
        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        def apply_now(*_):
            quote = "USDT" if self.btn_usdt.state=="down" else "USDC"
            on_apply(dict(notional=float(self.in_notional.text or 1000),
                          min_pct=float(self.in_minpct.text or 0.1),
                          min_abs=float(self.in_minabs.text or 0.05),
                          quote=quote))
            self.dismiss()
        btns.add_widget(Button(text="Apply", on_release=apply_now))
        box.add_widget(Label(text="[b]Filters[/b]", markup=True, size_hint=(1,None), height=dp(26)))
        box.add_widget(row1); box.add_widget(row2); box.add_widget(qrow); box.add_widget(btns)
        self.add_widget(box)

class SettingsModal(ModalView):
    def __init__(self, init, on_apply, on_edit_exchanges, **kw):
        super().__init__(**kw); self.size_hint=(0.92,0.7); self.background_color=(0,0,0,0.7); self.auto_dismiss=False
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        r1 = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.sw_auto = Switch(active=init["auto"])
        self.in_interval = TextInput(text=str(init["interval"]), input_filter="int", hint_text="sec")
        r1.add_widget(Label(text="Auto refresh")); r1.add_widget(self.sw_auto)
        r1.add_widget(Label(text="Interval(s)"));  r1.add_widget(self.in_interval)
        r2 = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.sw_strictnet = Switch(active=init["strict_network"])
        r2.add_widget(Label(text="Strict base network")); r2.add_widget(self.sw_strictnet)
        exbtn = Button(text=f"Select Exchanges ({init['ex_count']})", size_hint=(1,None), height=dp(44))
        exbtn.bind(on_release=lambda *_: (self.dismiss(), on_edit_exchanges()))
        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Close", on_release=lambda *_: self.dismiss()))
        def apply_now(*_):
            on_apply(dict(auto=bool(self.sw_auto.active),
                          interval=int(self.in_interval.text or 15),
                          strict_network=bool(self.sw_strictnet.active)))
            self.dismiss()
        btns.add_widget(Button(text="Apply", on_release=apply_now))
        box.add_widget(Label(text="[b]Settings[/b]", markup=True, size_hint=(1,None), height=dp(26)))
        box.add_widget(r1); box.add_widget(r2); box.add_widget(exbtn); box.add_widget(btns)
        self.add_widget(box)

class ExchangesModal(ModalView):
    def __init__(self, selected:set, on_done, **kw):
        super().__init__(**kw); self.size_hint=(0.92,0.7); self.background_color=(0,0,0,0.7); self.auto_dismiss=False
        self.sel=set(selected)
        g = GridLayout(cols=2, spacing=dp(8), size_hint=(1,None)); g.bind(minimum_height=g.setter("height"))
        for ex in sorted(EXCH_FETCHERS.keys()):
            t = ToggleButton(text=ex, state="down" if ex in self.sel else "normal", size_hint=(1,None), height=dp(44))
            t.bind(on_release=lambda btn, e=ex: (self.sel.add(e) if btn.state=="down" else self.sel.discard(e)))
            g.add_widget(t)
        sc = ScrollView(); sc.add_widget(g)
        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        btns.add_widget(Button(text="Apply", on_release=lambda *_: (on_done(self.sel), self.dismiss())))
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        root.add_widget(Label(text="[b]Exchanges[/b]", markup=True, size_hint=(1,None), height=dp(26)))
        root.add_widget(sc); root.add_widget(btns)
        self.add_widget(root)

# ---------------- Root ----------------
class Root(FloatLayout):
    running = BooleanProperty(False)

    notional = NumericProperty(1000.0)
    min_pct  = NumericProperty(0.1)
    min_abs  = NumericProperty(0.05)
    quote    = StringProperty("USDT")

    auto = BooleanProperty(True)
    interval = NumericProperty(15)
    strict_network = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.selected_exchs = {"okx","kucoin","gate"}

        # main column
        self.main = BoxLayout(orientation="vertical", size_hint=(1,1))
        self.add_widget(self.main)

        title = Label(text="[b]Arbitrage Tracker — BASE transfer[/b]", markup=True,
                      size_hint=(1,None), height=dp(46), font_size=sp(16))
        self.main.add_widget(title)

        # header + body with linked horizontal scroll
        self.header = make_header()
        self.hscroll = ScrollView(do_scroll_x=True, do_scroll_y=False, bar_width=0,
                                  size_hint=(1,None), height=dp(34))
        self.hscroll.add_widget(self.header)
        self.main.add_widget(self.hscroll)

        self.grid = DataGrid()
        self.bscroll = ScrollView(do_scroll_x=True, do_scroll_y=True, size_hint=(1,1))
        self.bscroll.add_widget(self.grid)
        self.main.add_widget(self.bscroll)

        # link scrolls
        self._syncing=False
        def sync_from_body(*_):
            if self._syncing: return
            self._syncing=True
            self.hscroll.scroll_x = self.bscroll.scroll_x
            self._syncing=False
        def sync_from_head(*_):
            if self._syncing: return
            self._syncing=True
            self.bscroll.scroll_x = self.hscroll.scroll_x
            self._syncing=False
        self.bscroll.bind(scroll_x=lambda *_: sync_from_body())
        self.hscroll.bind(scroll_x=lambda *_: sync_from_head())

        # footer
        self.footer = Label(text="Last update: —  |  exchanges: okx, kucoin, gate  |  quote: USDT",
                            size_hint=(1,None), height=dp(28), font_size=sp(12))
        self.main.add_widget(self.footer)

        # Floating buttons (right side)
        fab_wrap = AnchorLayout(anchor_x='right', anchor_y='bottom', size_hint=(1,1))
        btn_col = BoxLayout(orientation='horizontal', spacing=dp(10), padding=[0,0,dp(12),dp(12)],
                            size_hint=(None,None))
        def mk_fab(text, w=56, cb=None):
            b = Button(text=text, size_hint=(None,None), width=dp(w), height=dp(w),
                       background_normal='', background_color=(0.15,0.55,0.95,1), font_size=sp(16))
            b.bind(on_release=lambda *_: cb() if cb else None)
            return b
        # small Scan
        scan_btn = mk_fab("⟳", w=48, cb=self.scan)
        # big Menu (filters/settings)
        def open_menu():
            m = ModalView(size_hint=(None,None), size=(dp(220), dp(120)), background_color=(0,0,0,0.7), auto_dismiss=True)
            box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
            box.add_widget(Button(text="Filters", on_release=lambda *_: (m.dismiss(), self.open_filters())))
            box.add_widget(Button(text="Settings", on_release=lambda *_: (m.dismiss(), self.open_settings())))
            m.add_widget(box); m.open()
        menu_btn = mk_fab("⋮", w=56, cb=open_menu)
        btn_col.add_widget(scan_btn); btn_col.add_widget(menu_btn)
        fab_wrap.add_widget(btn_col)
        self.add_widget(fab_wrap)

        # auto refresh
        self._ev = Clock.schedule_interval(lambda *_: self.scan(), self.interval) if self.auto else None
        Clock.schedule_once(lambda *_: self.scan(), 0.4)

    # ---- Modals ----
    def open_filters(self):
        init = dict(notional=self.notional, min_pct=self.min_pct, min_abs=self.min_abs, quote=self.quote)
        def apply(cfg):
            self.notional = cfg["notional"]; self.min_pct = cfg["min_pct"]
            self.min_abs = cfg["min_abs"];   self.quote   = cfg["quote"]
            self.scan()
        FiltersModal(init, on_apply=apply).open()

    def open_settings(self):
        init = dict(auto=self.auto, interval=int(self.interval),
                    strict_network=self.strict_network, ex_count=len(self.selected_exchs))
        def apply(cfg):
            self.strict_network = cfg["strict_network"]
            if cfg["auto"]:
                self.interval = max(5, int(cfg["interval"] or 15))
                if self._ev: self._ev.cancel()
                self._ev = Clock.schedule_interval(lambda *_: self.scan(), self.interval)
            else:
                if self._ev: self._ev.cancel(); self._ev = None
            self.auto = cfg["auto"]
        def edit_exchanges():
            def done(sel):
                self.selected_exchs = set(sel) if sel else set(EXCH_FETCHERS.keys())
                self.scan()
            ExchangesModal(self.selected_exchs, on_done=done).open()
        SettingsModal(init, on_apply=apply, on_edit_exchanges=edit_exchanges).open()

    # ---- Scan ----
    def scan(self):
        if self.running: return
        self.running = True
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        used = sorted(self.selected_exchs)
        books = aggregate(used)
        rows = find_opps(books, used, quote=self.quote, notional=self.notional,
                         min_pct=self.min_pct, min_abs=self.min_abs,
                         strict_network=self.strict_network)
        self._on_results(rows, used)

    @mainthread
    def _on_results(self, rows, used):
        self.grid.set_rows(rows)
        ts = time.strftime("%H:%M:%S")
        self.footer.text = f"Last update: {ts}  |  exchanges: {', '.join(used)}  |  quote: {self.quote}"
        self.running = False

class ArbApp(App):
    def build(self):
        from kivy.core.window import Window
        Window.clearcolor = (0.06,0.06,0.06,1)
        return Root()

if __name__ == "__main__":
    ArbApp().run()
