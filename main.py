 # main.py — Kivy-only UI: Filter | Scan | Settings + جدول با هدر چسبان
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

import requests, time

# ---------- پیکربندی جدول ----------
COLUMNS = [
    ("Symbol", 0.20),
    ("Buy(Ask)", 0.24),
    ("Sell(Bid)", 0.24),
    ("Net %", 0.12),
    ("Abs Profit", 0.12),
    ("Fee", 0.08),
]

def col_px():
    w = max(360, Window.width)
    return [int(frac * w) for _, frac in COLUMNS]

UA = {"User-Agent": "Mozilla/5.0 (Kivy/ArbTracker)"}

def http_json(url, params=None):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=12)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None

# ---------- صرافی‌ها (API عمومی) ----------
def fetch_okx():
    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    j = http_json(url)
    books = {}
    if not j or j.get("code") != "0":
        return {"okx": books}
    for it in j.get("data", []):
        inst = it.get("instId", "")  # BTC-USDT
        if not inst.endswith("-USDT"):
            continue
        base = inst.split("-")[0]
        sym = f"{base}/USDT"
        try:
            ask = float(it.get("askPx") or 0)
            bid = float(it.get("bidPx") or 0)
        except Exception:
            ask = bid = 0.0
        if ask > 0 and bid > 0:
            books[sym] = {"ask": ask, "bid": bid}
    return {"okx": books}

def fetch_kucoin():
    url = "https://api.kucoin.com/api/v1/market/allTickers"
    j = http_json(url)
    books = {}
    if not j or j.get("code") != "200000":
        return {"kucoin": books}
    for it in j["data"].get("ticker", []):
        sym = it.get("symbol", "")  # BTC-USDT
        if not sym.endswith("-USDT"):
            continue
        base = sym.split("-")[0]
        ksym = f"{base}/USDT"
        try:
            ask = float(it.get("sell") or 0)
            bid = float(it.get("buy") or 0)
        except Exception:
            ask = bid = 0.0
        if ask > 0 and bid > 0:
            books[ksym] = {"ask": ask, "bid": bid}
    return {"kucoin": books}

def fetch_gate():
    url = "https://api.gateio.ws/api/v4/spot/tickers"
    j = http_json(url)
    books = {}
    if not isinstance(j, list):
        return {"gate": books}
    for it in j:
        pair = it.get("currency_pair", "")  # BTC_USDT
        if not pair.endswith("_USDT"):
            continue
        base = pair.split("_")[0]
        gsym = f"{base}/USDT"
        try:
            ask = float(it.get("lowest_ask") or 0)
            bid = float(it.get("highest_bid") or 0)
        except Exception:
            ask = bid = 0.0
        if ask > 0 and bid > 0:
            books[gsym] = {"ask": ask, "bid": bid}
    return {"gate": books}

FETCHERS = [fetch_okx, fetch_kucoin, fetch_gate]

def aggregate_books():
    books = {}
    enabled = []
    for fn in FETCHERS:
        d = fn()
        if not d:
            continue
        ex, bk = list(d.items())[0]
        books[ex] = bk
        enabled.append(ex)
    return books, enabled

def calc_opps(books, min_pct=0.05, min_abs=0.5, notional=1000.0):
    syms = set()
    for ex in books:
        syms |= set(books[ex].keys())
    rows = []
    for s in syms:
        best_buy = None   # (ex, ask)
        best_sell = None  # (ex, bid)
        for ex, bk in books.items():
            q = bk.get(s)
            if not q:
                continue
            ask, bid = q["ask"], q["bid"]
            if ask > 0:
                if (best_buy is None) or (ask < best_buy[1]):
                    best_buy = (ex, ask)
            if bid > 0:
                if (best_sell is None) or (bid > best_sell[1]):
                    best_sell = (ex, bid)
        if not best_buy or not best_sell:
            continue
        buy_ex, ask = best_buy
        sell_ex, bid = best_sell
        if buy_ex == sell_ex:
            continue
        pct = (bid / ask - 1.0) * 100.0
        abs_profit = (bid - ask) * (notional / ask)
        if pct >= min_pct and abs_profit >= min_abs:
            rows.append({
                "symbol": s,
                "buy": f"{buy_ex}@{ask:.8f}",
                "sell": f"{sell_ex}@{bid:.8f}",
                "pct": pct,
                "abs": abs_profit,
                "fee": "0",
            })
    rows.sort(key=lambda r: r["pct"], reverse=True)
    return rows

# ---------- UI ----------
class Header(GridLayout):
    widths = ListProperty([])

    def __init__(self, **kw):
        super().__init__(**kw)
        self.cols = len(COLUMNS)
        self.size_hint_y = None
        self.height = dp(40)
        self.spacing = dp(8)
        self.padding = (dp(8), 0)
        self.bind(widths=self._rebuild)
        self._rebuild()

    def _rebuild(self, *a):
        self.clear_widgets()
        ws = self.widths or col_px()
        for i, (title, _) in enumerate(COLUMNS):
            lbl = Label(text=f"[b]{title}[/b]", markup=True,
                        size_hint=(None, 1), width=ws[i],
                        halign="left", valign="middle")
            lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
            self.add_widget(lbl)

class Table(GridLayout):
    widths = ListProperty([])

    def __init__(self, **kw):
        super().__init__(**kw)
        self.cols = len(COLUMNS)
        self.spacing = dp(8)
        self.padding = (dp(8), dp(6))
        self.size_hint_x = None
        self.bind(minimum_height=self.setter("height"))

    def set_rows(self, rows):
        self.clear_widgets()
        ws = self.widths or col_px()
        self.width = sum(ws) + dp(8) * (len(COLUMNS) - 1) + dp(16)
        for r in rows:
            data = [
                r["symbol"], r["buy"], r["sell"],
                f"{r['pct']:.3f}%", f"{r['abs']:.2f}", r["fee"]
            ]
            for i, val in enumerate(data):
                lbl = Label(text=str(val), size_hint=(None, None),
                            width=ws[i], height=dp(40),
                            halign="left" if i not in (3, 4, 5) else "right",
                            valign="middle")
                lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
                self.add_widget(lbl)

class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = "vertical"
        self.spacing = dp(6)
        self.padding = (dp(8), dp(8))

        # نوار بالا: Filter | Scan | Settings
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        btn_filter = Button(text="Filter")
        btn_scan   = Button(text="Scan")
        btn_set    = Button(text="Settings")
        btn_filter.bind(on_release=self.open_filter)
        btn_set.bind(on_release=self.open_settings)
        btn_scan.bind(on_release=self.scan_now)
        top.add_widget(btn_filter); top.add_widget(btn_scan); top.add_widget(btn_set)
        self.add_widget(top)

        # هدر
        self.header_sv = ScrollView(do_scroll_x=True, do_scroll_y=False,
                                    bar_width=0, size_hint_y=None, height=dp(40))
        self.header = Header(widths=col_px())
        self.header_sv.add_widget(self.header)
        self.add_widget(self.header_sv)

        # بدنه
        self.body_sv = ScrollView(do_scroll_x=True, do_scroll_y=True, bar_width=dp(4))
        self.table = Table(widths=col_px())
        self.table_holder = BoxLayout(size_hint_y=1, size_hint_x=None)
        self.table_holder.bind(minimum_width=self.table_holder.setter("width"))
        self.table_holder.add_widget(self.table)
        self.body_sv.add_widget(self.table_holder)
        self.add_widget(self.body_sv)

        # سینک اسکرول افقی
        self.body_sv.bind(scroll_x=lambda inst, val: setattr(self.header_sv, "scroll_x", val))
        self.header_sv.bind(scroll_x=lambda inst, val: setattr(self.body_sv, "scroll_x", val))

        # وضعیت
        self.status = Label(text="Ready", size_hint_y=None, height=dp(24))
        self.add_widget(self.status)

        # حالت‌ها
        self.state = {
            "min_pct": 0.05,
            "min_abs": 0.5,
            "notional": 1000.0,
            "interval": 15,
        }
        Window.bind(on_resize=lambda *a: self._on_resize())
        Clock.schedule_once(lambda dt: self.scan_now(), 0.2)
        self.auto_event = Clock.schedule_interval(lambda dt: self.scan_now(auto=True), self.state["interval"])

    def _on_resize(self):
        ws = col_px()
        self.header.widths = ws
        self.table.widths = ws
        # refresh محتوا
        self.table.set_rows(getattr(self, "_last_rows", []))

    def set_status(self, txt):
        self.status.text = txt

    # ---- پاپاپ‌ها ----
    def open_filter(self, *a):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        lbl1 = Label(text="Min %:");     inp1 = self._ti(str(self.state["min_pct"]))
        lbl2 = Label(text="Min Abs:");   inp2 = self._ti(str(self.state["min_abs"]))
        lbl3 = Label(text="Notional:");  inp3 = self._ti(str(int(self.state["notional"])))
        row1 = BoxLayout(size_hint_y=None, height=dp(36)); row1.add_widget(lbl1); row1.add_widget(inp1)
        row2 = BoxLayout(size_hint_y=None, height=dp(36)); row2.add_widget(lbl2); row2.add_widget(inp2)
        row3 = BoxLayout(size_hint_y=None, height=dp(36)); row3.add_widget(lbl3); row3.add_widget(inp3)
        btns = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        ok = Button(text="Apply"); cl = Button(text="Close")
        btns.add_widget(ok); btns.add_widget(cl)
        box.add_widget(row1); box.add_widget(row2); box.add_widget(row3); box.add_widget(btns)
        pop = Popup(title="Filter", content=box, size_hint=(0.9, 0.5))
        cl.bind(on_release=lambda *_: pop.dismiss())
        def apply(*_):
            try:
                self.state["min_pct"] = float(inp1.text or 0)
                self.state["min_abs"] = float(inp2.text or 0)
                self.state["notional"] = float(inp3.text or 0)
            except Exception:
                pass
            pop.dismiss(); self.scan_now()
        ok.bind(on_release=apply)
        pop.open()

    def open_settings(self, *a):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        lbl = Label(text="Auto refresh (s):"); inp = self._ti(str(self.state["interval"]))
        row = BoxLayout(size_hint_y=None, height=dp(36)); row.add_widget(lbl); row.add_widget(inp)
        btns = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        ok = Button(text="Save"); cl = Button(text="Close")
        btns.add_widget(ok); btns.add_widget(cl)
        box.add_widget(row); box.add_widget(btns)
        pop = Popup(title="Settings", content=box, size_hint=(0.8, 0.35))
        cl.bind(on_release=lambda *_: pop.dismiss())
        def save_it(*_):
            try:
                iv = int(inp.text)
                iv = max(5, min(120, iv))
                self.state["interval"] = iv
                if self.auto_event: self.auto_event.cancel()
                self.auto_event = Clock.schedule_interval(lambda dt: self.scan_now(auto=True), iv)
            except Exception:
                pass
            pop.dismiss()
        ok.bind(on_release=save_it)
        pop.open()

    def _ti(self, text):
        # TextInput سبک — از Label برای سادگی استفاده نمی‌کنیم که پیچیده نشه.
        from kivy.uix.textinput import TextInput
        ti = TextInput(text=text, multiline=False, write_tab=False)
        return ti

    # ---- اسکن ----
    def scan_now(self, *a, auto=False):
        t0 = time.time()
        books, enabled = aggregate_books()
        rows = calc_opps(
            books,
            min_pct=self.state["min_pct"],
            min_abs=self.state["min_abs"],
            notional=self.state["notional"],
        )
        self._last_rows = rows
        self.table.set_rows(rows)
        took = time.time() - t0
        ts = time.strftime("%H:%M:%S")
        self.set_status(f"Last update: {ts} | exchanges: {', '.join(enabled) or '—'} | {len(rows)} rows | {took:.1f}s")

class ArbApp(App):
    def build(self):
        # پس‌زمینه‌ی روشن
        Window.clearcolor = (1, 1, 1, 1)
        return Root()

if __name__ == "__main__":
    ArbApp().run()
