# db.py
from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

DDL = """
CREATE TABLE IF NOT EXISTS trade (
  id                BIGSERIAL PRIMARY KEY,
  bot_id            TEXT NOT NULL,
  symbol            TEXT NOT NULL,

  open_time         TIMESTAMPTZ,
  open_side         TEXT CHECK (open_side IN ('long','short')),
  leverage          INT,
  margin_usdt       DOUBLE PRECISION,
  open_price        DOUBLE PRECISION,
  open_order_id     TEXT,

  status            TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  close_time        TIMESTAMPTZ,
  realized_pnl_usdt DOUBLE PRECISION,
  total_fees_usdt   DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS trade_event (
  id            BIGSERIAL PRIMARY KEY,
  trade_id      BIGINT NOT NULL REFERENCES trade(id) ON DELETE CASCADE,
  event_time    TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type    TEXT NOT NULL,  -- open / tp / close / sl / error
  side          TEXT CHECK (side IN ('long','short')),
  price         DOUBLE PRECISION,
  qty           DOUBLE PRECISION,
  percent       DOUBLE PRECISION,
  pnl_usdt      DOUBLE PRECISION,
  fees_usdt     DOUBLE PRECISION,
  order_id      TEXT,
  raw_signal    TEXT,
  meta          JSONB
);

CREATE INDEX IF NOT EXISTS idx_trade_bot_time
  ON trade(bot_id, open_time DESC);

CREATE INDEX IF NOT EXISTS idx_trade_event_trade_time
  ON trade_event(trade_id, event_time ASC);
"""


class DB:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = os.getenv("DATABASE_URL", "")
        print(self.database_url)
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not set. Put it in .env or environment variables.")

    def _conn(self):
        # dict_row: SELECT 결과를 dict로 받기 편함
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(DDL)
            conn.commit()

    def create_trade(
        self,
        *,
        bot_id: str,
        symbol: str,
        open_side: str,
        leverage: int,
        margin_usdt: float,
        open_price: float | None = None,
        open_order_id: str | None = None,
        raw_signal: str | None = None,
        open_meta: dict | None = None,
    ) -> int:
        """
        trade 1행 생성 + open 이벤트 1행도 같이 남김
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trade(
                        bot_id, symbol, open_time, open_side, leverage, margin_usdt, open_price, open_order_id, status
                    )
                    VALUES (%s, %s, now(), %s, %s, %s, %s, %s, 'open')
                    RETURNING id;
                    """,
                    (bot_id, symbol, open_side, leverage, margin_usdt, open_price, open_order_id),
                )
                trade_id = int(cur.fetchone()["id"])

                # open 이벤트 기록
                cur.execute(
                    """
                    INSERT INTO trade_event(
                        trade_id, event_type, side, price, percent, order_id, raw_signal, meta
                    )
                    VALUES (%s, 'open', %s, %s, NULL, %s, %s, %s);
                    """,
                    (
                        trade_id,
                        open_side,
                        open_price,
                        open_order_id,
                        raw_signal,
                        Jsonb(open_meta) if open_meta is not None else None,
                    ),
                )

            conn.commit()
            return trade_id

    def add_event(
        self,
        *,
        trade_id: int,
        event_type: str,
        side: str | None = None,
        price: float | None = None,
        qty: float | None = None,
        percent: float | None = None,
        pnl_usdt: float | None = None,
        fees_usdt: float | None = None,
        order_id: str | None = None,
        raw_signal: str | None = None,
        meta: dict | None = None,
    ) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trade_event(
                        trade_id, event_type, side, price, qty, percent, pnl_usdt, fees_usdt, order_id, raw_signal, meta
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id;
                    """,
                    (
                        trade_id,
                        event_type,
                        side,
                        price,
                        qty,
                        percent,
                        pnl_usdt,
                        fees_usdt,
                        order_id,
                        raw_signal,
                        Jsonb(meta) if meta is not None else None,
                    ),
                )
                event_id = int(cur.fetchone()["id"])
            conn.commit()
            return event_id

    def close_trade(
        self,
        *,
        trade_id: int,
        realized_pnl_usdt: float | None = None,
        total_fees_usdt: float | None = None,
        close_order_id: str | None = None,
        close_price: float | None = None,
        side: str | None = None,
        raw_signal: str | None = None,
        close_meta: dict | None = None,
    ) -> None:
        """
        trade 테이블을 closed로 업데이트 + close 이벤트 1행 기록
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                # close 이벤트 기록
                cur.execute(
                    """
                    INSERT INTO trade_event(
                        trade_id, event_type, side, price, pnl_usdt, fees_usdt, order_id, raw_signal, meta
                    )
                    VALUES (%s, 'close', %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        trade_id,
                        side,
                        close_price,
                        realized_pnl_usdt,
                        total_fees_usdt,
                        close_order_id,
                        raw_signal,
                        Jsonb(close_meta) if close_meta is not None else None,
                    ),
                )

                # trade row 업데이트
                cur.execute(
                    """
                    UPDATE trade
                    SET status='closed',
                        close_time=now(),
                        realized_pnl_usdt=%s,
                        total_fees_usdt=%s
                    WHERE id=%s;
                    """,
                    (realized_pnl_usdt, total_fees_usdt, trade_id),
                )

            conn.commit()

    def get_trade(self, trade_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM trade WHERE id=%s;",
                (trade_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_trade_events(self, trade_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_event WHERE trade_id=%s ORDER BY event_time ASC, id ASC;",
                (trade_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def latest_trades(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trade ORDER BY id DESC LIMIT %s;",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_open_trade_id(self, *, bot_id: str, symbol: str) -> int | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM trade
                WHERE bot_id=%s AND symbol=%s AND status='open'
                ORDER BY open_time DESC, id DESC
                LIMIT 1;
                """,
                (bot_id, symbol),
            ).fetchone()
            return int(row["id"]) if row else None