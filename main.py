# -*- coding: utf-8 -*-
# Arbitrage Tracker — minimal UI (Filters | Scan | Settings) + synced header/body
import time, threading, requests
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
from kivy.uix.switch import Switch
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget

# ---------------- HTTP ----------------
def http_get(url, headers=None, timeout=12):
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# ---------------- Fetchers (Public) ----------------
def fetch_binance():
    data = http_get("https://api.binance.com/api/v3/ticker/bookTicker") or []
    out = {}
    for it in data:
        s = it["symbol"]
        if   s.endswith("USDT"): base, q = s[:-4], "USDT"
        elif s.endswith("USDC"): base, q = s[:-4], "USDC"
        else: continue
        out[f"{base}/{q}"] = {"ask": float(it["askPrice"]), "bid": float(it["bidPrice"])}
    return out

def fetch_okx():
    d = http_get("https://www.okx.com/api/v5/market/tickers?instType=SPOT") or {}
    if str(d.get("code")) != "0": return {}
    out = {}
    for it in d.get("data", []):
        inst = it["instId"]
        if "-USDT" in inst or "-USDC" in inst:
            base, q = inst.split("-")
            out[f"{base}/{q}"] = {"ask": float(it["askPx"]), "bid": float(it["bidPx"])}
    return out

def fetch_kucoin():
    d = http_get("https://api.kucoin.com/api/v1/market/allTickers") or {}
    if d.get("code") != "200000": return {}
    out = {}
    for it in d["data"]["ticker"]:
        sym = it["symbol"]
        if sym.endswith("-USDT") or sym.endswith("-USDC"):
            base, q = sym.split("-")
            ask = float((it.get("sell") or it.get("bestAskPrice") or 0) or 0)
            bid = float((it.get("buy")  or it.get("bestBidPrice") or 0) or 0)
            out[f"{base}/{q}"] = {"ask": ask, "bid": bid}
    return out

def fetch_gate():
    d = http_get("https://api.gateio.ws/api/v4/spot/tickers", headers={"Accept":"application/json"}) or []
    out = {}
    for it in d:
        pair = it["currency_pair"]
        if pair.endswith("_USDT") or pair.endswith("_USDC"):
            base, q = pair.split("_")
            out[f"{base}/{q}"] = {"ask": float(it.get("lowest_ask") or 0),
                                  "bid": float(it.get("highest_bid") or 0)}
    return out

def fetch_mexc():
    d = http_get("https://api.mexc.com/api/v3/ticker/bookTicker") or []
    out = {}
    for it in d:
        s = it["symbol"]
        if   s.endswith("USDT"): base, q = s[:-4], "USDT"
        elif s.endswith("USDC"): base, q = s[:-4], "USDC"
        else: continue
        out[f"{base}/{q}"] = {"ask": float(it["askPrice"]), "bid": float(it["bidPrice"])}
    return out

def fetch_bybit():
    d = http_get("https://api.bybit.com/v5/market/tickers?category=spot") or {}
    if str(d.get("retCode")) != "0": return {}
    out = {}
    for it in d["result"]["list"]:
        s = it["symbol"]
        if   s.endswith("USDT"): base, q = s[:-4], "USDT"
        elif s.endswith("USDC"): base, q = s[:-4], "USDC"
        else: continue
        out[f"{base}/{q}"] = {"ask": float(it["ask1Price"]), "bid": float(it["bid1Price"])}
    return out

# --- public-only additions ---
def fetch_poloniex():
    d = http_get("https://poloniex.com/public?command=returnTicker") or {}
    out = {}
    for k, it in d.items():
        if "_" not in k: continue
        q, base = k.split("_", 1)
        if q not in ("USDT","USDC"): continue
        ask = float(it.get("lowestAsk") or 0); bid = float(it.get("highestBid") or 0)
        if ask and bid: out[f"{base}/{q}"] = {"ask": ask, "bid": bid}
    return out

def fetch_hitbtc():
    d = http_get("https://api.hitbtc.com/api/3/public/ticker") or {}
    out = {}
    for sym, it in d.items():
        if   sym.endswith("USDT"): base, q = sym[:-4], "USDT"
        elif sym.endswith("USDC"): base, q = sym[:-4], "USDC"
        else: continue
        ask = float(it.get("ask") or 0); bid = float(it.get("bid") or 0)
        if ask and bid: out[f"{base}/{q}"] = {"ask": ask, "bid": bid}
    return out

def fetch_bitget():
    d = http_get("https://api.bitget.com/api/spot/v1/market/tickers") or {}
    out = {}
    for it in (d.get("data") or []):
        sym = (it.get("symbol") or "").replace("_SPBL","")
        if   sym.endswith("USDT"): base, q = sym[:-4], "USDT"
        elif sym.endswith("USDC"): base, q = sym[:-4], "USDC"
        else: continue
        ask = float(it.get("bestAsk") or it.get("askPx") or 0)
        bid = float(it.get("bestBid") or it.get("bidPx") or 0)
        if ask and bid: out[f"{base}/{q}"] = {"ask": ask, "bid": bid}
    return out

def fetch_bitrue():
    for url in ("https://www.bitrue.com/api/v3/ticker/bookTicker",
                "https://www.bitrue.com/api/v1/ticker/bookTicker"):
        d = http_get(url)
        if not d: continue
        out = {}
        for it in d:
            s = it.get("symbol") or ""
            if   s.endswith("USDT"): base, q = s[:-4], "USDT"
            elif s.endswith("USDC"): base, q = s[:-4], "USDC"
            else: continue
            out[f"{base}/{q}"] = {"ask": float(it["askPrice"]), "bid": float(it["bidPrice"])}
        if out: return out
    return {}

EXCH_FETCHERS = {
    "binance": fetch_binance, "okx": fetch_okx, "kucoin": fetch_kucoin,
    "gate": fetch_gate, "mexc": fetch_mexc, "bybit": fetch_bybit,
    "poloniex": fetch_poloniex, "hitbtc": fetch_hitbtc, "bitget": fetch_bitget, "bitrue": fetch_bitrue,
}

def guess_network(exchange:str, base:str):
    return None  # بعداً با API خصوصی کامل می‌کنیم

# ---------------- Core ----------------
def aggregate(exchs):
    out = {}
    for ex in exchs:
        try: book = EXCH_FETCHERS[ex]()
        except Exception: book = {}
        for sym, px in book.items():
            out.setdefault(sym, {})[ex] = px
    return out

def find_opps(books, selected, quote="USDT", notional=1000.0, min_pct=0.1, min_abs=0.05, strict_network=False):
    sel = set(selected)
    rows = []
    for sym, mp in books.items():
        base, q = sym.split("/")
        if q != quote: continue
        for b_ex, b in mp.items():
            if b_ex not in sel: continue
            ask = b.get("ask") or 0
            if ask <= 0: continue
            for s_ex, s in mp.items():
                if s_ex == b_ex or s_ex not in sel: continue
                bid = s.get("bid") or 0
                if bid <= 0: continue
                pct = (bid-ask)/ask*100.0
                abs_profit = (bid-ask)*(notional/ask)
                nb, ns = guess_network(b_ex, base), guess_network(s_ex, base)
                if strict_network and (nb is None or ns is None or nb != ns): continue
                if pct >= min_pct and abs_profit >= min_abs:
                    rows.append({
                        "sym": sym,
                        "buy": f"{b_ex}@{ask:.8f}",
                        "sell": f"{s_ex}@{bid:.8f}",
                        "pct": pct, "abs": abs_profit,
                        "net": nb if nb else "—",
                        "canon": "✓" if (nb and ns and nb==ns) else "—",
                    })
    rows.sort(key=lambda r: (-r["pct"], -r["abs"]))
    return rows

# ---------------- UI ----------------
COLS = [
    ("Symbol", dp(150)), ("Buy(Ask)", dp(170)), ("Sell(Bid)", dp(170)),
    ("Net %", dp(90)), ("Abs Profit", dp(120)), ("Network", dp(120)), ("Canon", dp(80)),
]
TOTAL_W = sum(w for _, w in COLS)

def header_grid():
    g = GridLayout(cols=len(COLS), size_hint=(None,None), height=dp(30), width=TOTAL_W,
                   padding=[dp(6),0], spacing=dp(6))
    for title, w in COLS:
        g.add_widget(Label(text=f"[b]{title}[/b]", markup=True,
                           size_hint=(None,1), width=w, font_size=sp(13)))
    return g

class DataGrid(GridLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cols = len(COLS)
        self.size_hint = (None, None)
        self.spacing = dp(6); self.padding = [dp(6), 0]
        self.width = TOTAL_W
        self.bind(minimum_height=self.setter("height"))
    def set_rows(self, rows):
        self.clear_widgets()
        for r in rows:
            cells = [r["sym"], r["buy"], r["sell"], f"{r['pct']:.3f}%", f"{r['abs']:.2f}", r["net"], r["canon"]]
            for (title, w), val in zip(COLS, cells):
                self.add_widget(Label(text=val, size_hint=(None,None),
                                      width=w, height=dp(28), font_size=sp(12)))

# -------- Modals --------
class FiltersModal(ModalView):
    def __init__(self, init, on_apply, **kw):
        super().__init__(**kw)
        self.size_hint=(0.92,0.64); self.background_color=(0,0,0,0.7); self.auto_dismiss=False
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        r1 = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        r2 = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.t_notional = TextInput(text=str(int(init["notional"])), input_filter="int", hint_text="Notional")
        self.t_minpct  = TextInput(text=str(init["min_pct"]), input_filter="float", hint_text="Min %")
        self.t_minabs  = TextInput(text=str(init["min_abs"]), input_filter="float", hint_text="Min Abs")
        self._quote = init["quote"]
        b_usdt = Button(text="USDT", on_release=lambda *_: self._setq("USDT"))
        b_usdc = Button(text="USDC", on_release=lambda *_: self._setq("USDC"))
        self._btns = (b_usdt, b_usdc)
        self._refresh_q()
        r1.add_widget(self.t_notional); r1.add_widget(self.t_minpct)
        r2.add_widget(self.t_minabs);   r2.add_widget(b_usdt); r2.add_widget(b_usdc)
        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        def apply(*_):
            cfg = dict(
                notional=float(self.t_notional.text or 1000),
                min_pct=float(self.t_minpct.text or 0.1),
                min_abs=float(self.t_minabs.text or 0.05),
                quote=self._quote,
            )
            on_apply(cfg); self.dismiss()
        btns.add_widget(Button(text="Apply", on_release=apply))
        root.add_widget(Label(text="[b]Filters[/b]", markup=True, size_hint=(1,None), height=dp(24)))
        root.add_widget(r1); root.add_widget(r2); root.add_widget(btns)
        self.add_widget(root)
    def _setq(self, q): self._quote=q; self._refresh_q()
    def _refresh_q(self):
        for b in self._btns:
            sel = (b.text == self._quote)
            b.background_color = (0.2,0.6,1,1) if sel else (0.25,0.25,0.25,1)

class ExchangesModal(ModalView):
    def __init__(self, selected:set, on_done, **kw):
        super().__init__(**kw)
        self.size_hint=(0.92,0.7); self.background_color=(0,0,0,0.7); self.auto_dismiss=False
        self.sel=set(selected)
        grid = GridLayout(cols=2, spacing=dp(8), size_hint=(1,None))
        grid.bind(minimum_height=grid.setter("height"))
        for ex in EXCH_FETCHERS.keys():
            row = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(42))
            sw = Switch(active=(ex in self.sel))
            def toggle(inst, val, name=ex):
                if val: self.sel.add(name)
                else:   self.sel.discard(name)
            sw.bind(active=toggle)
            row.add_widget(Label(text=ex.capitalize(), size_hint=(1,1)))
            row.add_widget(sw)
            grid.add_widget(row)
        sc = ScrollView(); sc.add_widget(grid)
        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        btns.add_widget(Button(text="Apply", on_release=lambda *_: (on_done(self.sel), self.dismiss())))
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        root.add_widget(Label(text="[b]Exchanges[/b]", markup=True, size_hint=(1,None), height=dp(24)))
        root.add_widget(sc); root.add_widget(btns)
        self.add_widget(root)

class SettingsModal(ModalView):
    def __init__(self, init, on_apply, on_edit_exchanges, **kw):
        super().__init__(**kw)
        self.size_hint=(0.92,0.64); self.background_color=(0,0,0,0.7); self.auto_dismiss=False
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        r1 = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.sw_auto = Switch(active=init["auto"])
        self.t_interval = TextInput(text=str(init["interval"]), input_filter="int", hint_text="sec")
        r1.add_widget(Label(text="Auto refresh")); r1.add_widget(self.sw_auto)
        r1.add_widget(Label(text="Interval"));     r1.add_widget(self.t_interval)
        r2 = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.sw_strict = Switch(active=init["strict_network"])
        r2.add_widget(Label(text="Strict base network")); r2.add_widget(self.sw_strict)
        exbtn = Button(text=f"Select Exchanges ({init['ex_count']})",
                       on_release=lambda *_:(self.dismiss(), on_edit_exchanges()),
                       size_hint=(1,None), height=dp(44))
        btns = BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Close", on_release=lambda *_: self.dismiss()))
        def apply(*_):
            cfg = dict(auto=self.sw_auto.active,
                       interval=int(self.t_interval.text or 15),
                       strict_network=self.sw_strict.active)
            on_apply(cfg); self.dismiss()
        btns.add_widget(Button(text="Apply", on_release=apply))
        root.add_widget(Label(text="[b]Settings[/b]", markup=True, size_hint=(1,None), height=dp(24)))
        root.add_widget(r1); root.add_widget(r2); root.add_widget(exbtn); root.add_widget(btns)
        self.add_widget(root)

# ---------------- Root ----------------
class Root(BoxLayout):
    running = BooleanProperty(False)
    notional = NumericProperty(1000.0)
    min_pct = NumericProperty(0.1)
    min_abs = NumericProperty(0.05)
    quote = StringProperty("USDT")
    auto = BooleanProperty(True)
    interval = NumericProperty(15)
    strict_network = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation="vertical"
        self.selected_exchs = {"okx","kucoin","gate"}

        # Top bar: [Filters]  --center Scan--  [Settings]
        top = BoxLayout(size_hint=(1,None), height=dp(50), padding=[dp(8),0], spacing=dp(8))
        btn_filters = Button(text="Filters", size_hint=(None,1), width=dp(88),
                             on_release=lambda *_: self.open_filters())
        spacer_left = Widget(size_hint=(1,1))
        btn_scan = Button(text="Scan", size_hint=(None,1), width=dp(72),
                          on_release=lambda *_: self.scan())
        spacer_right = Widget(size_hint=(1,1))
        btn_settings = Button(text="Settings", size_hint=(None,1), width=dp(96),
                              on_release=lambda *_: self.open_settings())
        top.add_widget(btn_filters); top.add_widget(spacer_left)
        top.add_widget(btn_scan); top.add_widget(spacer_right); top.add_widget(btn_settings)
        self.add_widget(top)

        # Sticky header + synced scroll
        self.header_grid = header_grid()
        self.header_scroll = ScrollView(do_scroll_x=True, do_scroll_y=False, bar_width=0,
                                        size_hint=(1,None), height=dp(30))
        self.header_scroll.add_widget(self.header_grid)
        self.add_widget(self.header_scroll)

        self.data_grid = DataGrid()
        self.data_scroll = ScrollView(do_scroll_x=True, do_scroll_y=True, size_hint=(1,1))
        self.data_scroll.add_widget(self.data_grid)
        self.add_widget(self.data_scroll)

        # sync X scroll
        self._syncing = False
        def from_head(_, val):
            if self._syncing: return
            self._syncing = True; self.data_scroll.scroll_x = val; self._syncing = False
        def from_body(_, val):
            if self._syncing: return
            self._syncing = True; self.header_scroll.scroll_x = val; self._syncing = False
        self.header_scroll.bind(scroll_x=from_head)
        self.data_scroll.bind(scroll_x=from_body)

        # auto refresh
        self._ev = Clock.schedule_interval(lambda *_: self.scan(), self.interval) if self.auto else None
        Clock.schedule_once(lambda *_: self.scan(), 0.4)

    # ---- dialogs ----
    def open_filters(self):
        init = dict(notional=self.notional, min_pct=self.min_pct, min_abs=self.min_abs, quote=self.quote)
        def apply(cfg):
            self.notional = cfg["notional"]; self.min_pct = cfg["min_pct"]; self.min_abs = cfg["min_abs"]
            self.quote = cfg["quote"]; self.scan()
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
                if self._ev: self._ev.cancel(); self._ev=None
            self.auto = cfg["auto"]
        def edit_exchanges():
            def done(sel):
                self.selected_exchs = set(sel) if sel else set(EXCH_FETCHERS.keys())
                self.scan()
            ExchangesModal(self.selected_exchs, on_done=done).open()
        SettingsModal(init, on_apply=apply, on_edit_exchanges=edit_exchanges).open()

    # ---- scan ----
    def scan(self):
        if self.running: return
        self.running=True
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        used = sorted(self.selected_exchs)
        books = aggregate(used)
        rows = find_opps(books, used, quote=self.quote, notional=self.notional,
                         min_pct=self.min_pct, min_abs=self.min_abs,
                         strict_network=self.strict_network)
        self._on_results(rows)

    @mainthread
    def _on_results(self, rows):
        self.data_grid.set_rows(rows)
        self.running=False

class ArbApp(App):
    def build(self):
        from kivy.core.window import Window
        Window.clearcolor = (0.06,0.06,0.06,1)
        return Root()

if __name__ == "__main__":
    ArbApp().run()
