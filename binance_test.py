import os
import time
import hmac
import hashlib
import requests
from decimal import Decimal
from urllib.parse import urlencode

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")

BASE_URL = "https://api.binance.com"   # live
SYMBOL = "BTCUSDT"
IS_ISOLATED = "FALSE"                  # Cross Margin

ENTRY_BALANCE_RATIO = Decimal("0.40")
ENTRY_LEVERAGE_MULTIPLE = Decimal("1.60")
TAKE_PROFIT = Decimal("73000")
STOP1 = Decimal("69000")
STOP2 = Decimal("70000")
WAIT_SECONDS = 60

session = requests.Session()
session.headers.update({"X-MBX-APIKEY": API_KEY})


# ---------------------------
# HTTP helpers
# ---------------------------
def sign_params(params: dict) -> str:
    query = urlencode(params, doseq=True)
    sig = hmac.new(
        API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{query}&signature={sig}"


def public_get(path: str, params: dict | None = None):
    url = f"{BASE_URL}{path}"
    r = session.get(url, params=params or {}, timeout=20)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} | {r.text}")
    return r.json()


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


# ---------------------------
# Symbol filters
# ---------------------------
def get_exchange_info(symbol: str):
    # Public endpoint. Do NOT sign this.
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


def get_symbol_price(symbol: str) -> Decimal:
    ticker = public_get("/api/v3/ticker/price", {"symbol": symbol})
    return Decimal(ticker["price"])


def get_min_notional(filters: dict) -> Decimal:
    notional_filter = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL")
    if not notional_filter:
        return Decimal("0")
    return Decimal(notional_filter.get("minNotional", "0"))


def floor_to_step(value: Decimal, step: str) -> Decimal:
    step_dec = Decimal(step)
    if step_dec == 0:
        return value
    return (value // step_dec) * step_dec


def decimal_to_str(v: Decimal) -> str:
    return format(v, "f")


# ---------------------------
# Margin API actions
# ---------------------------
def place_cross_margin_market_buy(symbol: str, quote_order_qty: Decimal):
    # AUTO_BORROW_REPAY will auto-borrow if needed.
    return signed_request(
        "POST",
        "/sapi/v1/margin/order",
        {
            "symbol": symbol,
            "isIsolated": IS_ISOLATED,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": decimal_to_str(quote_order_qty),
            "sideEffectType": "AUTO_BORROW_REPAY",
            "autoRepayAtCancel": "true",
            "newOrderRespType": "FULL",
        },
    )


def place_cross_margin_oco_sell(symbol: str, qty_str: str, take_profit: Decimal, stop_loss: Decimal):
    return signed_request(
        "POST",
        "/sapi/v1/margin/order/oco",
        {
            "symbol": symbol,
            "isIsolated": IS_ISOLATED,
            "side": "SELL",
            "quantity": qty_str,
            "price": decimal_to_str(take_profit),
            "stopPrice": decimal_to_str(stop_loss),
            "sideEffectType": "AUTO_REPAY",
            "newOrderRespType": "FULL",
        },
    )


def cancel_margin_oco(symbol: str, order_list_id: int):
    return signed_request(
        "DELETE",
        "/sapi/v1/margin/orderList",
        {
            "symbol": symbol,
            "isIsolated": IS_ISOLATED,
            "orderListId": order_list_id,
        },
    )


def place_cross_margin_market_sell(symbol: str, qty_str: str):
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


def manual_liquidate_cross_margin():
    return signed_request(
        "POST",
        "/sapi/v1/margin/manual-liquidation",
        {"type": "MARGIN"},
    )


def get_cross_margin_account():
    return signed_request("GET", "/sapi/v1/margin/account", {})


def print_cross_margin_balance():
    account = get_cross_margin_account()
    usdt_asset = get_asset_from_account(account, "USDT")

    total_asset_btc = Decimal(account.get("totalAssetOfBtc", "0"))
    total_liability_btc = Decimal(account.get("totalLiabilityOfBtc", "0"))
    total_net_asset_btc = Decimal(account.get("totalNetAssetOfBtc", "0"))
    total_collateral_usdt = Decimal(account.get("TotalCollateralValueInUSDT", "0"))
    usdt_free = Decimal(usdt_asset.get("free", "0"))
    usdt_locked = Decimal(usdt_asset.get("locked", "0"))
    usdt_borrowed = Decimal(usdt_asset.get("borrowed", "0"))
    usdt_interest = Decimal(usdt_asset.get("interest", "0"))
    usdt_net_asset = Decimal(usdt_asset.get("netAsset", "0"))
    balance_for_entry = total_collateral_usdt

    if balance_for_entry <= 0:
        balance_for_entry = usdt_net_asset

    print("[MARGIN BALANCE] Cross Margin account")
    print(f"[MARGIN BALANCE] TotalCollateralValueInUSDT={total_collateral_usdt:.4f} USDT")
    print(
        "[MARGIN BALANCE] "
        f"USDT free={usdt_free} locked={usdt_locked} "
        f"borrowed={usdt_borrowed} interest={usdt_interest} netAsset={usdt_net_asset}"
    )
    print(f"[MARGIN BALANCE] balanceForEntry={balance_for_entry:.4f} USDT")
    print(f"[MARGIN BALANCE] totalNetAssetOfBtc={total_net_asset_btc} BTC")
    print(f"[MARGIN BALANCE] totalAssetOfBtc={total_asset_btc} BTC")
    print(f"[MARGIN BALANCE] totalLiabilityOfBtc={total_liability_btc} BTC")
    return balance_for_entry


def get_asset_from_account(account: dict, asset_name: str):
    for asset in account.get("userAssets", []):
        if asset.get("asset") == asset_name:
            return asset
    return {}


def get_cross_margin_asset(asset_name: str):
    account = get_cross_margin_account()
    return get_asset_from_account(account, asset_name)


def get_free_margin_asset_amount(asset_name: str) -> Decimal:
    asset = get_cross_margin_asset(asset_name)
    return Decimal(asset.get("free", "0"))


def safe_cancel_oco(symbol: str, order_list_id: int | None):
    if order_list_id is None:
        return None
    try:
        result = cancel_margin_oco(symbol, order_list_id)
        print(f"[CANCEL OCO] success: {result}")
        return result
    except Exception as e:
        print(f"[CANCEL OCO] skipped/failed: {e}")
        return None


# ---------------------------
# Main
# ---------------------------
def main():
    if not API_KEY or not API_SECRET:
        raise RuntimeError("BINANCE_API_KEY / BINANCE_API_SECRET 환경변수를 설정하세요.")

    print_cross_margin_balance()

    print(f"[WAIT] sleeping {WAIT_SECONDS} seconds before entry...")
    time.sleep(WAIT_SECONDS)

    print("[INFO] Loading symbol filters...")
    filters = get_symbol_filters(SYMBOL)

    qty_filter = filters["LOT_SIZE"]
    if not qty_filter:
        raise RuntimeError("LOT_SIZE / MARKET_LOT_SIZE filter not found.")

    step_size = qty_filter["stepSize"]
    min_qty = Decimal(qty_filter["minQty"])
    min_notional = get_min_notional(filters)

    current_balance_usdt = print_cross_margin_balance()
    buy_usdt = floor_to_step(
        current_balance_usdt * ENTRY_BALANCE_RATIO * ENTRY_LEVERAGE_MULTIPLE,
        "0.01",
    )

    if buy_usdt <= 0:
        raise RuntimeError(f"매수 금액이 0 이하입니다: {buy_usdt}")

    print(
        "[STEP 1] "
        f"{buy_usdt} USDT BTC market buy "
        f"({ENTRY_BALANCE_RATIO * 100}% balance * {ENTRY_LEVERAGE_MULTIPLE}x)"
    )
    buy = place_cross_margin_market_buy(SYMBOL, buy_usdt)
    print("[BUY]", buy)

    executed_qty_raw = buy.get("executedQty")
    status = buy.get("status")

    if not executed_qty_raw:
        raise RuntimeError("executedQty가 없습니다. 매수 응답을 확인하세요.")
    if status not in ("FILLED", "PARTIALLY_FILLED"):
        raise RuntimeError(f"매수 주문 상태가 예상과 다릅니다: {status}")

    executed_qty = Decimal(executed_qty_raw)

    fills = buy.get("fills", [])
    commission_btc = Decimal("0")

    for f in fills:
        if f.get("commissionAsset") == "BTC":
            commission_btc += Decimal(f["commission"])

    net_qty = executed_qty - commission_btc
    sell_qty = floor_to_step(net_qty, step_size)
    qty_str = decimal_to_str(sell_qty)

    if sell_qty < min_qty:
        raise RuntimeError(f"체결 수량이 최소 주문 수량보다 작습니다: {sell_qty} < {min_qty}")

    qty_str = decimal_to_str(sell_qty)
    print(f"[INFO] executedQty={executed_qty_raw}, roundedSellQty={qty_str}")

    print(f"[STEP 2] Place OCO sell TP {TAKE_PROFIT} / SL {STOP1}")
    oco1 = place_cross_margin_oco_sell(SYMBOL, qty_str, TAKE_PROFIT, STOP1)
    print("[OCO1]", oco1)
    oco1_id = oco1.get("orderListId")

    print(f"[WAIT] sleeping {WAIT_SECONDS} seconds...")
    time.sleep(WAIT_SECONDS)

    print(f"[STEP 3] Cancel old OCO and move SL to {STOP2}")
    safe_cancel_oco(SYMBOL, oco1_id)

    oco2_id = None
    try:
        oco2 = place_cross_margin_oco_sell(SYMBOL, qty_str, TAKE_PROFIT, STOP2)
        print("[OCO2]", oco2)
        oco2_id = oco2.get("orderListId")
    except Exception as e:
        print(f"[OCO2] failed: {e}")

    print(f"[WAIT] sleeping {WAIT_SECONDS} seconds...")
    time.sleep(WAIT_SECONDS)

    print("[STEP 4] Cancel current OCO and market-sell remaining entry BTC")
    safe_cancel_oco(SYMBOL, oco2_id)

    free_btc = get_free_margin_asset_amount("BTC")
    final_sell_qty = floor_to_step(min(free_btc, sell_qty), step_size)
    if final_sell_qty < min_qty:
        print(f"[SELL ALL] market sell skipped: free BTC {free_btc} < minQty {min_qty}")
        print("[STEP 4-1] Try cross margin manual liquidation")
        liquidation = manual_liquidate_cross_margin()
        print("[MANUAL LIQUIDATION]", liquidation)
        return

    current_price = get_symbol_price(SYMBOL)
    final_sell_notional = final_sell_qty * current_price
    if final_sell_notional < min_notional:
        print(
            "[SELL ALL] market sell skipped: "
            f"notional {final_sell_notional:.8f} USDT < minNotional {min_notional} USDT "
            f"(qty={final_sell_qty}, price={current_price})"
        )
        print("[STEP 4-1] Try cross margin manual liquidation")
        liquidation = manual_liquidate_cross_margin()
        print("[MANUAL LIQUIDATION]", liquidation)
        return

    try:
        sell = place_cross_margin_market_sell(SYMBOL, decimal_to_str(final_sell_qty))
        print("[SELL ALL]", sell)
    except Exception as e:
        print(f"[SELL ALL] failed: {e}")
        print("[NOTE] 이미 TP/SL이 먼저 체결되어 포지션이 없을 수 있습니다.")


if __name__ == "__main__":
    main()
