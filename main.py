# -*- coding: utf-8 -*-
# ArbTracker APK (Kivy) — Real-Only + Private-API Gated
import os, json, time, hmac, hashlib, base64, secrets, threading
from typing import Dict, List, Optional, Tuple
import urllib.parse as urlparse
import requests
import pyaes  # AES-CTR (pure python)

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

TIMEOUT = 15
UA = {"User-Agent": "ArbTrackerAPK/1.0"}

# ---------- HTTP ----------
def http_get(url, params=None, headers=None, timeout=TIMEOUT):
    try:
        hh = dict(UA); 
        if headers: hh.update(headers)
        r = requests.get(url, params=params or {}, headers=hh, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def http_post(url, data=None, headers=None, timeout=TIMEOUT):
    try:
        hh = dict(UA); 
        if headers: hh.update(headers)
        r = requests.post(url, data=data or {}, headers=hh, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def now_ms(): return int(time.time()*1000)

# ---------- Normalization ----------
CHAIN_MAP = {
    "ETHEREUM":"ERC20","ERC20":"ERC20","ETH":"ERC20",
    "BEP20":"BEP20","BSC":"BEP20","BINANCE SMART CHAIN":"BEP20",
    "TRON":"TRC20","TRC20":"TRC20","TRX":"TRC20",
    "ARBITRUM":"ARB","ARBITRUM ONE":"ARB","ARB":"ARB",
    "OPTIMISM":"OP","OP":"OP",
    "MATIC":"POLYGON","POLYGON":"POLYGON","POL":"POLYGON",
    "AVALANCHE":"AVAXC","AVAXC":"AVAXC","AVALANCHE C-CHAIN":"AVAXC",
    "SOL":"SOL","SOLANA":"SOL",
    "BASE":"BASE","TON":"TON","SUI":"SUI","APTOS":"APTOS",
    "BTC":"BTC","BITCOIN":"BTC","LTC":"LTC","LITECOIN":"LTC"
}
def norm_chain(s: str)->Optional[str]:
    if not s: return None
    u = s.strip().upper()
    if "-" in u: u = u.split("-")[-1]
    return CHAIN_MAP.get(u, u)

def norm_pairkey(s: str)->str:
    return (s or "").upper().replace("-","").replace("_","")

def same_contract(a: Optional[str], b: Optional[str])->bool:
    if not a and not b: return True
    if not a or not b: return False
    return a.strip().lower()==b.strip().lower()

# ---------- Signing ----------
def sign_qs_sha256(params: dict, secret: str):
    qs = urlparse.urlencode(params)
    sig = hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    return qs + "&signature=" + sig

def sign_okx(method: str, path: str, body: str, ts: str, secret: str):
    msg = (ts + method.upper() + path + (body or "")).encode()
    mac = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return base64.b64encode(mac).decode()

def kraken_private(path: str, data: dict, key: str, secret_b64: str):
    nonce = str(now_ms())
    payload = dict(data or {}); payload["nonce"]=nonce
    postdata = urlparse.urlencode(payload)
    sha256 = hashlib.sha256((nonce+postdata).encode()).digest()
    mac = hmac.new(base64.b64decode(secret_b64), path.encode()+sha256, hashlib.sha512)
    headers = {"API-Key":key,"API-Sign":base64.b64encode(mac.digest()).decode(),"Content-Type":"application/x-www-form-urlencoded", **UA}
    url = "https://api.kraken.com"+path
    try:
        r = requests.post(url, data=postdata, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        j = r.json()
        if j.get("error"): return None
        return j.get("result")
    except Exception:
        return None

# ---------- Network caches ----------
class NetCache: 
    def __init__(self): self.store={}
    def get(self,ex): return self.store.get(ex)
    def set(self,ex,v): self.store[ex]=v
NET = NetCache()

# ---------- Networks per exchange ----------
def nets_binance(keys):
    if NET.get("binance"): return NET.get("binance")
    k, s = keys.get("api_key"), keys.get("secret")
    if not (k and s): return {}
    params={"timestamp":now_ms(),"recvWindow":5000}
    qs = sign_qs_sha256(params, s)
    url = "https://api.binance.com/sapi/v1/capital/config/getall?"+qs
    j = http_get(url, headers={"X-MBX-APIKEY":k}) or []
    out={}
    for c in j:
        sym = (c.get("coin") or "").upper()
        nm  = c.get("name") or sym
        for ch in c.get("networkList") or []:
            n = norm_chain(ch.get("network") or ch.get("name"))
            if not n: continue
            out.setdefault(sym,{})[n]={
                "can_dep": bool(ch.get("depositEnable")),
                "can_wd":  bool(ch.get("withdrawEnable")),
                "wd_fee":  float(ch.get("withdrawFee") or 0.0),
                "min_wd":  float(ch.get("withdrawMin") or 0.0),
                "min_dep": float(ch.get("depositMin") or 0.0),
                "contract": (ch.get("contractAddress") or None),
                "name": nm
            }
    NET.set("binance", out); return out

def nets_okx(keys):
    if NET.get("okx"): return NET.get("okx")
    # عمومی کفایت می‌کند؛ ولی بدون کلید، این اکسچنج وارد اسکن نمی‌شود (gating)
    j = http_get("https://www.okx.com/api/v5/asset/currencies") or {}
    out={}
    for c in j.get("data",[]):
        sym = (c.get("ccy") or "").upper()
        ch  = norm_chain(c.get("chain") or "")
        if not ch: continue
        out.setdefault(sym,{})[ch]={
            "can_dep": (str(c.get("canDep")).lower() in ("1","true")),
            "can_wd":  (str(c.get("canWd")).lower() in ("1","true")),
            "wd_fee":  float(c.get("minFee") or c.get("fee") or 0.0),
            "min_wd":  float(c.get("minWd") or 0.0),
            "min_dep": float(c.get("minDep") or 0.0),
            "contract": (c.get("contractAddr") or None),
            "name": c.get("name") or sym
        }
    NET.set("okx", out); return out

def nets_gate(keys):
    if NET.get("gate"): return NET.get("gate")
    j = http_get("https://api.gateio.ws/api/v4/spot/currencies", headers={"Accept":"application/json"}) or []
    out={}
    for c in j:
        sym = (c.get("currency") or "").upper()
        nm  = c.get("name") or sym
        for ch in c.get("chains") or []:
            n = norm_chain(ch.get("chain") or ch.get("name"))
            if not n: continue
            out.setdefault(sym,{})[n]={
                "can_dep": not bool(ch.get("deposit_disabled") or ch.get("deposit_disabled_notice")),
                "can_wd":  not bool(ch.get("withdraw_disabled") or ch.get("withdraw_disabled_notice")),
                "wd_fee":  float(ch.get("withdraw_fix_on_chain_fee") or ch.get("withdraw_fee") or 0),
                "min_wd":  float(ch.get("withdraw_min") or 0),
                "min_dep": float(ch.get("deposit_min") or 0),
                "contract": (ch.get("contract_address") or None),
                "name": nm
            }
    NET.set("gate", out); return out

def nets_mexc(keys):
    if NET.get("mexc"): return NET.get("mexc")
    k, s = keys.get("api_key"), keys.get("secret")
    if not (k and s): return {}
    params={"timestamp":now_ms(),"recvWindow":5000}
    qs = sign_qs_sha256(params, s)
    url = "https://api.mexc.com/api/v3/capital/config/getall?"+qs
    j = http_get(url, headers={"X-MEXC-APIKEY":k}) or []
    out={}
    for c in j:
        sym=(c.get("coin") or "").upper()
        nm=c.get("name") or sym
        for ch in c.get("networkList") or []:
            n = norm_chain(ch.get("network") or "")
            if not n: continue
            out.setdefault(sym,{})[n]={
                "can_dep": bool(ch.get("depositEnable")),
                "can_wd":  bool(ch.get("withdrawEnable")),
                "wd_fee":  float(ch.get("withdrawFee") or 0),
                "min_wd":  float(ch.get("withdrawMin") or 0),
                "min_dep": float(ch.get("depositMin") or 0),
                "contract": (ch.get("contractAddress") or None),
                "name": nm
            }
    NET.set("mexc", out); return out

def nets_bitget(keys):
    if NET.get("bitget"): return NET.get("bitget")
    j = http_get("https://api.bitget.com/api/spot/v1/public/currencies") or {}
    out={}
    for c in j.get("data",[]) or []:
        sym=(c.get("coinName") or c.get("symbol") or "").upper()
        nm = c.get("name") or sym
        for ch in c.get("chains") or []:
            n = norm_chain(ch.get("chain") or "")
            if not n: continue
            out.setdefault(sym,{})[n]={
                "can_dep": str(ch.get("rechargeable")).lower() in ("true","1"),
                "can_wd":  str(ch.get("withdrawable")).lower() in ("true","1"),
                "wd_fee":  float(ch.get("withdrawFee") or 0),
                "min_wd":  float(ch.get("withdrawMin") or 0),
                "min_dep": float(ch.get("rechargeMin") or 0),
                "contract": (ch.get("contractAddress") or None),
                "name": nm
            }
    NET.set("bitget", out); return out

def nets_xt(keys):
    if NET.get("xt"): return NET.get("xt")
    j = http_get("https://sapi.xt.com/v4/public/wallet/support/currency") or {}
    out={}
    for c in j.get("result") or []:
        sym=(c.get("currency") or "").upper()
        nm = c.get("name") or sym
        for ch in c.get("chains") or []:
            n = norm_chain(ch.get("chain") or "")
            if not n: continue
            out.setdefault(sym,{})[n]={
                "can_dep": not bool(ch.get("depositDisabled")),
                "can_wd":  not bool(ch.get("withdrawDisabled")),
                "wd_fee":  float(ch.get("withdrawFee") or 0),
                "min_wd":  float(ch.get("withdrawMin") or 0),
                "min_dep": float(ch.get("depositMin") or 0),
                "contract": (ch.get("contractAddress") or None),
                "name": nm
            }
    NET.set("xt", out); return out

def nets_bitmart(keys):
    if NET.get("bitmart"): return NET.get("bitmart")
    j = http_get("https://api-cloud.bitmart.com/spot/v1/currencies") or {}
    out={}
    for c in j.get("data",{}).get("currencies",[]):
        sym=(c.get("currency") or "").upper()
        nm = c.get("name") or sym
        for ch in c.get("chains") or []:
            n = norm_chain(ch.get("chain") or "")
            if not n: continue
            out.setdefault(sym,{})[n]={
                "can_dep": bool(ch.get("deposit_enabled")),
                "can_wd":  bool(ch.get("withdraw_enabled")),
                "wd_fee":  float(ch.get("withdraw_fee") or 0),
                "min_wd":  float(ch.get("withdraw_min") or 0),
                "min_dep": float(ch.get("deposit_min") or 0),
                "contract": (ch.get("contract_address") or None),
                "name": nm
            }
    NET.set("bitmart", out); return out

def nets_htx(keys):
    if NET.get("htx"): return NET.get("htx")
    j = http_get("https://api.huobi.pro/v2/reference/currencies") or {}
    out={}
    for c in j.get("data",[]) or []:
        sym=(c.get("currency") or "").upper()
        nm = c.get("display-name") or sym
        for ch in c.get("chains") or []:
            n = norm_chain(ch.get("chain") or "")
            if not n: continue
            out.setdefault(sym,{})[n]={
                "can_dep": (ch.get("depositStatus")=="allowed"),
                "can_wd":  (ch.get("withdrawStatus")=="allowed"),
                "wd_fee":  float(ch.get("transactFeeWithdraw") or 0),
                "min_wd":  float(ch.get("minWithdrawAmt") or 0),
                "min_dep": float(ch.get("minDepositAmt") or 0),
                "contract": (ch.get("contractAddr") or None),
                "name": nm
            }
    NET.set("htx", out); return out

def nets_kraken(keys):
    # lazy در حین نیاز پر می‌شود
    return {}

def ensure_kraken_asset(asset, keys, store):
    if asset in store: return
    k, s_b64 = keys.get("api_key"), keys.get("secret")
    if not (k and s_b64): return
    deps = kraken_private("/0/private/DepositMethods", {"asset": asset}, k, s_b64) or []
    wds  = kraken_private("/0/private/WithdrawMethods", {"asset": asset}, k, s_b64) or []
    dep = {norm_chain(d.get("method")): True for d in deps}
    wd  = {norm_chain(w.get("method")): True for w in wds}
    res={}
    for ch in set(list(dep.keys())+list(wd.keys())):
        if not ch: continue
        res[ch]={
            "can_dep": dep.get(ch, False),
            "can_wd":  wd.get(ch, False),
            "wd_fee":  0.0,
            "min_wd":  0.0,
            "min_dep": 0.0,
            "contract": None,
            "name": asset
        }
    store[asset]=res

def nets_bitrue(keys):
    # شبکه‌ها ممکنه پایدار نباشند
    return {}

NET_FETCHERS = {
    "binance": nets_binance, "okx": nets_okx, "gate": nets_gate, "mexc": nets_mexc,
    "bitget": nets_bitget, "xt": nets_xt, "bitmart": nets_bitmart, "htx": nets_htx,
    "kraken": nets_kraken, "bitrue": nets_bitrue
}

# ---------- Tickers ----------
def tickers_binance():
    j = http_get("https://api.binance.com/api/v3/ticker/bookTicker") or []
    out={}
    for r in j:
        s = norm_pairkey(r.get("symbol",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                out[(base,q)] = {"bid": float(r["bidPrice"]), "ask": float(r["askPrice"])}
                break
    return out

def tickers_okx():
    j = http_get("https://www.okx.com/api/v5/market/tickers", params={"instType":"SPOT"}) or {}
    out={}
    for it in j.get("data",[]):
        s = norm_pairkey(it.get("instId",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                out[(base,q)] = {"bid": float(it["bidPx"]), "ask": float(it["askPx"])}
                break
    return out

def tickers_gate():
    j = http_get("https://api.gateio.ws/api/v4/spot/tickers", headers={"Accept":"application/json"}) or []
    out={}
    for it in j:
        s = norm_pairkey(it.get("currency_pair",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                out[(base,q)] = {"bid": float(it.get("highest_bid") or 0), "ask": float(it.get("lowest_ask") or 0)}
                break
    return out

def tickers_mexc():
    j = http_get("https://api.mexc.com/api/v3/ticker/bookTicker") or []
    out={}
    for it in j:
        s = norm_pairkey(it.get("symbol",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                out[(base,q)] = {"bid": float(it["bidPrice"]), "ask": float(it["askPrice"])}
                break
    return out

def tickers_bitget():
    j = http_get("https://api.bitget.com/api/v2/spot/market/tickers") or {}
    out={}
    for it in j.get("data",[]) or []:
        s = norm_pairkey(it.get("symbol",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                out[(base,q)] = {"bid": float(it.get("bidPr") or 0), "ask": float(it.get("askPr") or 0)}
                break
    return out

def tickers_xt():
    j = http_get("https://sapi.xt.com/v4/public/ticker") or {}
    out={}
    for it in j.get("result") or []:
        s = norm_pairkey(it.get("s",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                out[(base,q)] = {"bid": float(it.get("bp") or 0), "ask": float(it.get("ap") or 0)}
                break
    return out

def tickers_bitmart():
    j = http_get("https://api-cloud.bitmart.com/spot/quotation/v3/tickers") or {}
    out={}
    for it in j.get("data",{}).get("tickers",[]):
        s = norm_pairkey(it.get("symbol",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                out[(base,q)] = {"bid": float(it.get("best_bid") or 0), "ask": float(it.get("best_ask") or 0)}
                break
    return out

def tickers_htx():
    j = http_get("https://api.huobi.pro/market/tickers") or {}
    out={}
    for it in j.get("data",[]):
        s = norm_pairkey(it.get("symbol",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                out[(base,q)] = {"bid": float(it.get("bid") or 0), "ask": float(it.get("ask") or 0)}
                break
    return out

def tickers_kraken():
    j = http_get("https://api.kraken.com/0/public/Ticker") or {}
    out={}
    for pair, it in (j.get("result") or {}).items():
        s = norm_pairkey(pair)
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                bid = float(it["b"][0]) if isinstance(it.get("b"), list) else float(it.get("b", [0])[0])
                ask = float(it["a"][0]) if isinstance(it.get("a"), list) else float(it.get("a", [0])[0])
                out[(base,q)] = {"bid": bid, "ask": ask}
                break
    return out

def tickers_bitrue():
    j = http_get("https://openapi.bitrue.com/api/v1/ticker/24hr") or []
    out={}
    for it in j:
        s = norm_pairkey(it.get("symbol",""))
        for q in ("USDT","USDC","BTC","ETH"):
            if s.endswith(q):
                base = s[:-len(q)]
                p = float(it.get("lastPrice") or 0)
                if p>0:
                    out[(base,q)] = {"bid": p, "ask": p}
                break
    return out

TICKERS = {
    "binance": tickers_binance, "okx": tickers_okx, "gate": tickers_gate, "mexc": tickers_mexc,
    "bitget": tickers_bitget, "xt": tickers_xt, "bitmart": tickers_bitmart, "htx": tickers_htx,
    "kraken": tickers_kraken, "bitrue": tickers_bitrue
}

TAKER_FEE = {
    "binance":0.0010,"okx":0.0010,"gate":0.0020,"mexc":0.0020,"bitget":0.0010,
    "xt":0.0020,"bitmart":0.0025,"htx":0.0020,"kraken":0.0026,"bitrue":0.0010
}

# ---------- Secure key storage (AES-CTR + HMAC) ----------
MAGIC=b"AK1"
def derive(pin:str, salt:bytes):
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 200_000, dklen=64)
    return dk[:32], dk[32:]

def enc_json(obj:dict, pin:str)->bytes:
    raw = json.dumps(obj, ensure_ascii=False).encode()
    salt = secrets.token_bytes(16); iv = secrets.token_bytes(16)
    ek, mk = derive(pin, salt)
    ctr = pyaes.Counter(int.from_bytes(iv,"big"))
    aes = pyaes.AESModeOfOperationCTR(ek, counter=ctr)
    ct = aes.encrypt(raw)
    mac = hmac.new(mk, MAGIC+salt+iv+ct, hashlib.sha256).digest()
    return MAGIC+salt+iv+ct+mac

def dec_json(blob:bytes, pin:str)->dict:
    if not blob or blob[:3]!=MAGIC: raise ValueError("bad file")
    salt=blob[3:19]; iv=blob[19:35]; ct=blob[35:-32]; mac=blob[-32:]
    ek, mk = derive(pin, salt)
    mac2 = hmac.new(mk, blob[:-32], hashlib.sha256).digest()
    if not hmac.compare_digest(mac, mac2): raise ValueError("bad pin")
    ctr = pyaes.Counter(int.from_bytes(iv,"big"))
    aes = pyaes.AESModeOfOperationCTR(ek, counter=ctr)
    raw = aes.decrypt(ct)
    return json.loads(raw.decode())

# ---------- Core scan ----------
def get_wallet_info(exchange:str, asset:str, keys:dict, cache:dict):
    fn = NET_FETCHERS.get(exchange)
    if not fn: return {}
    data = fn(keys.get(exchange, {})) or {}
    if exchange=="kraken":
        if asset not in data:
            ensure_kraken_asset(asset, keys.get("kraken", {}), data)
            NET.store["kraken"]=data
    return data.get(asset, {})

def compute_net(ask, bid, notional, ex_buy, ex_sell, wd_fee_base):
    q = notional/ask
    fee_buy = notional * TAKER_FEE.get(ex_buy,0.001)
    fee_sell= (q*bid) * TAKER_FEE.get(ex_sell,0.001)
    wd_usd = wd_fee_base * ask
    gross = q*(bid-ask)
    net = gross - fee_buy - fee_sell - wd_usd
    pct = (net/notional)*100.0
    return net, pct

def scan_real(selected:List[str], quotes:Tuple[str,...], notional:float, min_pct:float, min_abs:float, api_keys:dict):
    # gate by keys
    gated=[]
    for ex in selected:
        need = EXCHS[ex]["needs"]
        have = api_keys.get(ex, {})
        if all(have.get(x) for x in need): gated.append(ex)
    if len(gated)<2: return []

    # tickers
    books={}
    for ex in gated:
        try: books[ex]=TICKERS[ex]() or {}
        except Exception: books[ex]={}

    out=[]
    # pairwise
    for i, a in enumerate(gated):
        for b in gated[i+1:]:
            A, B = books.get(a,{}), books.get(b,{})
            for (base,q), pa in A.items():
                if q not in quotes: continue
                pb = B.get((base,q))
                if not pb: continue
                # check both directions: a->b and b->a
                for (src, dst, pbuy, psell) in ((a,b,pa,pb),(b,a,pb,pa)):
                    ask = pbuy["ask"]; bid = psell["bid"]
                    if ask<=0 or bid<=0: continue
                    wa = get_wallet_info(src, base, api_keys, NET.store)  # withdraw
                    wb = get_wallet_info(dst, base, api_keys, NET.store)  # deposit
                    if not wa or not wb: continue
                    best=None
                    for ch, ia in wa.items():
                        ib = wb.get(ch)
                        if not ib: continue
                        if not (ia.get("can_wd") and ib.get("can_dep")): continue
                        # identity by contract if available
                        if not same_contract(ia.get("contract"), ib.get("contract")): continue
                        # min withdraw check
                        min_wd = float(ia.get("min_wd") or 0.0)
                        units = notional/ask
                        if units < min_wd: continue
                        net, pct = compute_net(ask, bid, notional, src, dst, float(ia.get("wd_fee") or 0.0))
                        row = {
                            "sym": f"{base}/{q}",
                            "src": EXCHS[src]["name"], "dst": EXCHS[dst]["name"],
                            "ask": ask, "bid": bid, "net$": net, "net%": pct,
                            "net": ch,
                            "fees": f"wd:{float(ia.get('wd_fee') or 0.0):g} {base} + takers"
                        }
                        if best is None or row["net$"]>best["net$"]: best=row
                    if best and best["net$"]>=min_abs and best["net%"]>=min_pct:
                        out.append(best)
    out.sort(key=lambda r:(-r["net$"], -r["net%"]))
    return out

# ---------- Exchange registry ----------
EXCHS = {
    "binance":{"name":"Binance","needs":["api_key","secret"]},
    "okx":{"name":"OKX","needs":["api_key","secret","passphrase"]},
    "gate":{"name":"Gate.io","needs":["api_key","secret"]},
    "mexc":{"name":"MEXC","needs":["api_key","secret"]},
    "bitget":{"name":"Bitget","needs":["api_key","secret","passphrase"]},
    "xt":{"name":"XT.com","needs":["api_key","secret"]},
    "bitmart":{"name":"Bitmart","needs":["api_key","secret"]},
    "htx":{"name":"HTX","needs":["api_key","secret"]},
    "kraken":{"name":"Kraken","needs":["api_key","secret"]},
    "bitrue":{"name":"Bitrue","needs":["api_key","secret"]},
}

# ---------- UI components ----------
COLS=[("Symbol",150),("Buy→Sell",220),("Net %",90),("Net $",110),("Network",110),("Fees",180)]
TOTAL_W=sum(dp(w) for _,w in COLS)

def header():
    g=GridLayout(cols=len(COLS), size_hint=(None,None), height=dp(30), width=TOTAL_W, padding=[dp(6),0], spacing=dp(6))
    for t,w in COLS:
        g.add_widget(Label(text=f"[b]{t}[/b]", markup=True, size_hint=(None,1), width=dp(w), font_size=sp(13)))
    return g

class DataGrid(GridLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cols=len(COLS); self.size_hint=(None,None); self.spacing=dp(6); self.padding=[dp(6),0]; self.width=TOTAL_W
        self.bind(minimum_height=self.setter("height"))
    def set_rows(self, rows):
        self.clear_widgets()
        if not rows:
            self.add_widget(Label(text="فرصت مطابق فیلترها یافت نشد.", size_hint=(None,None), width=TOTAL_W, height=dp(28)))
            return
        for r in rows:
            cells=[
                r["sym"],
                f"{r['src']}@{r['ask']:.8f} → {r['dst']}@{r['bid']:.8f}",
                f"{r['net%']:.3f}%",
                f"{r['net$']:.4f}",
                r["net"],
                r["fees"]
            ]
            for (t,w), val in zip(COLS, cells):
                self.add_widget(Label(text=val, size_hint=(None,None), width=dp(w), height=dp(28), font_size=sp(12)))

class FiltersModal(ModalView):
    def __init__(self, init, on_apply, **kw):
        super().__init__(**kw); self.size_hint=(0.92,0.6); self.background_color=(0,0,0,0.85); self.auto_dismiss=False
        root=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        r1=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        r2=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.t_notional=TextInput(text=str(int(init["notional"])), input_filter="int", hint_text="Notional")
        self.t_minpct=TextInput(text=str(init["min_pct"]), input_filter="float", hint_text="Min % (net)")
        self.t_minabs=TextInput(text=str(init["min_abs"]), input_filter="float", hint_text="Min $ (net)")
        self._quote=init["quote"]; b1=Button(text="USDT", on_release=lambda *_: self._setq("USDT"))
        b2=Button(text="USDC", on_release=lambda *_: self._setq("USDC")); self._btns=(b1,b2); self._refresh()
        r1.add_widget(self.t_notional); r1.add_widget(self.t_minpct)
        r2.add_widget(self.t_minabs); r2.add_widget(b1); r2.add_widget(b2)
        btns=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        def apply(*_):
            cfg=dict(notional=float(self.t_notional.text or 1000), min_pct=float(self.t_minpct.text or 0.1),
                     min_abs=float(self.t_minabs.text or 0.05), quote=self._quote)
            on_apply(cfg); self.dismiss()
        btns.add_widget(Button(text="Apply", on_release=apply))
        root.add_widget(r1); root.add_widget(r2); root.add_widget(btns); self.add_widget(root)
    def _setq(self,q): self._quote=q; self._refresh()
    def _refresh(self):
        for b in self._btns: b.background_color=(0.2,0.6,1,1) if b.text==self._quote else (0.25,0.25,0.25,1)

class ExchangesModal(ModalView):
    def __init__(self, selected:set, on_done, **kw):
        super().__init__(**kw); self.size_hint=(0.92,0.7); self.background_color=(0,0,0,0.85); self.auto_dismiss=False
        self.sel=set(selected)
        grid=GridLayout(cols=1, spacing=dp(8), size_hint=(1,None)); grid.bind(minimum_height=grid.setter("height"))
        for ex in EXCHS.keys():
            row=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(40))
            sw=Switch(active=(ex in self.sel))
            def tog(inst,val,name=ex):
                if val: self.sel.add(name)
                else: self.sel.discard(name)
            sw.bind(active=tog)
            row.add_widget(Label(text=EXCHS[ex]["name"], size_hint=(1,1)))
            row.add_widget(sw)
            grid.add_widget(row)
        sc=ScrollView(); sc.add_widget(grid)
        btns=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        btns.add_widget(Button(text="Apply", on_release=lambda *_:(on_done(self.sel), self.dismiss())))
        root=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        root.add_widget(sc); root.add_widget(btns); self.add_widget(root)

# --- API keys UI (encrypted with PIN) ---
MAG=b"AK1"
class PinModal(ModalView):
    def __init__(self, title, on_ok, **kw):
        super().__init__(**kw); self.size_hint=(0.8,0.4); self.background_color=(0,0,0,0.85); self.auto_dismiss=False
        self.on_ok=on_ok
        box=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        box.add_widget(Label(text=title, size_hint=(1,None), height=dp(24)))
        self.t=TextInput(password=True, hint_text="PIN (4-10 chars)", multiline=False, size_hint=(1,None), height=dp(44))
        btns=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Cancel", on_release=lambda *_: self.dismiss()))
        btns.add_widget(Button(text="OK", on_release=lambda *_:(self.on_ok(self.t.text), self.dismiss())))
        box.add_widget(self.t); box.add_widget(btns); self.add_widget(box)

class ApiKeysModal(ModalView):
    def __init__(self, init_data:dict, on_apply, **kw):
        super().__init__(**kw)
        self.size_hint=(0.94,0.9); self.background_color=(0,0,0,0.88); self.auto_dismiss=False
        self.on_apply=on_apply
        self.file_path=os.path.join(App.get_running_app().user_data_dir, "secrets.enc")
        self.inputs={}
        root=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        grid=GridLayout(cols=1, spacing=dp(8), size_hint=(1,1)); grid.bind(minimum_height=grid.setter("height"))
        def add_ex(ex, need_pass):
            box=BoxLayout(orientation="vertical", spacing=dp(6), size_hint=(1,None), height=dp(140 if need_pass else 100))
            box.add_widget(Label(text=EXCHS[ex]["name"], size_hint=(1,None), height=dp(20)))
            k=TextInput(hint_text="API Key", text=(init_data.get(ex,{}).get("api_key") or ""), multiline=False, size_hint=(1,None), height=dp(40))
            s=TextInput(hint_text="API Secret", text=(init_data.get(ex,{}).get("secret") or ""), password=True, multiline=False, size_hint=(1,None), height=dp(40))
            box.add_widget(k); box.add_widget(s)
            p=None
            if need_pass:
                p=TextInput(hint_text="Passphrase", text=(init_data.get(ex,{}).get("passphrase") or ""), password=True, multiline=False, size_hint=(1,None), height=dp(40))
                box.add_widget(p)
            self.inputs[ex]=(k,s,p); grid.add_widget(box)
        for ex in EXCHS:
            add_ex(ex, "passphrase" in EXCHS[ex]["needs"])
        sc=ScrollView(size_hint=(1,1)); sc.add_widget(grid); root.add_widget(sc)
        btns=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(48))
        btns.add_widget(Button(text="Close", on_release=lambda *_: self.dismiss()))
        btns.add_widget(Button(text="Load",  on_release=self._load))
        btns.add_widget(Button(text="Clear", on_release=self._clear))
        btns.add_widget(Button(text="Save (Encrypted)", on_release=self._save))
        root.add_widget(btns); self.add_widget(root)
    def _collect(self):
        data={}
        for ex,(k,s,p) in self.inputs.items():
            d={"api_key":(k.text or "").strip(),"secret":(s.text or "").strip()}
            if p: d["passphrase"]=(p.text or "").strip()
            data[ex]=d
        return data
    def _save(self,*_):
        def ok(pin):
            try:
                data=self._collect()
                blob=enc_json(data, pin)
                with open(self.file_path,"wb") as f: f.write(blob)
                self.on_apply(data)
            except Exception: pass
        PinModal("Enter a PIN to encrypt", on_ok=ok).open()
    def _load(self,*_):
        if not os.path.exists(self.file_path): return
        def ok(pin):
            try:
                with open(self.file_path,"rb") as f: blob=f.read()
                data=dec_json(blob, pin)
                for ex,vals in data.items():
                    if ex in self.inputs:
                        k,s,p=self.inputs[ex]
                        k.text=vals.get("api_key",""); s.text=vals.get("secret",""); 
                        if p: p.text=vals.get("passphrase","")
                self.on_apply(data)
            except Exception: pass
        PinModal("Enter PIN to load", on_ok=ok).open()
    def _clear(self,*_):
        try:
            if os.path.exists(self.file_path): os.remove(self.file_path)
            for ex,(k,s,p) in self.inputs.items():
                k.text=""; s.text=""; 
                if p: p.text=""
            self.on_apply({})
        except Exception: pass

class SettingsModal(ModalView):
    def __init__(self, init, on_apply, on_exchs, on_keys, **kw):
        super().__init__(**kw)
        self.size_hint=(0.92,0.72); self.background_color=(0,0,0,0.88); self.auto_dismiss=False
        root=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        r1=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        self.sw_auto=Switch(active=init["auto"])
        self.t_int=TextInput(text=str(init["interval"]), input_filter="int", hint_text="sec")
        r1.add_widget(Label(text="Auto refresh")); r1.add_widget(self.sw_auto)
        r1.add_widget(Label(text="Interval"));     r1.add_widget(self.t_int)
        btn_api=Button(text="API Keys", size_hint=(1,None), height=dp(44), on_release=lambda *_:(self.dismiss(), on_keys()))
        btn_ex =Button(text=f"Select Exchanges ({init['ex_count']})", size_hint=(1,None), height=dp(44), on_release=lambda *_:(self.dismiss(), on_exchs()))
        btns=BoxLayout(spacing=dp(8), size_hint=(1,None), height=dp(44))
        btns.add_widget(Button(text="Close", on_release=lambda *_: self.dismiss()))
        def apply(*_):
            cfg=dict(auto=self.sw_auto.active, interval=int(self.t_int.text or 15))
            on_apply(cfg); self.dismiss()
        btns.add_widget(Button(text="Apply", on_release=apply))
        root.add_widget(r1); root.add_widget(btn_api); root.add_widget(btn_ex); root.add_widget(btns); self.add_widget(root)

class Root(BoxLayout):
    running=BooleanProperty(False)
    notional=NumericProperty(100.0)
    min_pct=NumericProperty(0.2)  # درصد
    min_abs=NumericProperty(0.5)
    quote=StringProperty("USDT")
    auto=BooleanProperty(True)
    interval=NumericProperty(15)
    def __init__(self, **kw):
        super().__init__(**kw); self.orientation="vertical"
        self.selected=set(EXCHS.keys())
        self.api_store={}
        # Top bar
        top=BoxLayout(size_hint=(1,None), height=dp(50), padding=[dp(8),0], spacing=dp(8))
        btn_f=Button(text="Filters", size_hint=(None,1), width=dp(88), on_release=lambda *_: self.open_filters())
        sp_l=Widget(size_hint=(1,1))
        btn_s=Button(text="Scan", size_hint=(None,1), width=dp(72), on_release=lambda *_: self.scan())
        sp_r=Widget(size_hint=(1,1))
        btn_set=Button(text="Settings", size_hint=(None,1), width=dp(96), on_release=lambda *_: self.open_settings())
        top.add_widget(btn_f); top.add_widget(sp_l); top.add_widget(btn_s); top.add_widget(sp_r); top.add_widget(btn_set)
        self.add_widget(top)
        # header + data
        self.h_scroll=ScrollView(do_scroll_x=True, do_scroll_y=False, bar_width=0, size_hint=(1,None), height=dp(30))
        self.h_grid=header(); self.h_scroll.add_widget(self.h_grid); self.add_widget(self.h_scroll)
        self.d_grid=DataGrid()
        self.d_scroll=ScrollView(do_scroll_x=True, do_scroll_y=True, size_hint=(1,1)); self.d_scroll.add_widget(self.d_grid); self.add_widget(self.d_scroll)
        # sync x
        self._sync=False
        self.h_scroll.bind(scroll_x=self._from_head); self.d_scroll.bind(scroll_x=self._from_body)
        # auto
        self._ev=Clock.schedule_interval(lambda *_: self.scan(), self.interval) if self.auto else None
        Clock.schedule_once(lambda *_: self.scan(), 0.5)
    def _from_head(self,_,v):
        if self._sync: return
        self._sync=True; self.d_scroll.scroll_x=v; self._sync=False
    def _from_body(self,_,v):
        if self._sync: return
        self._sync=True; self.h_scroll.scroll_x=v; self._sync=False
    def open_filters(self):
        init=dict(notional=self.notional, min_pct=self.min_pct, min_abs=self.min_abs, quote=self.quote)
        def apply(cfg):
            self.notional=cfg["notional"]; self.min_pct=cfg["min_pct"]; self.min_abs=cfg["min_abs"]; self.quote=cfg["quote"]
            self.scan()
        FiltersModal(init, on_apply=apply).open()
    def open_settings(self):
        init=dict(auto=self.auto, interval=int(self.interval), ex_count=len(self.selected))
        def apply(cfg):
            if cfg["auto"]:
                self.interval=max(5,int(cfg["interval"] or 15))
                if self._ev: self._ev.cancel()
                self._ev=Clock.schedule_interval(lambda *_: self.scan(), self.interval)
            else:
                if self._ev: self._ev.cancel(); self._ev=None
            self.auto=cfg["auto"]
        def edit_ex():
            def done(sel):
                self.selected=set(sel) if sel else set(EXCHS.keys())
                self.scan()
            ExchangesModal(self.selected, on_done=done).open()
        def api_keys():
            def updated(d):
                self.api_store=d or {}
                NET.store.clear()  # کلید عوض شد → کش شبکه‌ها پاک
            ApiKeysModal(self.api_store, on_apply=updated).open()
        SettingsModal(init, on_apply=apply, on_exchs=edit_ex, on_keys=api_keys).open()
    def scan(self):
        if self.running: return
        self.running=True
        threading.Thread(target=self._worker, daemon=True).start()
    def _worker(self):
        try:
            qts=(self.quote,)  # فعلاً یک کوُت
            rows=scan_real(sorted(self.selected), quotes=qts, notional=float(self.notional),
                           min_pct=float(self.min_pct), min_abs=float(self.min_abs), api_keys=self.api_store)
            self._on_results(rows)
        except Exception:
            self._on_results([])
    @mainthread
    def _on_results(self, rows):
        self.d_grid.set_rows(rows); self.running=False

class ArbApp(App):
    def build(self):
        from kivy.core.window import Window
        Window.clearcolor=(0.06,0.06,0.06,1)
        return Root()

if __name__ == "__main__":
    ArbApp().run()
