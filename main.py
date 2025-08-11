# main.py
# -*- coding: utf-8 -*-
import time, requests
from collections import defaultdict
from threading import Thread
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

# ---------- settings ----------
TIMEOUT=12; RETRIES=2; SLP=0.15
EXCHANGES = ["okx","kucoin","gate"]   # strict/verified
FEES_TRADE={"okx":0.0008,"kucoin":0.001,"gate":0.001}
WITHDRAW_BASE_FEES={"BTC":{"BTC":0.0002},"ETH":{"ERC20":0.003}}  # sample
CONFLICTS={"ALTLAYER":{"aliases":{"okx":["ALT"],"gate":["ALT"]}}}
NOTIONAL=1000.0; MIN_PCT=0.01; MIN_ABS=0.05
QUOTES=("USDT","USDC")

# ---------- http ----------
def http_get(url, params=None, headers=None):
    for _ in range(RETRIES):
        try:
            r=requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code>=400: time.sleep(0.4); continue
            return r.json()
        except Exception:
            time.sleep(0.6)
    return None

def normalize_symbol(s):
    s=(s or "").upper()
    if '-' in s: b,q=s.split('-')
    elif '_' in s: b,q=s.split('_')
    else:
        QS=["USDT","USDC","BTC","ETH","EUR","USD","BUSD","TRY","UST"]
        q=None
        for e in sorted(QS,key=len,reverse=True):
            if s.endswith(e): q=e; b=s[:-len(e)]; break
        if not q: return s
        if q=="UST": q="USDT"
    return f"{b}/{q}"

# ---------- orderbooks ----------
def f_okx():
    out={}; j=http_get("https://www.okx.com/api/v5/market/tickers",{"instType":"SPOT"}) or {}
    for it in j.get("data",[]):
        sym=normalize_symbol(it.get("instId",""))
        try: bid=float(it["bidPx"]); ask=float(it["askPx"])
        except: continue
        if bid>0 and ask>0: out[sym]={"bid":bid,"ask":ask}
    return out

def f_kucoin():
    out={}; j=http_get("https://api.kucoin.com/api/v1/market/allTickers") or {}
    for it in j.get("data",{}).get("ticker",[]):
        sym=normalize_symbol(it.get("symbol",""))
        try: bid=float(it["bestBid"]); ask=float(it["bestAsk"])
        except: continue
        if bid>0 and ask>0: out[sym]={"bid":bid,"ask":ask}
    return out

def f_gate():
    out={}; j=http_get("https://api.gateio.ws/api/v4/spot/tickers") or []
    for it in j:
        sym=normalize_symbol(it.get("currency_pair",""))
        try: bid=float(it["highest_bid"]); ask=float(it["lowest_ask"])
        except: continue
        if bid>0 and ask>0: out[sym]={"bid":bid,"ask":ask}
    return out

FETCHERS={"okx":f_okx,"kucoin":f_kucoin,"gate":f_gate}

# ---------- base metadata ----------
def meta_okx():
    names=defaultdict(dict); nets=defaultdict(lambda: defaultdict(dict))
    j=http_get("https://www.okx.com/api/v5/asset/currencies") or {}
    for it in j.get("data",[]):
        b=(it.get("ccy") or "").upper(); chain=(it.get("chain") or "").upper()
        if not b or not chain: continue
        net=chain.split("-",1)[1] if "-" in chain else chain
        dep=str(it.get("canDep","1"))=="1"; wd=str(it.get("canWd","1"))=="1"
        c=(it.get("ctAddr") or "").strip() or None
        nets[b][net]={"dep":dep,"wd":wd,"contract":c}
    return names,nets

def meta_kucoin():
    names=defaultdict(dict); nets=defaultdict(lambda: defaultdict(dict))
    j=http_get("https://api.kucoin.com/api/v1/currencies") or {}
    for it in j.get("data",[]):
        b=(it.get("currency") or "").upper()
        full=(it.get("fullName") or it.get("name") or "").strip().lower()
        if b and full: names[b]["full_name"]=full
        for ch in it.get("chains",[]):
            net=(ch.get("chainName") or "").upper()
            dep=bool(ch.get("isDepositEnabled",True)); wd=bool(ch.get("isWithdrawEnabled",True))
            c=(ch.get("contractAddress") or "").strip() or None
            if b and net: nets[b][net]={"dep":dep,"wd":wd,"contract":c}
    return names,nets

def meta_gate():
    names=defaultdict(dict); nets=defaultdict(lambda: defaultdict(dict))
    j=http_get("https://api.gateio.ws/api/v4/spot/currencies") or []
    for it in j:
        b=(it.get("currency") or "").upper()
        full=(it.get("name") or "").strip().lower()
        net=(it.get("chain") or "").upper()
        dep=(it.get("deposit_disabled") in [0,False,None]); wd=(it.get("withdraw_disabled") in [0,False,None])
        if b and full: names[b]["full_name"]=full
        if b and net: nets[b][net]={"dep":dep,"wd":wd,"contract":None}
    return names,nets

META_FETCH={"okx":meta_okx,"kucoin":meta_kucoin,"gate":meta_gate}

def build_meta(exs):
    names_map={}; nets_map={}
    for ex in exs:
        try: nm,ns = META_FETCH[ex]()
        except Exception: nm,ns = {},{}
        names_map[ex]=nm; nets_map[ex]=ns; time.sleep(SLP)
    return names_map,nets_map

def canonical_name(ex, base, names_map):
    b=base.upper()
    nm=names_map.get(ex,{}).get(b,{}).get("full_name","")
    canon=(nm or b).strip().lower()
    for C,cfg in CONFLICTS.items():
        aliases=cfg.get("aliases",{})
        if ex in aliases and b in [t.upper() for t in aliases[ex]]: return C.lower()
    return canon

def aggregate(exs):
    books=defaultdict(dict)
    for ex in exs:
        try: data=FETCHERS[ex]()
        except Exception: data=None
        if not data: continue
        for sym,ba in data.items(): books[sym][ex]=ba
        time.sleep(SLP)
    return books

def pick_base_net(base, sell_ex, buy_ex, nets_map):
    b=base.upper()
    sell=nets_map.get(sell_ex,{}).get(b,{})
    buy =nets_map.get(buy_ex ,{}).get(b,{})
    feas=[]
    for net in set(sell.keys()) & set(buy.keys()):
        if sell[net].get("wd",False) and buy[net].get("dep",False):
            c1=sell[net].get("contract"); c2=buy[net].get("contract")
            if c1 and c2 and (c1.strip().lower()!=c2.strip().lower()): continue
            feas.append(net)
    return feas[0] if feas else None

def withdraw_fee_in_quote(base, net, sell_bid):
    fee_base={"BTC":{"BTC":0.0002},"ETH":{"ERC20":0.003}}.get(base.upper(),{}).get(net,0.0)
    return fee_base*sell_bid

def compute(books, names_map, nets_map, notional=NOTIONAL, min_pct=MIN_PCT, min_abs=MIN_ABS):
    opps=[]
    for sym,exd in books.items():
        if '/' not in sym: continue
        base,quote=sym.split('/')
        if QUOTES and quote not in QUOTES: continue
        best_buy=None; best_sell=None
        for ex,ba in exd.items():
            bid,ask=ba["bid"],ba["ask"]
            if ask>0 and (best_buy is None or ask<best_buy[1]): best_buy=(ex,ask)
            if bid>0 and (best_sell is None or bid>best_sell[1]): best_sell=(ex,bid)
        if not best_buy or not best_sell: continue
        buy_ex,buy_ask=best_buy; sell_ex,sell_bid=best_sell
        if buy_ex==sell_ex: continue

        c_buy=canonical_name(buy_ex,base,names_map); c_sel=canonical_name(sell_ex,base,names_map)
        if c_buy and c_sel and c_buy!=c_sel: continue

        net=pick_base_net(base,sell_ex,buy_ex,nets_map)
        if not net: continue

        buy_fee=FEES_TRADE.get(buy_ex,0.001); sell_fee=FEES_TRADE.get(sell_ex,0.001)
        tf_q=withdraw_fee_in_quote(base,net,sell_bid)
        net_sell=sell_bid*(1-sell_fee); net_buy=buy_ask*(1+buy_fee)
        net_unit=(net_sell-net_buy)-tf_q
        if net_buy<=0: continue
        pct=(net_unit/net_buy)*100.0
        units=(notional/buy_ask) if buy_ask>0 else 0
        abs_p=net_unit*units
        if pct>=min_pct and abs_p>=min_abs:
            opps.append((sym,f"{buy_ex}@{buy_ask:.8f}",f"{sell_ex}@{sell_bid:.8f}",
                         f"{pct:.3f}%", f"{abs_p:.2f}", f"{tf_q:.6f}", net, c_buy or c_sel))
    opps.sort(key=lambda x: float(x[3].replace('%','')), reverse=True)
    return opps[:50]

# ---------- UI ----------
class Table(GridLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cols=8
        self.size_hint_y=None
        self.bind(minimum_height=self.setter('height'))
        self.add_header()

    def add_header(self):
        headers=["Symbol","Buy(Ask)","Sell(Bid)","Net %","Abs Profit","Base Fee(Q)","Network","Canon"]
        for h in headers:
            self.add_widget(Label(text=f"[b]{h}[/b]", markup=True, size_hint_y=None, height=dp(36)))

    def load(self, rows):
        self.clear_widgets()
        self.add_header()
        if not rows:
            self.add_widget(Label(text="No opportunities above thresholds right now.",
                                  size_hint_y=None, height=dp(36)))
            for _ in range(7): self.add_widget(Label(size_hint_y=None, height=dp(36)))
            return
        for r in rows:
            for c in r:
                self.add_widget(Label(text=str(c), size_hint_y=None, height=dp(32)))

class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation='vertical', **kw)
        self.title = Label(text="[b]Arbitrage Tracker — BASE transfer[/b]", markup=True, size_hint_y=None, height=dp(40))
        self.add_widget(self.title)
        self.scroll=ScrollView()
        self.table=Table()
        self.scroll.add_widget(self.table)
        self.add_widget(self.scroll)
        self.status=Label(text="Initializing...", size_hint_y=None, height=dp(30))
        self.add_widget(self.status)

class ArbApp(App):
    def build(self):
        Window.clearcolor=(0.07,0.07,0.07,1)
        self.root_widget=Root()
        Clock.schedule_once(lambda dt: self.start_worker(), 0.5)
        return self.root_widget

    def start_worker(self):
        def worker():
            while True:
                try:
                    books=aggregate(EXCHANGES)
                    names,nets=build_meta(EXCHANGES)
                    rows=compute(books,names,nets)
                    Clock.schedule_once(lambda dt: self.root_widget.table.load(rows))
                    Clock.schedule_once(lambda dt: setattr(self.root_widget.status,'text', f"Last update: {time.strftime('%H:%M:%S')}  | exchanges: {', '.join(EXCHANGES)}"), 0)
                except Exception as e:
                    Clock.schedule_once(lambda dt: setattr(self.root_widget.status,'text', f"Error: {e}"), 0)
                time.sleep(15)
        Thread(target=worker, daemon=True).start()

if __name__=="__main__":
    ArbApp().run()
