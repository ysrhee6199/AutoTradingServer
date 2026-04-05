import os
import time
import hmac
import hashlib
import requests
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")

BASE_URL = "https://api.binance.com"   # live only for /sapi margin
SYMBOL = "BTCUSDT"
IS_ISOLATED = "FALSE"                  # Cross Margin
BUY_USDT = Decimal("250")
STOP1 = Decimal("67000")
STOP1_LIMIT = Decimal("66950")
STOP2 = Decimal("68000")
STOP2_LIMIT = Decimal("67950")

session = requests.Session()
session.headers.update({"X-MBX-APIKEY": API_KEY})


def sign_params(params: dict) -> str:
    query = urlencode(params, doseq=True)
    sig = hmac.new(
        API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{query}&signature={sig}"


def signed_request(method: str, path: str, params: dict):
    params = dict(params)
    params["timestamp"] = int(time.time() * 1000)
    params.setdefault("recvWindow", 10000)

    body = sign_params(params)
    url = f"{BASE_URL}{path}"

    if method.upper() == "GET":
        r = session.get(f"{url}?{body}", timeout=20)
    elif method.upper() == "POST":
        r = session.post(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
    elif method.upper() == "DELETE":
        r = session.delete(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
    else:
        raise ValueError(f"Unsupported method: {method}")

    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} | {r.text}")
    return r.json()


def public_get(path: str, params: dict | None = None):
    url = f"{BASE_URL}{path}"
    r = session.get(url, params=params or {}, timeout=20)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} | {r.text}")
    return r.json()


def get_exchange_info(symbol: str):
    return public_get("/api/v3/exchangeInfo", {"symbol": symbol})


def get_symbol_filters(symbol: str):
    info = get_exchange_info(symbol)
    symbols = info.get("symbols", [])
    if not symbols:
        raise RuntimeError(f"Symbol not found: {symbol}")

    filters = {}
    for f in symbols[0]["filters"]:
        filters[f["filterType"]] = f
    return filters


def quantize_step(value: Decimal, step: str) -> str:
    step_dec = Decimal(step)
    if step_dec == 0:
        return str(value)
    quantized = (value // step_dec) * step_dec
    return format(quantized, "f")


def place_market_buy_quote(symbol: str, quote_order_qty: Decimal):
    return signed_request(
        "POST",
        "/sapi/v1/margin/order",
        {
            "symbol": symbol,
            "isIsolated": IS_ISOLATED,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": str(quote_order_qty),
            "sideEffectType": "AUTO_BORROW_REPAY",
            "autoRepayAtCancel": "true",
            "newOrderRespType": "FULL",
        },
    )


def place_stop_loss_limit_sell(symbol: str, qty_str: str, stop_price: Decimal, limit_price: Decimal):
    return signed_request(
        "POST",
        "/sapi/v1/margin/order",
        {
            "symbol": symbol,
            "isIsolated": IS_ISOLATED,
            "side": "SELL",
            "type": "STOP_LOSS_LIMIT",
            "quantity": qty_str,
            "price": str(limit_price),
            "stopPrice": str(stop_price),
            "timeInForce": "GTC",
            "sideEffectType": "AUTO_REPAY",
            "newOrderRespType": "ACK",
        },
    )


def cancel_margin_order(symbol: str, order_id: int):
    return signed_request(
        "DELETE",
        "/sapi/v1/margin/order",
        {
            "symbol": symbol,
            "isIsolated": IS_ISOLATED,
            "orderId": order_id,
        },
    )


def market_sell_all(symbol: str, qty_str: str):
    return signed_request(
        "POST",
        "/sapi/v1/margin/order",
        {
            "symbol": symbol,
            "isIsolated": IS_ISOLATED,
            "side": "SELL",
            "type": "MARKET",
            "quantity": qty_str,
            "sideEffectType": "AUTO_REPAY",
            "newOrderRespType": "FULL",
        },
    )


def safe_cancel(symbol: str, order_id: int | None):
    if order_id is None:
        return None
    try:
        result = cancel_margin_order(symbol, order_id)
        print(f"[CANCEL] success: {result}")
        return result
    except Exception as e:
        # 이미 체결/취소된 경우 여기로 올 수 있음
        print(f"[CANCEL] skipped/failed: {e}")
        return None


def main():
    if not API_KEY or not API_SECRET:
        raise RuntimeError("BINANCE_API_KEY / BINANCE_API_SECRET 환경변수를 설정하세요.")

    print("[INFO] Loading symbol filters...")
    filters = get_symbol_filters(SYMBOL)
    lot_size = filters.get("LOT_SIZE")
    if not lot_size:
        raise RuntimeError("LOT_SIZE filter not found.")
    step_size = lot_size["stepSize"]
    min_qty = Decimal(lot_size["minQty"])

    print("[STEP 1] 250 USDT BTC market buy with AUTO_BORROW_REPAY")
    buy = place_market_buy_quote(SYMBOL, BUY_USDT)
    print("[BUY]", buy)

    executed_qty_raw = buy.get("executedQty")
    status = buy.get("status")

    if not executed_qty_raw:
        raise RuntimeError("executedQty가 없습니다. 매수 응답을 확인하세요.")
    if status not in ("FILLED", "PARTIALLY_FILLED"):
        raise RuntimeError(f"매수 상태가 예상과 다릅니다: {status}")

    executed_qty = Decimal(executed_qty_raw)
    qty_str = quantize_step(executed_qty, step_size)

    if Decimal(qty_str) < min_qty:
        raise RuntimeError(f"체결 수량이 최소 주문 수량보다 작습니다: {qty_str} < {min_qty}")

    print(f"[INFO] executedQty={executed_qty_raw}, roundedQty={qty_str}")

    print("[STEP 2] Place initial stop-loss at 67000")
    stop1 = place_stop_loss_limit_sell(SYMBOL, qty_str, STOP1, STOP1_LIMIT)
    print("[STOP1]", stop1)
    stop1_id = stop1.get("orderId")

    print("[WAIT] sleeping 60 seconds...")
    time.sleep(60)

    print("[STEP 3] Cancel old stop and move stop-loss to 68000")
    safe_cancel(SYMBOL, stop1_id)

    stop2_id = None
    try:
        stop2 = place_stop_loss_limit_sell(SYMBOL, qty_str, STOP2, STOP2_LIMIT)
        print("[STOP2]", stop2)
        stop2_id = stop2.get("orderId")
    except Exception as e:
        print(f"[STOP2] failed: {e}")

    print("[WAIT] sleeping 60 seconds...")
    time.sleep(60)

    print("[STEP 4] Cancel current stop and market-sell all")
    safe_cancel(SYMBOL, stop2_id)

    try:
        sell = market_sell_all(SYMBOL, qty_str)
        print("[SELL ALL]", sell)
    except Exception as e:
        print(f"[SELL ALL] failed: {e}")
        print("[NOTE] 이미 손절이 체결되어 포지션이 없을 수 있습니다.")


if __name__ == "__main__":
    main()