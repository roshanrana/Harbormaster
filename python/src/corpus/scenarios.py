"""The twelve adversarial cases from requirements section 8.

Each entry here is a file designed to break something specific. They are
generated rather than hand-written so they stay consistent with the venue
vocabularies in ``generate.py``, and they are named so a failing scenario test
points at the case rather than at a fixture number.

The list is the honest part of this project. Any system can parse a tidy CSV;
what distinguishes one worth deploying is what it does with the ninth file on a
Friday afternoon that has yesterday's date in the name and Wednesday's business
inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from corpus.generate import VENUES, CorpusGenerator, Trade

# The corpus is anchored on a fixed week so calendar behaviour is reproducible.
#   Thu 2026-08-27, Fri 2026-08-28, Sat/Sun 29-30, Mon 2026-08-31
MONDAY = date(2026, 8, 31)
FRIDAY = date(2026, 8, 28)
THURSDAY = date(2026, 8, 27)


@dataclass(slots=True)
class Scenario:
    """One adversarial fixture and what it is designed to break."""

    name: str
    designed_to_break: str
    expected: str
    files: list[Path]


class ScenarioBuilder:
    """Builds the twelve adversarial fixtures into a directory."""

    def __init__(self, out: Path, seed: int = 20260831) -> None:
        self.out = out
        self.gen = CorpusGenerator(seed)

    def build_all(self) -> list[Scenario]:
        return [
            self.late_arrival(),
            self.filename_content_disagreement(),
            self.exact_duplicate(),
            self.redelivery_under_new_name(),
            self.correction_after_dispatch(),
            self.multi_date_file(),
            self.four_price_columns(),
            self.bare_price_header(),
            self.email_cash_advice(),
            self.unattributable_file(),
            self.awkward_workbook(),
            self.totals_row_and_preamble(),
        ]

    # 1
    def late_arrival(self) -> Scenario:
        """A file landing Monday whose contents belong to Friday."""
        trades = self._cme_trades(FRIDAY, 12)
        path = self.out / "01_late_arrival" / "MCP_TRD_20260831.csv"
        self.gen.write_delimited(path, trades, VENUES["CME"])
        gl = self.out / "01_late_arrival" / "GL_CLNT004_TRADE_20260828.csv"
        self.gen.write_gl_extract(gl, trades, "CLNT004")
        return Scenario(
            name="late_arrival",
            designed_to_break="routing a late file onto today's ledger instead of Friday's",
            expected="resolves to 2026-08-28 and binds to Friday's slot, not Monday's",
            files=[path, gl],
        )

    # 2
    def filename_content_disagreement(self) -> Scenario:
        """Filename says Thursday, contents say Friday."""
        trades = self._cme_trades(FRIDAY, 8)
        path = self.out / "02_date_disagreement" / "MCP_TRD_20260827.csv"
        self.gen.write_delimited(path, trades, VENUES["CME"])
        return Scenario(
            name="filename_content_disagreement",
            designed_to_break="silently trusting the filename date",
            expected="content wins, mismatch_flagged is true, and the note names both dates",
            files=[path],
        )

    # 3
    def exact_duplicate(self) -> Scenario:
        """The identical file delivered twice."""
        trades = self._cme_trades(FRIDAY, 6)
        first = self.out / "03_exact_duplicate" / "MCP_TRD_20260828.csv"
        second = self.out / "03_exact_duplicate" / "resend" / "MCP_TRD_20260828.csv"
        self.gen.write_delimited(first, trades, VENUES["CME"])
        self.gen.write_delimited(second, trades, VENUES["CME"])
        return Scenario(
            name="exact_duplicate",
            designed_to_break="reprocessing identical content and double-counting a reconciliation",
            expected="second arrival suppressed with verdict DUPLICATE; no second instruction",
            files=[first, second],
        )

    # 4
    def redelivery_under_new_name(self) -> Scenario:
        """Identical content, different filename."""
        trades = self._cme_trades(FRIDAY, 6)
        first = self.out / "04_redelivery" / "MCP_TRD_20260828.csv"
        second = self.out / "04_redelivery" / "MCP_TRD_20260828_RESEND.csv"
        self.gen.write_delimited(first, trades, VENUES["CME"])
        self.gen.write_delimited(second, trades, VENUES["CME"])
        return Scenario(
            name="redelivery_under_new_name",
            designed_to_break="treating a renamed resend as a new file",
            expected="suppressed with verdict REDELIVERY, and the suppression is audited",
            files=[first, second],
        )

    # 5
    def correction_after_dispatch(self) -> Scenario:
        """An amended file for a slot that already dispatched."""
        original = self._cme_trades(FRIDAY, 10)
        corrected = list(original)
        corrected[3] = Trade(
            trade_id=original[3].trade_id,
            account_id=original[3].account_id,
            instrument=original[3].instrument,
            trade_date=original[3].trade_date,
            value_date=original[3].value_date,
            quantity=original[3].quantity * 2,  # the amendment
            trade_price=original[3].trade_price,
            settlement_price=original[3].settlement_price,
            side=original[3].side,
        )
        a = self.out / "05_correction" / "MCP_TRD_20260828.csv"
        b = self.out / "05_correction" / "amended" / "MCP_TRD_20260828.csv"
        self.gen.write_delimited(a, original, VENUES["CME"])
        self.gen.write_delimited(b, corrected, VENUES["CME"])
        return Scenario(
            name="correction_after_dispatch",
            designed_to_break="leaving a stale reconciliation in place after an amendment",
            expected="void published before the replacement, both on the same slot partition",
            files=[a, b],
        )

    # 6
    def multi_date_file(self) -> Scenario:
        """One file spanning three value dates."""
        trades = (
            self._cme_trades(THURSDAY, 4)
            + self._cme_trades(FRIDAY, 5)
            + self._cme_trades(MONDAY, 3)
        )
        path = self.out / "06_multi_date" / "MCP_TRD_20260831.csv"
        self.gen.write_delimited(path, trades, VENUES["CME"])
        return Scenario(
            name="multi_date_file",
            designed_to_break="forcing a mixed-date file onto one value date",
            expected="splits into 3 sub-batches; row counts sum to the source",
            files=[path],
        )

    # 7
    def four_price_columns(self) -> Scenario:
        """An ICE extract carrying four price-like columns."""
        trades = self._trades("ICE", ["8842-00119"], FRIDAY, 10)
        path = self.out / "07_four_prices" / "ICE_TRD_20260828.csv"
        self.gen.write_delimited(path, trades, VENUES["ICE"])
        return Scenario(
            name="four_price_columns",
            designed_to_break="conflating trade price with settlement, mark or prior settle",
            expected=(
                "Price maps to trade_price, Settle Px to settlement_price, "
                "surplus columns left unassigned"
            ),
            files=[path],
        )

    # 8
    def bare_price_header(self) -> Scenario:
        """Two price columns labelled only Price and Px."""
        trades = self._cme_trades(FRIDAY, 15)
        path = self.out / "08_bare_price" / "MCP_TRD_20260828.csv"
        self.gen.write_delimited(path, trades, VENUES["CME"], bare_price_header=True)
        return Scenario(
            name="bare_price_header",
            designed_to_break="header-only mapping, which cannot separate these two",
            expected="resolved structurally: Price varies per row, Px repeats per instrument",
            files=[path],
        )

    # 9
    def email_cash_advice(self) -> Scenario:
        """A cash movement described in prose."""
        path = self.out / "09_email_cash" / "ardent-cash-2026-08-28.txt"
        self.gen.write_email(
            path,
            [
                ("AGM-5590-01", Decimal("1250000.00"), "USD", FRIDAY),
                ("AGM-5590-01", Decimal("-487350.25"), "USD", FRIDAY),
                ("AGM-5590-01", Decimal("96200.00"), "EUR", FRIDAY),
            ],
        )
        return Scenario(
            name="email_cash_advice",
            designed_to_break="assuming every arrival is tabular",
            expected="three movements extracted with amounts, currencies and value date",
            files=[path],
        )

    # 10
    def unattributable_file(self) -> Scenario:
        """Nothing identifies the owner."""
        path = self.out / "10_unattributable" / "export_final.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "Alpha,Beta,Gamma,Delta\n"
            "1,2026-08-28,100,42.50\n"
            "2,2026-08-28,250,42.75\n"
            "3,2026-08-28,75,42.60\n"
        )
        return Scenario(
            name="unattributable_file",
            designed_to_break="guessing an owner rather than asking a human",
            expected="quarantined with a reason naming that the client could not be determined",
            files=[path],
        )

    # 11
    def awkward_workbook(self) -> Scenario:
        """A custody workbook with a cover sheet, banner and totals row."""
        trades = self._trades("LSEG", ["GB-2201-4407"], FRIDAY, 9)
        path = self.out / "11_awkward_workbook" / "HF_Custody_Positions_28Aug2026.xlsx"
        self.gen.write_excel(path, trades, VENUES["LSEG"], cover_sheet=True)
        return Scenario(
            name="awkward_workbook",
            designed_to_break="reading sheet 0, row 0 and trusting it",
            expected="selects the data sheet, finds the header at row 4, excludes the totals row",
            files=[path],
        )

    # 12
    def totals_row_and_preamble(self) -> Scenario:
        """A CSV wrapped in a title banner and closed with a summary line."""
        trades = self._trades("HKEX", ["HK-4471-0021"], FRIDAY, 7)
        path = self.out / "12_preamble_totals" / "PRS_trd_20260828.csv"
        self.gen.write_delimited(
            path,
            trades,
            VENUES["HKEX"],
            preamble="PACIFIC RIM SECURITIES\nDaily Trade Extract\nGenerated 2026-08-31 02:15 HKT",
            totals_row=True,
        )
        return Scenario(
            name="totals_row_and_preamble",
            designed_to_break="counting a summary line as a trade and a banner as the header",
            expected="7 rows parsed, header found below the banner, totals row excluded",
            files=[path],
        )

    # --- helpers -----------------------------------------------------------

    def _cme_trades(self, value_date: date, count: int) -> list[Trade]:
        return self._trades("CME", ["8842-00119", "8842-00204"], value_date, count)

    def _trades(self, venue: str, accounts: list[str], value_date: date, count: int) -> list[Trade]:
        return self.gen.trades(
            account_ids=accounts, venue=venue, value_date=value_date, count=count
        )


def build(out: Path, seed: int = 20260831) -> list[Scenario]:
    """Generate every adversarial fixture under ``out``."""
    return ScenarioBuilder(out, seed).build_all()
