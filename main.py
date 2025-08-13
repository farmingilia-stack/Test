# -*- coding: utf-8 -*-
# Arbitrage Tracker — Mobile (filters/settings modals + sticky header + H/V scroll)
# Deps: kivy, requests

import time, json, threading
from functools import partial

import requests
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, StringProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.switch import Switch
from kivy.uix.modalview import ModalView

# ---------- HTTP helper ----------
def http_get(url, headers=None, timeout=10):
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# ---------- Public book-tickers ----------
def fetch_binance():
    url = "https://api.binance.com/api/v3/ticker/bookTicker"
    data = http_get(url)
    books = {}
    if not data: return books
    for it in data:
        s = it["symbol"]
        if s.endswith("USDT"): base, quote = s[:-4], "USDT"
        elif s.endswith("USDC"): base, quote = s[:-4], "USDC"
        else: continue
        books[f"{base}/{quote}"] = {"ask": float(it["askPrice"]), "bid": float(it["bidPrice"])}
    return books

def fetch_okx():
    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    data = http_get(url)
    books = {}
    if not data or str(data.get("code")) != "0": return books
    for it in data.get("data", []):
        inst = it["instId"]  # e.g. ALT-USDT
        if "-USDT" in inst or "-USDC" in inst:
            base, quote = inst.split("-")
            books[f"{base}/{quote}"] = {"ask": float(it["askPx"]), "bid": float(it["bidPx"])}
    return books

def fetch_kucoin():
    url = "https://api.kucoin.com/api/v1/market/allTickers"
    data = http_get(url)
    books = {}
    if not data or data.get("code") != "200000": return books
    for it in data["data"]["ticker"]:
        sym = it["symbol"]  # ALT-USDT
        if sym.endswith("-USDT") or sym.endswith("-USDC"):
            base, quote = sym.split("-")
            ask = it.get("sell") or it.get("bestAskPrice") or "0"
            bid = it.get("buy")  or it.get("bestBidPrice") or "0"
            books[f"{base}/{quote}"] = {"ask": float(ask or 0), "bid": float(bid or 0)}
    return books

def fetch_gate():
    url = "https://api.gateio.ws/api/v4/spot/tickers"
    data = http_get(url, headers={"Accept": "application/json"})
    books = {}
    if not data: return books
    for it in data:
        pair = it["currency_pair"]  # ALT_USDT
        if pair.endswith("_USDT") or pair.endswith("_USDC"):
            base, quote = pair.split("_")
            books[f"{base}/{quote}"] = {
                "ask": float(it.get("lowest_ask") or 0),
                "bid": float(it.get("highest_bid") or 0),
            }
    return books

def fetch_mexc():
    url = "https://api.mexc.com/api/v3/ticker/bookTicker"
    data = http_get(url)
    books = {}
    if not data: return books
    for it in data:
        s = it["symbol"]
        if s.endswith("USDT"): base, quote = s[:-4], "USDT"
        elif s.endswith("USDC"): base, quote = s[:-4], "USDC"
        else: continue
        books[f"{base}/{quote}"] = {"ask": float(it["askPrice"]), "bid": float(it["bidPrice"])}
    return books

def fetch_bybit():
    url = "https://api.bybit.com/v5/market/tickers?category=spot"
    data = http_get(url)
    books = {}
    if not data or str(data.get("retCode")) != "0": return books
    for it in data["result"]["list"]:
        s = it["symbol"]
        if s.endswith("USDT"): base, quote = s[:-4], "USDT"
        elif s.endswith("USDC"): base, quote = s[:-4], "USDC"
        else: continue
        books[f"{base}/{quote}"] = {"ask": float(it["ask1Price"]), "bid": float(it["bid1Price"])}
    return books

EXCH_FETCHERS = {
    "okx": fetch_okx,
    "kucoin": fetch_kucoin,
    "gate": fetch_gate,
    "binance": fetch_binance,
    "mexc": fetch_mexc,
    "bybit": fetch_bybit,
}

# --- (Optional) network canon (placeholder: unknown -> "—") ---
def guess_network(exchange: str, base: str):
    # بدون API خصوصی، شبکه دقیق اکثر کوین‌ها مشخص نیست → برمی‌گردونیم None
    return None

# ---------- Core ----------
def aggregate(exchs):
    out = {}
    for ex in exchs:
        try:
            book = EXCH_FETCHERS[ex]()
        except Exception:
            book = {}
        for sym, px in book.items():
            out.setdefault(sym, {})[ex] = px
    return out

def find_opps(books, selected_exchs, quote="USDT", notional=1000.0, min_pct=0.1, min_abs=0.05,
              strict_network=False):
    rows = []
    sel = set(selected_exchs)
    for sym, exmap in books.items():
        base, q = sym.split("/")
        if q != quote: 
            continue
        for b_ex, b in exmap.items():
            if b_ex not in sel: continue
            ask = b.get("ask") or 0
            if ask <= 0: continue
            for s_ex, s in exmap.items():
                if s_ex == b_ex or s_ex not in sel: continue
                bid = s.get("bid") or 0
                if bid <= 0: continue
                pct = (bid - ask)/ask * 100.0
                abs_profit = (bid - ask) * (notional/ask)
                # شبکهٔ پایه (Base) – اگر هر دو معلوم و برابر نبود، حذف
                net_b = guess_network(b_ex, base)
                net_s = guess_network(s_ex, base)
                if strict_network and (net_b is None or net_s is None or net_b != net_s):
                    continue
                if pct >= min_pct and abs_profit >= min_abs:
                    rows.append({
                        "sym": sym,
                        "buy": f"{b_ex}@{ask:.8f}",
                        "sell": f"{s_ex}@{bid:.8f}",
                        "pct": pct,
                        "abs": abs_profit,
                        "net": net_b if net_b else "—",
                        "canon": "✓" if (net_b and net_s and net_b == net_s) else "—",
                    })
    rows.sort(key=lambda r: (-r["pct"], -r["abs"]))
    return rows

# ---------- UI helpers ----------
COLS = [
    ("Symbol",      dp(150)),
    ("Buy(Ask)",    dp(170)),
    ("Sell(Bid)",   dp(170)),
    ("Net %",       dp(90)),
    ("Abs Profit",  dp(120)),
    ("Network",     dp(120)),
    ("Canon",       dp(80)),
]
TOTAL_W = sum(w for _, w in COLS)

def header_grid():
    g = GridLayout(cols=len(COLS), size_hint=(None, None), height=dp(30), width=TOTAL_W, padding=[dp(6),0], spacing=dp(6))
    for title, w in COLS:
        g.add_widget(Label(text=f"[b]{title}[/b]", markup=True, size_hint=(None,1), width=w, font_size=sp(13)))
    return g

class DataGrid(GridLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cols = len(COLS)
        self.size_hint = (None, None)
        self.spacing = dp(6)
        self.padding = [dp(6), 0]
        self.width = TOTAL_W
        self.bind(minimum_height=self.setter("height"))

    def set_rows(self, rows):
        self.clear_widgets()
        for r in rows:
            cells = [
                r["sym"], r["buy"], r["sell"],
                f"{r['pct']:.3f}%", f"{r['abs']:.2f}",
                r["net"], r["canon"]
            ]
            for (title, w), val in zip(COLS, cells):
                self.add_widget(Label(text=val, size_hint=(None,None), width=w, height=dp(28), font_size=sp(12)))

class FiltersModal(ModalView):
    def __init__(self, init, on_apply, **kw):
        super().__init__(**kw)
        self.size_hint = (0.92, 0.7)
        self.background_color = (0,0,0,0.7)
        self.auto_dismiss = False
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        row1 = GridLayout(cols=2, spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.in_notional = TextInput(text=str(int(init["notional"])), input_filter="int", hint_text="Notional")
        self.in_minpct  = TextInput(text=str(init["min_pct"]), input_filter="float", hint_text="Min %")
        row2 = GridLayout(cols=2, spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.in_minabs  = TextInput(text=str(init["min_abs"]), input_filter="float", hint_text="Min Abs")
        qrow = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.btn_usdt = ToggleButton(text="USDT", state="down" if init["quote"]=="USDT" else "normal")
        self.btn_usdc = ToggleButton(text="USDC", state="down" if init["quote"]=="USDC" else "normal")
        def setq(q):
            self.btn_usdt.state = "down" if q=="USDT" else "normal"
            self.btn_usdc.state = "down" if q=="USDC" else "normal"
        self.btn_usdt.bind(on_release=lambda *_: setq("USDT"))
        self.btn_usdc.bind(on_release=lambda *_: setq("USDC"))

        row1.add_widget(self.in_notional); row1.add_widget(self.in_minpct)
        row2.add_widget(self.in_minabs);   qrow.add_widget(self.btn_usdt); qrow.add_widget(self.btn_usdc)

        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        def apply_now(*_):
            quote = "USDT" if self.btn_usdt.state=="down" else "USDC"
            cfg = dict(
                notional=float(self.in_notional.text or 1000),
                min_pct=float(self.in_minpct.text or 0.1),
                min_abs=float(self.in_minabs.text or 0.05),
                quote=quote,
            )
            on_apply(cfg); self.dismiss()
        btns.add_widget(Button(text="Apply", on_release=apply_now))

        box.add_widget(Label(text="[b]Filters[/b]", markup=True, size_hint=(1,None), height=dp(24)))
        box.add_widget(row1); box.add_widget(row2); box.add_widget(qrow); box.add_widget(btns)
        self.add_widget(box)

class SettingsModal(ModalView):
    def __init__(self, init, on_apply, on_edit_exchanges, **kw):
        super().__init__(**kw)
        self.size_hint = (0.92, 0.7)
        self.background_color = (0,0,0,0.7)
        self.auto_dismiss = False
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        # auto refresh
        r1 = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.sw_auto = Switch(active=init["auto"])
        self.in_interval = TextInput(text=str(init["interval"]), input_filter="int", hint_text="sec")
        r1.add_widget(Label(text="Auto refresh")); r1.add_widget(self.sw_auto)
        r1.add_widget(Label(text="Interval(s)"));  r1.add_widget(self.in_interval)

        # strict network
        r2 = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.sw_strictnet = Switch(active=init["strict_network"])
        r2.add_widget(Label(text="Strict base network")); r2.add_widget(self.sw_strictnet)

        # exchanges
        exbtn = Button(text=f"Select Exchanges ({init['ex_count']})", size_hint=(1,None), height=dp(44))
        exbtn.bind(on_release=lambda *_: (self.dismiss(), on_edit_exchanges()))

        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Close", on_release=lambda *_: self.dismiss()))
        def apply_now(*_):
            cfg = dict(
                auto=bool(self.sw_auto.active),
                interval=int(self.in_interval.text or 15),
                strict_network=bool(self.sw_strictnet.active),
            )
            on_apply(cfg); self.dismiss()
        btns.add_widget(Button(text="Apply", on_release=apply_now))

        box.add_widget(Label(text="[b]Settings[/b]", markup=True, size_hint=(1,None), height=dp(24)))
        box.add_widget(r1); box.add_widget(r2); box.add_widget(exbtn); box.add_widget(btns)
        self.add_widget(box)

class ExchangesModal(ModalView):
    def __init__(self, selected:set, on_done, **kw):
        super().__init__(**kw)
        self.size_hint=(0.92,0.7); self.background_color=(0,0,0,0.7); self.auto_dismiss=False
        self.sel=set(selected)
        g = GridLayout(cols=2, spacing=dp(8), size_hint=(1,None))
        g.bind(minimum_height=g.setter("height"))
        for ex in EXCH_FETCHERS.keys():
            t = ToggleButton(text=ex, state="down" if ex in self.sel else "normal",
                             size_hint=(1,None), height=dp(44))
            t.bind(on_release=lambda btn, e=ex: (self.sel.add(e) if btn.state=="down" else self.sel.discard(e)))
            g.add_widget(t)
        sc = ScrollView(); sc.add_widget(g)
        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        btns.add_widget(Button(text="Apply", on_release=lambda *_: (on_done(self.sel), self.dismiss())))
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        root.add_widget(Label(text="[b]Exchanges[/b]", markup=True, size_hint=(1,None), height=dp(24)))
        root.add_widget(sc); root.add_widget(btns)
        self.add_widget(root)

# ---------- Root UI ----------
class Root(BoxLayout):
    running = BooleanProperty(False)
    last_status = StringProperty("—")

    # filters
    notional = NumericProperty(1000.0)
    min_pct = NumericProperty(0.1)
    min_abs = NumericProperty(0.05)
    quote = StringProperty("USDT")

    # settings
    auto = BooleanProperty(True)
    interval = NumericProperty(15)
    strict_network = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = "vertical"
        self.selected_exchs = {"okx","kucoin","gate"}

        # Top bar
        top = BoxLayout(size_hint=(1,None), height=dp(48), padding=[dp(8),0], spacing=dp(8))
        top.add_widget(Label(text="[b]Arbitrage Tracker — BASE transfer[/b]", markup=True, font_size=sp(16)))
        top.add_widget(Button(text="Filters", size_hint=(None,1), width=dp(90), on_release=lambda *_: self.open_filters()))
        top.add_widget(Button(text="Settings", size_hint=(None,1), width=dp(100), on_release=lambda *_: self.open_settings()))
        top.add_widget(Button(text="Scan", size_hint=(None,1), width=dp(80), on_release=lambda *_: self.scan()))
        self.add_widget(top)

        # sticky header
        self.header = header_grid()
        header_wrap = ScrollView(do_scroll_x=True, do_scroll_y=False, bar_width=0, size_hint=(1,None), height=dp(30))
        header_wrap.add_widget(self.header)
        self.add_widget(header_wrap)

        # data area (both directions)
        self.grid = DataGrid()
        self.scroller = ScrollView(do_scroll_x=True, do_scroll_y=True, size_hint=(1,1))
        self.scroller.add_widget(self.grid)
        self.add_widget(self.scroller)

        # footer
        self.footer = Label(text="Last update: — | exchanges: okx, kucoin, gate | quote: USDT",
                            size_hint=(1,None), height=dp(28), font_size=sp(12))
        self.add_widget(self.footer)

        # auto timer
        self._ev = Clock.schedule_interval(lambda *_: self.scan(), self.interval) if self.auto else None
        Clock.schedule_once(lambda *_: self.scan(), 0.4)

    # -------- Modals --------
    def open_filters(self):
        init = dict(notional=self.notional, min_pct=self.min_pct, min_abs=self.min_abs, quote=self.quote)
        def apply(cfg):
            self.notional = cfg["notional"]; self.min_pct = cfg["min_pct"]
            self.min_abs = cfg["min_abs"];   self.quote = cfg["quote"]
            self.scan()
        FiltersModal(init, on_apply=apply).open()

    def open_settings(self):
        init = dict(auto=self.auto, interval=int(self.interval),
                    strict_network=self.strict_network, ex_count=len(self.selected_exchs))
        def apply(cfg):
            self.strict_network = cfg["strict_network"]
            # (re)schedule auto
            if cfg["auto"]:
                self.interval = max(5, int(cfg["interval"] or 15))
                if self._ev: self._ev.cancel()
                self._ev = Clock.schedule_interval(lambda *_: self.scan(), self.interval)
            else:
                if self._ev: self._ev.cancel(); self._ev=None
            self.auto = cfg["auto"]
        def edit_exchanges():
            def done(sel):
                self.selected_exchs = set(sel) if sel else set(EXCH_FETCHERS.keys())
                self.scan()
            ExchangesModal(self.selected_exchs, on_done=done).open()
        SettingsModal(init, on_apply=apply, on_edit_exchanges=edit_exchanges).open()

    # -------- Scan --------
    def scan(self):
        if self.running: return
        self.running = True
        self.last_status = "Scanning..."
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        t0 = time.time()
        used = sorted(self.selected_exchs)
        books = aggregate(used)
        rows = find_opps(books, used, quote=self.quote, notional=self.notional,
                         min_pct=self.min_pct, min_abs=self.min_abs,
                         strict_network=self.strict_network)
        self._on_results(rows, used, t0)

    @mainthread
    def _on_results(self, rows, used, t0):
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
