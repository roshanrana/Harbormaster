"""Generating a realistic reference corpus.

Correctness targets (NFR-4, NFR-5, NFR-7) are meaningless measured against
fixtures invented to suit the parser. This module produces files shaped like
the ones the system will actually meet: each venue names its columns the way
that venue names them, each format carries the structural quirks that format
carries, and the awkward cases are generated on purpose rather than discovered
in production.

Everything is seeded. The same seed produces byte-identical output, so a golden
test that fails means the code changed, not that the data did.

The venue vocabularies below are the important part. A generator that emitted
"trade_price" in every file would make the mapping layer look far better than
it is; the whole point is that ICE says ``Settle Px``, Eurex says ``SettlPric``
and LSEG says ``Valuation Price``, and something has to reconcile that.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# --- venue vocabularies ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class VenueProfile:
    """How one venue names things in its extracts."""

    venue: str
    account: str
    instrument: str
    trade_id: str
    trade_date: str
    value_date: str
    quantity: str
    trade_price: str
    settlement_price: str
    net_amount: str
    currency: str
    side: str
    #: Extra price columns this venue emits that carry no canonical meaning.
    surplus_prices: tuple[str, ...] = ()
    delimiter: str = ","
    date_format: str = "%Y-%m-%d"


VENUES: dict[str, VenueProfile] = {
    "CME": VenueProfile(
        venue="CME",
        account="Account ID",
        instrument="Symbol",
        trade_id="TradeID",
        trade_date="Trade Date",
        value_date="Value Date",
        quantity="Qty",
        trade_price="Exec Price",
        settlement_price="Settle Price",
        net_amount="Net Amount",
        currency="CCY",
        side="B/S",
        surplus_prices=("Prior Settle Price",),
    ),
    "ICE": VenueProfile(
        venue="ICE",
        account="ClearingAccount",
        instrument="ContractCode",
        trade_id="DealID",
        trade_date="TradeDt",
        value_date="SettlementDate",
        quantity="Contracts",
        trade_price="Price",
        settlement_price="Settle Px",
        net_amount="NetMoney",
        currency="Currency",
        side="BuySell",
        surplus_prices=("Mark Price", "Prior Settle Px"),
    ),
    "EUREX": VenueProfile(
        venue="EUREX",
        account="SafekeepingAccount",
        instrument="ISIN",
        trade_id="TrdID",
        trade_date="TrdDt",
        value_date="ValueDt",
        quantity="NominalAmount",
        trade_price="DealPrice",
        settlement_price="SettlPric",
        net_amount="SettlementAmount",
        currency="SettlCcy",
        side="Direction",
        date_format="%d.%m.%Y",
    ),
    "LSEG": VenueProfile(
        venue="LSEG",
        account="Custody Account",
        instrument="SEDOL",
        trade_id="Reference",
        trade_date="Trade Date",
        value_date="Valuation Date",
        quantity="Units",
        trade_price="Clean Price",
        settlement_price="Valuation Price",
        net_amount="Consideration",
        currency="Currency Code",
        side="Transaction Type",
        date_format="%d-%b-%Y",
    ),
    "HKEX": VenueProfile(
        venue="HKEX",
        account="Acct",
        instrument="Ticker",
        trade_id="Ticket No",
        trade_date="Business Date",
        value_date="Settlement Date",
        quantity="Shares",
        trade_price="Avg Price",
        settlement_price="Closing Price",
        net_amount="Net Proceeds",
        currency="Curr",
        side="Action",
        delimiter="|",
    ),
    "NASDAQ": VenueProfile(
        venue="NASDAQ",
        account="AccountNumber",
        instrument="Symbol",
        trade_id="ExecID",
        trade_date="TransactionDate",
        value_date="SettleDate",
        quantity="Shares",
        trade_price="LastPx",
        settlement_price="ClosingPrice",
        net_amount="Proceeds",
        currency="Currency",
        side="Side",
        date_format="%m/%d/%Y",
    ),
    "CBOE": VenueProfile(
        venue="CBOE",
        account="Portfolio",
        instrument="OCC Symbol",
        trade_id="Ticket",
        trade_date="Activity Date",
        value_date="Position Date",
        quantity="Contracts",
        trade_price="Trade Price",
        settlement_price="Official Settlement Price",
        net_amount="Market Value",
        currency="CCY",
        side="Long/Short",
        surplus_prices=("Theoretical Price",),
    ),
    "NYSE": VenueProfile(
        venue="NYSE",
        account="Account",
        instrument="Ticker",
        trade_id="Ref No",
        trade_date="Trade Date",
        value_date="Effective Date",
        quantity="Quantity",
        trade_price="Price",
        settlement_price="Close Price",
        net_amount="Cash Amount",
        currency="Currency",
        side="Direction",
    ),
}


# --- instruments -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    isin: str
    sedol: str
    kind: str
    base_price: Decimal
    currency: str


INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("ESZ6", "US78378X1072", "2840215", "FUTURE", Decimal("5401.25"), "USD"),
    Instrument("NQZ6", "US6311011026", "2840216", "FUTURE", Decimal("19850.25"), "USD"),
    Instrument("CLF7", "US1912161007", "2840217", "FUTURE", Decimal("78.42"), "USD"),
    Instrument("FGBLZ6", "DE0001102614", "5602604", "FUTURE", Decimal("132.87"), "EUR"),
    Instrument("FESXZ6", "EU0009658145", "5602605", "FUTURE", Decimal("4912.00"), "EUR"),
    Instrument("VOD.L", "GB00BH4HKS39", "BH4HKS3", "EQUITY", Decimal("74.28"), "GBP"),
    Instrument("HSBA.L", "GB0005405286", "0540528", "EQUITY", Decimal("658.90"), "GBP"),
    Instrument("0700.HK", "KYG875721634", "BMMV2K8", "EQUITY", Decimal("372.40"), "HKD"),
    Instrument("AAPL", "US0378331005", "2046251", "EQUITY", Decimal("241.18"), "USD"),
    Instrument("MSFT", "US5949181045", "2588173", "EQUITY", Decimal("428.55"), "USD"),
    Instrument("SPX 5400 C", "US78378X1072", "2840218", "OPTION", Decimal("112.30"), "USD"),
)


@dataclass(slots=True)
class Trade:
    """One economic record, before it is expressed in any venue's dialect."""

    trade_id: str
    account_id: str
    instrument: Instrument
    trade_date: date
    value_date: date
    quantity: Decimal
    trade_price: Decimal
    settlement_price: Decimal
    side: str

    @property
    def net_amount(self) -> Decimal:
        return (abs(self.quantity) * self.trade_price).quantize(Decimal("0.01"))

    @property
    def currency(self) -> str:
        return self.instrument.currency


@dataclass(slots=True)
class GeneratedFile:
    path: Path
    client_id: str
    venue: str
    domain: str
    value_date: str
    fmt: str
    trades: list[Trade] = field(default_factory=list)
    note: str = ""


# --- generation ------------------------------------------------------------


class CorpusGenerator:
    """Produces a deterministic corpus of counterparty and GL files."""

    def __init__(self, seed: int = 20260831) -> None:
        self.rng = random.Random(seed)

    def trades(
        self,
        *,
        account_ids: list[str],
        venue: str,
        value_date: date,
        count: int,
        trade_date: date | None = None,
    ) -> list[Trade]:
        """Generate trades whose settlement prices repeat per instrument.

        That repetition is not cosmetic. It is the structural signal the price
        disambiguator relies on: a settlement price is a property of an
        instrument on a day, a trade price is a property of an execution.
        """
        td = trade_date or self._previous_weekday(value_date)
        pool = [i for i in INSTRUMENTS if self._venue_allows(venue, i)]
        settlements: dict[str, Decimal] = {}
        out: list[Trade] = []

        for n in range(count):
            inst = pool[self.rng.randrange(len(pool))]
            if inst.symbol not in settlements:
                drift = Decimal(self.rng.randrange(-300, 300)) / Decimal(100)
                settlements[inst.symbol] = (inst.base_price + drift).quantize(Decimal("0.01"))
            tick = Decimal(self.rng.randrange(-250, 250)) / Decimal(100)
            trade_price = (settlements[inst.symbol] + tick).quantize(Decimal("0.01"))
            side = "B" if self.rng.random() < 0.6 else "S"
            qty = Decimal(self.rng.randrange(1, 500))
            out.append(
                Trade(
                    trade_id=f"T{value_date.strftime('%m%d')}{n:04d}",
                    account_id=account_ids[n % len(account_ids)],
                    instrument=inst,
                    trade_date=td,
                    value_date=value_date,
                    quantity=qty if side == "B" else -qty,
                    trade_price=trade_price,
                    settlement_price=settlements[inst.symbol],
                    side=side,
                )
            )
        return out

    def _venue_allows(self, venue: str, inst: Instrument) -> bool:
        if venue in {"EUREX"}:
            return inst.currency == "EUR"
        if venue in {"LSEG"}:
            return inst.currency == "GBP"
        if venue in {"HKEX"}:
            return inst.currency == "HKD"
        return inst.currency == "USD"

    @staticmethod
    def _previous_weekday(d: date) -> date:
        prev = d - timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        return prev

    # --- writers -----------------------------------------------------------

    def write_delimited(
        self,
        path: Path,
        trades: list[Trade],
        profile: VenueProfile,
        *,
        include_value_date: bool = True,
        preamble: str | None = None,
        totals_row: bool = False,
        bare_price_header: bool = False,
    ) -> None:
        """Write a venue-dialect delimited file."""
        d = profile.delimiter
        headers = [
            profile.account,
            profile.instrument,
            profile.trade_id,
            profile.trade_date,
        ]
        if include_value_date:
            headers.append(profile.value_date)
        headers += [
            profile.quantity,
            "Price" if bare_price_header else profile.trade_price,
            "Px" if bare_price_header else profile.settlement_price,
            *profile.surplus_prices,
            profile.net_amount,
            profile.currency,
            profile.side,
        ]

        lines: list[str] = []
        if preamble:
            lines.extend(preamble.splitlines())
            lines.append("")
        lines.append(d.join(headers))

        for t in trades:
            row = [
                t.account_id,
                self._instrument_for(profile, t.instrument),
                t.trade_id,
                t.trade_date.strftime(profile.date_format),
            ]
            if include_value_date:
                row.append(t.value_date.strftime(profile.date_format))
            row += [str(t.quantity), str(t.trade_price), str(t.settlement_price)]
            row += [str(t.settlement_price - Decimal("1.50")) for _ in profile.surplus_prices]
            row += [str(t.net_amount), t.currency, t.side]
            lines.append(d.join(row))

        if totals_row:
            total = sum((t.net_amount for t in trades), Decimal("0"))
            row = ["Total"] + [""] * (len(headers) - 3) + [str(total), "", ""]
            lines.append(d.join(row[: len(headers)]))

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")

    @staticmethod
    def _instrument_for(profile: VenueProfile, inst: Instrument) -> str:
        field_name = profile.instrument.lower()
        if "isin" in field_name:
            return inst.isin
        if "sedol" in field_name:
            return inst.sedol
        return inst.symbol

    def write_xml(self, path: Path, trades: list[Trade], profile: VenueProfile) -> None:
        """Write a nested XML extract with attributes and child elements."""
        rows = []
        for t in trades:
            rows.append(
                f'    <Trade id="{t.trade_id}" side="{t.side}">\n'
                f"      <Account>{t.account_id}</Account>\n"
                f"      <Instrument>{self._instrument_for(profile, t.instrument)}</Instrument>\n"
                f"      <TradeDt>{t.trade_date.isoformat()}</TradeDt>\n"
                f"      <ValueDt>{t.value_date.isoformat()}</ValueDt>\n"
                f"      <Quantity>{t.quantity}</Quantity>\n"
                f"      <DealPrice>{t.trade_price}</DealPrice>\n"
                f"      <SettlPric>{t.settlement_price}</SettlPric>\n"
                f"      <SettlementAmount>{t.net_amount}</SettlementAmount>\n"
                f"      <SettlCcy>{t.currency}</SettlCcy>\n"
                f"    </Trade>"
            )
        body = "\n".join(rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<TradeExtract venue="{profile.venue}" '
            f'generated="{trades[0].value_date.isoformat()}">\n'
            "  <Trades>\n"
            f"{body}\n"
            "  </Trades>\n"
            "</TradeExtract>\n"
        )

    def write_fixml(self, path: Path, trades: list[Trade]) -> None:
        """Write FIXML execution reports with standard tag names."""
        rows = []
        for t in trades:
            side = "1" if t.side == "B" else "2"
            rows.append(
                f'  <ExecRpt ExecID="{t.trade_id}" Side="{side}" '
                f'LastQty="{abs(t.quantity)}" LastPx="{t.trade_price}" '
                f'SettlPx="{t.settlement_price}" NetMoney="{t.net_amount}" '
                f'TrdDt="{t.trade_date.isoformat()}" SettlDt="{t.value_date.isoformat()}" '
                f'Ccy="{t.currency}">\n'
                f'    <Instrmt Sym="{t.instrument.symbol}" ID="{t.instrument.isin}" IDSrc="4"/>\n'
                f'    <Pty ID="{t.account_id}" R="24"/>\n'
                "  </ExecRpt>"
            )
        body = "\n".join(rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'<FIXML v="5.0" r="20030618" s="20040109">\n{body}\n</FIXML>\n')

    def write_json(self, path: Path, trades: list[Trade], profile: VenueProfile) -> None:
        """Write a nested JSON payload of the shape an upstream queue emits."""
        payload = {
            "messageType": "TRADE_EXTRACT",
            "venue": profile.venue,
            "records": [
                {
                    "tradeId": t.trade_id,
                    "account": {"id": t.account_id, "type": "CUSTODY"},
                    "instrument": {"symbol": t.instrument.symbol, "isin": t.instrument.isin},
                    "dates": {
                        "tradeDate": t.trade_date.isoformat(),
                        "valueDate": t.value_date.isoformat(),
                    },
                    "economics": {
                        "quantity": str(t.quantity),
                        "tradePrice": str(t.trade_price),
                        "settlementPrice": str(t.settlement_price),
                        "netAmount": str(t.net_amount),
                        "currency": t.currency,
                    },
                    "side": "BUY" if t.side == "B" else "SELL",
                }
                for t in trades
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

    def write_email(self, path: Path, movements: list[tuple[str, Decimal, str, date]]) -> None:
        """Write a free-text cash advice email of the kind operations teams get."""
        lines = [
            "From: operations@ardentglobal.example",
            "To: recon@bank.example",
            f"Subject: Cash movements for value {movements[0][3].isoformat()}",
            "",
            "Morning all,",
            "",
            "Please find below today's cash movements for settlement.",
            "",
        ]
        for account, amount, currency, value_date in movements:
            direction = "credit" if amount > 0 else "debit"
            lines.append(
                f"  Account {account}: {direction} of {currency} {abs(amount):,.2f} "
                f"value {value_date.strftime('%d %B %Y')}"
            )
        lines += [
            "",
            "Let us know if anything looks out of line.",
            "",
            "Regards,",
            "Ardent Operations",
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")

    def write_excel(
        self, path: Path, trades: list[Trade], profile: VenueProfile, *, cover_sheet: bool = True
    ) -> None:
        """Write a custody workbook, complete with the quirks real ones have."""
        from openpyxl import Workbook

        wb = Workbook()
        first = wb.active
        assert first is not None
        if cover_sheet:
            # Real custody workbooks lead with a cover sheet. A parser that
            # takes sheet index 0 reads the disclaimer, not the data.
            first.title = "Cover"
            first["A1"] = "HALLOWAY AND FINCH"
            first["A2"] = "Custody Statement"
            first["A4"] = "This report is confidential."
            sheet = wb.create_sheet("Holdings")
        else:
            first.title = "Holdings"
            sheet = first

        # Title banner and a blank spacer above the header row.
        sheet["A1"] = "CUSTODY POSITION STATEMENT"
        sheet["A2"] = f"Valuation date {trades[0].value_date.isoformat()}"

        headers = [
            profile.account,
            profile.instrument,
            profile.trade_id,
            profile.trade_date,
            profile.value_date,
            profile.quantity,
            profile.trade_price,
            profile.settlement_price,
            profile.net_amount,
            profile.currency,
            profile.side,
        ]
        for col, header in enumerate(headers, start=1):
            sheet.cell(row=4, column=col, value=header)

        for r, t in enumerate(trades, start=5):
            values = [
                t.account_id,
                self._instrument_for(profile, t.instrument),
                t.trade_id,
                t.trade_date.strftime(profile.date_format),
                t.value_date.strftime(profile.date_format),
                float(t.quantity),
                float(t.trade_price),
                float(t.settlement_price),
                float(t.net_amount),
                t.currency,
                t.side,
            ]
            for c_idx, value in enumerate(values, start=1):
                sheet.cell(row=r, column=c_idx, value=value)

        # Trailing totals row, which is not a holding.
        total_row = len(trades) + 5
        sheet.cell(row=total_row, column=1, value="Total")
        sheet.cell(row=total_row, column=9, value=float(sum(t.net_amount for t in trades)))

        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)

    def write_gl_extract(self, path: Path, trades: list[Trade], client_id: str) -> None:
        """Write the internal side of the reconciliation.

        The GL extract is well-controlled and uses consistent column names, in
        contrast to everything arriving from outside. That asymmetry is the
        point: side 1 is easy, side 2 is the problem.
        """
        headers = [
            "gl_account",
            "client_id",
            "instrument_id",
            "trade_id",
            "trade_date",
            "value_date",
            "quantity",
            "trade_price",
            "settlement_price",
            "net_amount",
            "currency",
            "side",
        ]
        lines = [",".join(headers)]
        for t in trades:
            lines.append(
                ",".join(
                    [
                        t.account_id,
                        client_id,
                        t.instrument.symbol,
                        t.trade_id,
                        t.trade_date.isoformat(),
                        t.value_date.isoformat(),
                        str(t.quantity),
                        str(t.trade_price),
                        str(t.settlement_price),
                        str(t.net_amount),
                        t.currency,
                        "BUY" if t.side == "B" else "SELL",
                    ]
                )
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
