# -*- coding: utf-8 -*-
import threading, time, requests
from functools import partial
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner

# ----------------------- Defaults -----------------------
DEFAULT_EXCHANGES = ["okx", "kucoin", "gate"]
DEFAULT_QUOTE = "USDT"

USER_AGENT = {"User-Agent": "Mozilla/5.0 ArbTracker/Android"}
REQ_TIMEOUT = 10

# جدول: عنوان، عرض به dp
COLS = [
    ("Symbol", 140),
    ("Buy(Ask)", 170),
    ("Sell(Bid)", 170),
    ("Net %", 100),
    ("Abs Profit", 120),
    ("Vol(k$)", 100),
    ("Transfer Fee", 110),
    ("Network", 110),
    ("Canon", 90),
]

# ----------------------- HTTP utils -----------------------
def http_get(url, timeout=REQ_TIMEOUT):
    try:
        r = requests.get(url, timeout=timeout, headers=USER_AGENT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# ----------------------- Public fetchers (no key) -----------------------
# خروجی هر fetcher:
# { "BASE/QUOTE": {"ask": float, "bid": float, "qv": float(QuoteVolume 24h $)} }

def fetch_okx():
    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    data = http_get(url)
    out = {}
    if not data or data.get("code") != "0":
        return out
    for it in data.get("data", []):
        inst = it.get("instId", "")
        if inst.count("-") != 1:
            continue
        base, quote = inst.split("-")
        try:
            ask = float(it.get("askPx") or 0) or 0.0
            bid = float(it.get("bidPx") or 0) or 0.0
        except Exception:
            continue
        # حجم: okx volCcy24h (quote) / vol24h (base) و last
        qv = 0.0
        try:
            qv = float(it.get("volCcy24h") or 0) or 0.0
            if qv == 0.0:
                base_vol = float(it.get("vol24h") or 0) or 0.0
                last = float(it.get("last") or 0) or 0.0
                qv = base_vol * last
        except Exception:
            pass
        out[f"{base}/{quote}"] = {"ask": ask, "bid": bid, "qv": qv}
    return out

def fetch_kucoin():
    url = "https://api.kucoin.com/api/v1/market/allTickers"
    data = http_get(url)
    out = {}
    if not data or data.get("code") != "200000":
        return out
    for it in data.get("data", {}).get("ticker", []):
        sym = (it.get("symbol") or "").upper().replace("-", "/")
        try:
            ask = float(it.get("sell") or 0) or 0.0  # kucoin: sell=best ask
            bid = float(it.get("buy") or 0) or 0.0   # kucoin: buy =best bid
        except Exception:
            continue
        qv = 0.0
        try:
            qv = float(it.get("volValue") or 0) or 0.0  # quote volume USD-ish
            if qv == 0.0:
                base_vol = float(it.get("vol") or 0) or 0.0
                last = float(it.get("last") or 0) or 0.0
                qv = base_vol * last
        except Exception:
            pass
        out[sym] = {"ask": ask, "bid": bid, "qv": qv}
    return out

def fetch_gate():
    url = "https://api.gateio.ws/api/v4/spot/tickers"
    data = http_get(url)
    out = {}
    if not isinstance(data, list):
        return out
    for it in data:
        sym = (it.get("currency_pair") or "").upper().replace("_", "/")
        try:
            ask = float(it.get("lowest_ask") or 0) or 0.0
            bid = float(it.get("highest_bid") or 0) or 0.0
        except Exception:
            continue
        qv = 0.0
        try:
            qv = float(it.get("quote_volume") or 0) or 0.0
        except Exception:
            pass
        out[sym] = {"ask": ask, "bid": bid, "qv": qv}
    return out

FETCHERS = {"okx": fetch_okx, "kucoin": fetch_kucoin, "gate": fetch_gate}

# ----------------------- Core scan -----------------------
def aggregate_books(exchanges, quote="USDT"):
    books = {}
    vols = {}
    for ex in exchanges:
        fn = FETCHERS.get(ex)
        if not fn:
            continue
        data = fn()
        for sym, v in data.items():
            if not sym.endswith("/" + quote):
                continue
            books.setdefault(sym, {})[ex] = {"ask": v["ask"], "bid": v["bid"]}
            vols.setdefault(sym, {})[ex] = v.get("qv", 0.0)
    return books, vols

def find_opps(books, vols, notional=1000.0, min_pct=0.05, min_abs=0.5,
              min_qv_usd=0.0, safe_bases=None, strict_name=False, strict_network=False):
    rows = []
    safe_set = set([s.strip().upper() for s in (safe_bases or []) if s.strip()])
    for sym, exmap in books.items():
        base, quote = sym.split("/")
        # فیلتر «Strict name»: اگر لیست امن ارائه شده، فقط همان‌ها
        if strict_name and safe_set and base not in safe_set:
            continue
        if len(exmap) < 2:
            continue
        for buy_ex, buy in exmap.items():
            for sell_ex, sell in exmap.items():
                if buy_ex == sell_ex:
                    continue
                ask, bid = buy["ask"], sell["bid"]
                if ask <= 0 or bid <= 0:
                    continue
                # حداقل حجم 24h در هر دو صرافی (Quote volume به دلار تقریبی)
                qv_buy = max(0.0, vols.get(sym, {}).get(buy_ex, 0.0))
                qv_sell = max(0.0, vols.get(sym, {}).get(sell_ex, 0.0))
                if min_qv_usd > 0 and (qv_buy < min_qv_usd or qv_sell < min_qv_usd):
                    continue
                # Strict network: با API عمومی نداریم => خروجی صفر برای جلوگیری از سیگنال اشتباه
                if strict_network:
                    continue

                pct = (bid - ask) / ask * 100.0
                abs_profit = (bid - ask) * (notional / max(ask, 1e-12))
                if pct >= min_pct and abs_profit >= min_abs:
                    volk = min(qv_buy, qv_sell) / 1000.0
                    rows.append({
                        "symbol": sym,
                        "buy": f"{buy_ex}@{ask:.10f}".rstrip('0').rstrip('.'),
                        "sell": f"{sell_ex}@{bid:.10f}".rstrip('0').rstrip('.'),
                        "pct": pct, "abs": abs_profit,
                        "volk": volk, "fee": "0", "net": "—", "canon": "—",
                    })
    rows.sort(key=lambda r: (r["pct"], r["volk"]), reverse=True)
    return rows

# ----------------------- UI -----------------------
class ExchangesPopup(Popup):
    def __init__(self, selected, on_apply, **kwargs):
        super().__init__(**kwargs)
        self.title = "Select Exchanges"
        self.size_hint = (0.9, 0.7)
        self.auto_dismiss = False
        self._selected = set(selected)

        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        grid = GridLayout(cols=2, spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))

        for ex in DEFAULT_EXCHANGES:
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(6))
            cb = CheckBox(active=(ex in self._selected), size_hint=(None, None), size=(dp(24), dp(24)))
            def _toggle(instance, val, exname=ex):
                if instance.active: self._selected.add(exname)
                else: self._selected.discard(exname)
            cb.bind(active=_toggle)
            row.add_widget(cb)
            row.add_widget(Label(text=ex.upper(), font_size=sp(15), halign="left", valign="middle"))
            grid.add_widget(row)

        sv = ScrollView(size_hint=(1,1), do_scroll_x=False, do_scroll_y=True, bar_width=dp(6))
        sv.add_widget(grid)
        root.add_widget(sv)

        btns = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(10))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        btns.add_widget(Button(text="Apply", on_release=lambda *_: (on_apply(sorted(self._selected)), self.dismiss())))
        root.add_widget(btns)

        self.content = root

class ArbAppUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(6),
                         padding=(dp(8), dp(8), dp(8), dp(4)), **kwargs)

        # Title
        self.add_widget(Label(text="Arbitrage Tracker — BASE transfer",
                              size_hint_y=None, height=dp(28), bold=True, font_size=sp(18)))

        # Controls 1
        ctrl = GridLayout(cols=10, size_hint_y=None, height=dp(44), spacing=dp(6))
        self.notional = TextInput(text="1000", multiline=False, input_filter="float", hint_text="Notional", font_size=sp(14))
        self.minpct = TextInput(text="0.05", multiline=False, input_filter="float", hint_text="Min %", font_size=sp(14))
        self.minabs = TextInput(text="0.5", multiline=False, input_filter="float", hint_text="Min Abs", font_size=sp(14))
        self.minqv  = TextInput(text="0", multiline=False, input_filter="float", hint_text="Min 24h $Vol", font_size=sp(14))
        self.quote  = TextInput(text=DEFAULT_QUOTE, multiline=False, hint_text="Quote", font_size=sp(14))

        ctrl.add_widget(Label(text="Notional", font_size=sp(12))); ctrl.add_widget(self.notional)
        ctrl.add_widget(Label(text="Min %", font_size=sp(12)));   ctrl.add_widget(self.minpct)
        ctrl.add_widget(Label(text="Min Abs", font_size=sp(12))); ctrl.add_widget(self.minabs)
        ctrl.add_widget(Label(text="Min 24h $Vol", font_size=sp(12))); ctrl.add_widget(self.minqv)
        ctrl.add_widget(Label(text="Quote", font_size=sp(12)));   ctrl.add_widget(self.quote)
        self.add_widget(ctrl)

        # Controls 2 (exchanges + auto refresh + stricts)
        line2 = GridLayout(cols=8, size_hint_y=None, height=dp(44), spacing=dp(6))
        self.exchanges = DEFAULT_EXCHANGES.copy()
        self.ex_btn = Button(text=f"Exchanges ({', '.join([e.upper() for e in self.exchanges])})")
        self.ex_btn.bind(on_release=self.open_exchanges)

        self.auto_cb = CheckBox(active=True)
        self.refresh_spinner = Spinner(text="15s", values=["5s","10s","15s","30s","60s"],
                                       size_hint=(None,None), size=(dp(90), dp(36)))
        self.refresh_spinner.bind(text=self._change_refresh)

        self.strict_name_cb = CheckBox(active=False)
        self.strict_net_cb  = CheckBox(active=False)

        self.safe_bases = TextInput(text="", hint_text="Safe bases e.g. BTC,ETH,SOL",
                                    multiline=False, font_size=sp(13))

        self.scan_btn = Button(text="Scan now", size_hint=(None,None), size=(dp(110), dp(36)))
        self.scan_btn.bind(on_release=lambda *_: self.start_scan())

        # Labels
        line2.add_widget(self.ex_btn)
        line2.add_widget(Label(text="Auto", font_size=sp(12)))
        line2.add_widget(self.auto_cb)
        line2.add_widget(self.refresh_spinner)
        line2.add_widget(Label(text="Strict name", font_size=sp(12)))
        line2.add_widget(self.strict_name_cb)
        line2.add_widget(Label(text="Strict network", font_size=sp(12)))
        line2.add_widget(self.strict_net_cb)

        self.add_widget(line2)

        # Safe bases + Scan
        line3 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        line3.add_widget(self.safe_bases)
        line3.add_widget(self.scan_btn)
        self.add_widget(line3)

        # Header + table (sync scroll)
        self.header_scroll = ScrollView(size_hint_y=None, height=dp(34),
                                        do_scroll_x=True, do_scroll_y=False, bar_width=0)
        self.body_scroll = ScrollView(size_hint=(1,1), do_scroll_x=True, do_scroll_y=True, bar_width=dp(6))
        self.body_scroll.bind(scroll_x=self._sync_header)

        self.header_grid = GridLayout(rows=1, size_hint_x=None, height=dp(34), spacing=dp(2))
        self.body_grid   = GridLayout(cols=len(COLS), size_hint_y=None, spacing=dp(2),
                                      row_default_height=dp(30), row_force_default=True)

        total_w = 0
        for title, w in COLS:
            lbl = Label(text=title, bold=True, font_size=sp(14), size_hint=(None,1), width=dp(w))
            self.header_grid.add_widget(lbl); total_w += dp(w)
        self.header_grid.width = total_w
        self.body_grid.bind(minimum_height=self.body_grid.setter("height"))

        self.header_scroll.add_widget(self.header_grid)
        self.body_scroll.add_widget(self.body_grid)
        self.add_widget(self.header_scroll)
        self.add_widget(self.body_scroll)

        # Status bar + توضیح strict
        self.status = Label(text="Last update: — | exchanges: —",
                            size_hint_y=None, height=dp(26), font_size=sp(12))
        self.note   = Label(text="Note: Strict network requires private APIs; when ON, results are suppressed.",
                            size_hint_y=None, height=dp(22), font_size=sp(11))
        self.add_widget(self.status)
        self.add_widget(self.note)

        # schedule
        self._timer = Clock.schedule_interval(lambda dt: self._auto_scan(), 15)
        Clock.schedule_once(lambda dt: self.start_scan(), 0.5)

    def _sync_header(self, *_):
        self.header_scroll.scroll_x = self.body_scroll.scroll_x

    def _change_refresh(self, spinner, text):
        val = int(text.replace("s", ""))
        if self._timer: self._timer.cancel()
        self._timer = Clock.schedule_interval(lambda dt: self._auto_scan(), val)

    def _auto_scan(self):
        if self.auto_cb.active:
            self.start_scan()

    def open_exchanges(self, *_):
        def _apply(selected):
            self.exchanges = selected or []
            if not self.exchanges:
                self.exchanges = DEFAULT_EXCHANGES.copy()
            self.ex_btn.text = f"Exchanges ({', '.join([e.upper() for e in self.exchanges])})"
        ExchangesPopup(self.exchanges, _apply).open()

    def start_scan(self):
        self.scan_btn.disabled = True
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _parse_floats(self):
        try: notional = float(self.notional.text or 0)
        except: notional = 1000.0
        try: min_pct = float(self.minpct.text or 0)
        except: min_pct = 0.05
        try: min_abs = float(self.minabs.text or 0)
        except: min_abs = 0.5
        try: min_qv = float(self.minqv.text or 0)
        except: min_qv = 0.0
        return notional, min_pct, min_abs, min_qv

    def _scan_worker(self):
        notional, min_pct, min_abs, min_qv = self._parse_floats()
        quote = (self.quote.text or DEFAULT_QUOTE).upper().strip()
        safe_bases = [x.strip() for x in (self.safe_bases.text or "").split(",") if x.strip()]
        strict_name = self.strict_name_cb.active
        strict_net  = self.strict_net_cb.active

        books, vols = aggregate_books(self.exchanges, quote=quote)
        rows = find_opps(books, vols, notional=notional, min_pct=min_pct,
                         min_abs=min_abs, min_qv_usd=min_qv, safe_bases=safe_bases,
                         strict_name=strict_name, strict_network=strict_net)
        self._update_table(rows, quote)

    @mainthread
    def _update_table(self, rows, quote):
        self.body_grid.clear_widgets()
        if not rows:
            msg = Label(text="No opportunities above thresholds right now.",
                        size_hint=(None,None), width=self.header_grid.width, height=dp(34),
                        font_size=sp(14), halign="left", valign="middle")
            msg.bind(size=lambda inst, val: setattr(inst, "text_size", val))
            self.body_grid.add_widget(msg)
            for _ in range(len(COLS)-1):
                self.body_grid.add_widget(Label(text="", size_hint=(None,None),
                                                width=dp(COLS[_][1]), height=dp(34)))
        else:
            for r in rows:
                vals = [
                    r["symbol"],
                    r["buy"],
                    r["sell"],
                    f"{r['pct']:.3f}%",
                    f"{r['abs']:.2f}",
                    f"{r['volk']:.1f}",
                    r["fee"],
                    r["net"],
                    r["canon"],
                ]
                for (title, w), val in zip(COLS, vals):
                    lab = Label(text=str(val), size_hint=(None,None), width=dp(w), height=dp(30),
                                font_size=sp(13), halign="left", valign="middle")
                    lab.bind(size=lambda inst, val: setattr(inst, "text_size", val))
                    self.body_grid.add_widget(lab)

        ts = datetime.now().strftime("%H:%M:%S")
        self.status.text = f"Last update: {ts}  |  exchanges: {', '.join(self.exchanges)}  |  quote: {quote}"
        self.scan_btn.disabled = False

class ArbApp(App):
    def build(self):
        Window.clearcolor = (0, 0, 0, 1)
        return ArbAppUI()

if __name__ == "__main__":
    ArbApp().run()
