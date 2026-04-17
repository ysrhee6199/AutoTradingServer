import os
import time
import json
import hmac
import hashlib
import base64
import math
import requests
from urllib.parse import urlencode
from typing import Optional, Dict

BASE_URL = "https://api.bitget.com"

API_KEY = os.getenv("BITGET_API_KEY", "")
API_SECRET = os.getenv("BITGET_API_SECRET", "")
API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE", "")

PRODUCT_TYPE = "USDT-FUTURES"
SYMBOL = "BTCUSDT"
MARGIN_COIN = "USDT"

def make_sign(ts_ms: str,
              method: str,
              path: str,
              query: Optional[Dict] = None,
              body: str = "") -> str:

    method = method.upper()

    if query:
        query_str = urlencode(sorted(query.items()))
        prehash = ts_ms + method + path + "?" + query_str + body
    else:
        prehash = ts_ms + method + path + body

    mac = hmac.new(
        API_SECRET.encode("utf-8"),
        prehash.encode("utf-8"),
        hashlib.sha256
    )

    return base64.b64encode(mac.digest()).decode("utf-8")


def get_usdtm_futures_balance():
    path = "/api/v2/mix/account/accounts"
    query = {"productType": "USDT-FUTURES"}
    ts_ms = str(int(time.time() * 1000))

    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": make_sign(ts_ms, "GET", path, query=query),
        "ACCESS-PASSPHRASE": API_PASSPHRASE,
        "ACCESS-TIMESTAMP": ts_ms,
        "locale": "en-US",
        "Content-Type": "application/json"
    }

    response = requests.get(
        BASE_URL + path,
        headers=headers,
        params=query,
        timeout=10
    )

    response.raise_for_status()
    result = response.json()

    if result.get("code") == "00000":
        for acct in result.get("data", []):
            if acct.get("marginCoin") == "USDT":
                return float(acct.get("available", 0.0))

    return 0.0


def get_usdtm_futures_total_equity():
    path = "/api/v2/mix/account/accounts"
    query = {"productType": "USDT-FUTURES"}
    ts_ms = str(int(time.time() * 1000))

    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": make_sign(ts_ms, "GET", path, query=query),
        "ACCESS-PASSPHRASE": API_PASSPHRASE,
        "ACCESS-TIMESTAMP": ts_ms,
        "locale": "en-US",
        "Content-Type": "application/json"
    }

    response = requests.get(
        BASE_URL + path,
        headers=headers,
        params=query,
        timeout=10
    )

    response.raise_for_status()
    result = response.json()

    if result.get("code") == "00000":
        for acct in result.get("data", []):
            if acct.get("marginCoin") == "USDT":
                # API 버전/설정에 따라 총 잔액 필드명이 다를 수 있어 우선순위로 조회
                for key in ("usdtEquity", "accountEquity", "equity", "available"):
                    v = acct.get(key)
                    if v is not None:
                        return float(v)

    return 0.0





def _json_dumps_compact(obj) -> str:
    # 서명에 들어가는 body는 "공백 없는" JSON 문자열로 고정하는 게 안전
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _sign(ts_ms: str, method: str, path: str, query: dict = None, body: str = "") -> str:
    method = method.upper()

    if query:
        # query string key 정렬
        query_str = urlencode(sorted(query.items()))
        prehash = ts_ms + method + path + "?" + query_str + body
    else:
        prehash = ts_ms + method + path + body

    mac = hmac.new(API_SECRET.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode("utf-8")


def _request(method: str, path: str, query: dict = None, body_dict: dict = None, auth: bool = False):
    method = method.upper()
    ts_ms = str(int(time.time() * 1000))

    body = ""
    if body_dict is not None:
        body = _json_dumps_compact(body_dict)

    headers = {"Content-Type": "application/json", "locale": "en-US"}

    # ✅ query는 서명/전송 모두 같은 순서로
    query_items = None
    if query:
        query_items = sorted(query.items())  # list of tuples

    if auth:
        headers.update({
            "ACCESS-KEY": API_KEY,
            "ACCESS-PASSPHRASE": API_PASSPHRASE,
            "ACCESS-TIMESTAMP": ts_ms,
            "ACCESS-SIGN": _sign(ts_ms, method, path, query=query, body=body),  # _sign 내부는 sorted 사용중
        })

    url = BASE_URL + path

    if method == "GET":
        r = requests.get(url, headers=headers, params=query_items, timeout=10)
    elif method == "POST":
        r = requests.post(url, headers=headers, params=query_items, data=body, timeout=10)
    else:
        raise ValueError("Unsupported method")

    if r.status_code >= 400:
        print("HTTP", r.status_code, r.text)
        r.raise_for_status()

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text, "status": r.status_code}

    if r.status_code >= 400:
        print("HTTP", r.status_code, data)
        return data  # ✅ 예외로 죽지 말고 data 반환

    if isinstance(data, dict) and data.get("code") and data.get("code") != "00000":
        print("Bitget error:", data)
    return data


def get_contract_config(symbol: str = SYMBOL):
    # GET /api/v2/mix/market/contracts  (public)
    data = _request(
        "GET",
        "/api/v2/mix/market/contracts",
        query={"productType": "usdt-futures", "symbol": symbol},
        auth=False,
    )
    # data["data"]는 list
    return data["data"][0]


def get_market_price(symbol: str = SYMBOL) -> float:
    # GET /api/v2/mix/market/symbol-price (public)
    data = _request(
        "GET",
        "/api/v2/mix/market/symbol-price",
        query={"productType": "usdt-futures", "symbol": symbol},
        auth=False,
    )
    return float(data["data"][0]["price"])


def _format_leverage(leverage) -> str:
    leverage_f = float(leverage)
    if not leverage_f.is_integer():
        raise ValueError(f"leverage must be an integer ratio: {leverage}")
    return str(int(leverage_f))


def set_isolated_leverage_50x(symbol: str = SYMBOL, leverage: int = 50, hold_side: str = None):
    # POST /api/v2/mix/account/set-leverage (private)
    # one-way + isolated에서 동일 레버리지면 holdSide 없이 leverage만 사용 가능(문서 설명 참고)
    body = {
        "symbol": symbol,
        "productType": PRODUCT_TYPE,
        "marginCoin": MARGIN_COIN,
        "leverage": _format_leverage(leverage),
    }
    if hold_side:
        body["holdSide"] = hold_side
    return _request("POST", "/api/v2/mix/account/set-leverage", body_dict=body, auth=True)


def _round_down_to_step(x: float, step: float) -> float:
    return math.floor(x / step) * step


def calc_size_from_margin_usdt(margin_usdt: float, leverage: int, symbol: str = SYMBOL) -> str:
    cfg = get_contract_config(symbol)
    price = get_market_price(symbol)

    step = float(cfg["sizeMultiplier"])      # 예: 0.01
    min_qty = float(cfg["minTradeNum"])      # 예: 0.01
    vol_place = int(cfg["volumePlace"])      # 예: 2

    notional = margin_usdt * leverage        # 예: 100 * 50 = 5000 USDT
    raw_size = notional / price              # BTC 단위

    size = _round_down_to_step(raw_size, step)
    if size < min_qty:
        raise ValueError(
            f"Calculated size too small: {size}. Need >= minTradeNum({min_qty}). "
            f"(price={price}, notional={notional})"
        )

    # volumePlace 자릿수로 문자열 포맷 (불필요한 부동소수 오차 방지)
    fmt = "{:0." + str(vol_place) + "f}"
    return fmt.format(size)


def place_market_order_open(side: str, margin_usdt: float = 100.0, leverage: int = 50, symbol: str = SYMBOL):
    """
    side: "buy"=롱 오픈, "sell"=숏 오픈 (one-way-mode 기준)
    """
    # (권장) 레버리지 먼저 세팅
    hold_side = "long" if side == "buy" else "short"
    set_isolated_leverage_50x(symbol, leverage, hold_side)

    size_str = calc_size_from_margin_usdt(margin_usdt, leverage, symbol)
    client_oid = str(int(time.time() * 1000)) 

    body = {
        "symbol": symbol,
        "productType": PRODUCT_TYPE,
        "marginMode": "isolated",
        "marginCoin": MARGIN_COIN,
        "size": size_str,         # 베이스코인(BTC) 수량
        "side": side,             # buy=롱, sell=숏 (one-way 기준)
        "tradeSide": "open",             # ✅ hedge-mode 필수, one-way면 무시됨
        "orderType": "market",
        "clientOid": client_oid,         
        # hedge-mode 아니면 tradeSide는 보통 불필요. (필요해지면 "open" 넣어야 함)
    }
    return _request("POST", "/api/v2/mix/order/place-order", body_dict=body, auth=True)


def open_long_btcusdt_isolated_50x_100usdt():
    return place_market_order_open("buy", margin_usdt=50.0, leverage=2)


def open_short_btcusdt_isolated_50x_100usdt():
    return place_market_order_open("sell", margin_usdt=50.0, leverage=2)

def _round_down_to_step(x: float, step: float) -> float:
    return math.floor(x / step) * step

def get_position_for(symbol: str, hold_side: str):
    pos = _request(
        "GET",
        "/api/v2/mix/position/all-position",
        query={"productType": PRODUCT_TYPE, "marginCoin": MARGIN_COIN},
        auth=True
    )
    items = (pos.get("data") or []) if isinstance(pos, dict) else []
    for p in items:
        if p.get("symbol") == symbol and str(p.get("holdSide","")).lower() == hold_side.lower():
            return p
    return None

def close_position_percent(symbol: str, hold_side: str, percent: float):
    if percent <= 0 or percent > 100:
        raise ValueError("percent must be 0~100")

    p = get_position_for(symbol, hold_side)  # 네가 이미 쓰는: all-position에서 symbol+holdSide 찾는 함수
    if not p:
        return {"ok": False, "msg": f"No {hold_side} position on {symbol}"}

    margin_mode = str(p.get("marginMode", "")).lower()   # isolated / crossed
    if not margin_mode:
        return {"ok": False, "msg": "marginMode missing", "pos": p}

    total_size = float(p.get("available") or p.get("total") or "0")
    if total_size <= 0:
        return {"ok": False, "msg": "No closable size", "pos": p}

    close_size = total_size * (percent / 100.0)

    cfg = get_contract_config(symbol)
    step = float(cfg["sizeMultiplier"])
    vol_place = int(cfg["volumePlace"])
    min_qty = float(cfg["minTradeNum"])

    close_size = _round_down_to_step(close_size, step)
    if close_size < min_qty:
        return {"ok": False, "msg": "Close size < minTradeNum", "close_size": close_size, "min": min_qty}

    fmt = "{:0." + str(vol_place) + "f}"
    size_str = fmt.format(close_size)

    # ✅ hedge-mode 공식 매핑 (문서 기준)
    # close long: side=buy, tradeSide=close
    # close short: side=sell, tradeSide=close
    side = "buy" if hold_side.lower() == "long" else "sell"

    body = {
        "symbol": symbol,
        "productType": PRODUCT_TYPE,   # "USDT-FUTURES"
        "marginMode": margin_mode,     # "isolated" or "crossed"
        "marginCoin": MARGIN_COIN,     # "USDT"
        "size": size_str,
        "side": side,
        "tradeSide": "close",          # ✅ hedge-mode에서 close 필수
        "orderType": "market",
        "clientOid": "partial_close_" + str(int(time.time() * 1000)),
    }
    return _request("POST", "/api/v2/mix/order/place-order", body_dict=body, auth=True)

def get_current_position_side(symbol: str):
    """
    현재 포지션 방향 반환

    return:
        "long"  → 롱 포지션 존재
        "short" → 숏 포지션 존재
        "both"  → 롱/숏 동시에 존재 (hedge 모드)
        "none"  → 포지션 없음
    """

    pos = _request(
        "GET",
        "/api/v2/mix/position/all-position",
        query={
            "productType": PRODUCT_TYPE,
            "marginCoin": MARGIN_COIN
        },
        auth=True
    )

    items = pos.get("data") or []

    has_long = False
    has_short = False

    for p in items:
        if p.get("symbol") != symbol:
            continue

        size = float(p.get("total") or 0)
        if size <= 0:
            continue

        hold_side = str(p.get("holdSide", "")).lower()

        if hold_side == "long":
            has_long = True
        elif hold_side == "short":
            has_short = True

    if has_long and has_short:
        return "both"
    elif has_long:
        return "long"
    elif has_short:
        return "short"
    else:
        return "none"

#if __name__ == "__main__":
   # get_usdtm_futures_balance()
    #open_short_btcusdt_isolated_50x_100usdt()
    # 롱 전량 청산
  #  close_long_btcusdt_market()
    # 숏 전량 청산
   #close_short_btcusdt_market())
    #side = get_current_position_side("BTCUSDT")
    #print("현재 포지션:", side)
    #print(close_position_percent("BTCUSDT", "long", 100))   # 롱 50% 청산
    #side = get_current_position_side("BTCUSDT")
    #print("현재 포지션:", side)
  # get_usdtm_futures_balance()
   # get_usdtm_futures_balance()
