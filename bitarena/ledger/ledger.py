"""Append-only, Ed25519-signed, hash-chained trade ledger.

Each record carries exactly the fields a Bitget submission must show — timestamp,
trading pair, direction, price, quantity, account balance change — plus the
firewall decision and a hash of the certificate that authorized the trade. Records
are chained (each embeds the previous record's hash) and individually signed: any
mutation, reordering, or mid-chain deletion is detectable by :meth:`SignedLedger.verify`.
Tail truncation (dropping the most recent records) leaves a self-consistent prefix, so
it is caught only when ``verify`` is given the trusted ``expected_count`` the arena holds.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..domain.market import Side
from ..domain.verdict import Decision
from ..firewall.signing import Signer, model_canonical, sha256_hex, verify_bytes

GENESIS_HASH = "0" * 64
_CORE_EXCLUDE = frozenset({"record_hash", "signature_hex", "public_key_hex"})
_SIG_EXCLUDE = frozenset({"signature_hex", "public_key_hex"})


class TradeRecord(BaseModel):
    """One signed, chained trade event."""

    model_config = ConfigDict(frozen=True)

    seq: int
    ts: int  # epoch milliseconds
    agent_id: str
    symbol: str  # trading pair
    side: Side  # direction
    price: float  # fill price
    quantity: float
    notional_usd: float
    fee_usd: float
    balance_before_usd: float
    balance_after_usd: float
    decision: Decision  # firewall verdict that authorized this trade
    cert_hash: str  # sha256 of the firewall certificate (links trade -> verdict)
    prev_hash: str
    record_hash: str = ""
    signature_hex: str = ""
    public_key_hex: str = ""

    @property
    def balance_change_usd(self) -> float:
        return self.balance_after_usd - self.balance_before_usd


class SignedLedger:
    """In-memory + optional JSONL-on-disk signed ledger."""

    def __init__(self, signer: Signer, path: Path | str | None = None) -> None:
        self._signer = signer
        self._path = Path(path) if path else None
        self._records: list[TradeRecord] = []
        self._last_hash = GENESIS_HASH
        self._seq = 0
        if self._path is not None and self._path.exists():
            self._load()

    @property
    def records(self) -> list[TradeRecord]:
        return list(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def append(
        self,
        *,
        ts: int,
        agent_id: str,
        symbol: str,
        side: Side,
        price: float,
        quantity: float,
        notional_usd: float,
        fee_usd: float,
        balance_before_usd: float,
        balance_after_usd: float,
        decision: Decision,
        cert_hash: str = "",
    ) -> TradeRecord:
        """Append a signed, chained trade record and persist it (if a path is set)."""
        draft = TradeRecord(
            seq=self._seq,
            ts=ts,
            agent_id=agent_id,
            symbol=symbol.upper(),
            side=side,
            price=price,
            quantity=quantity,
            notional_usd=notional_usd,
            fee_usd=fee_usd,
            balance_before_usd=balance_before_usd,
            balance_after_usd=balance_after_usd,
            decision=decision,
            cert_hash=cert_hash,
            prev_hash=self._last_hash,
        )
        record_hash = sha256_hex(model_canonical(draft, exclude=_CORE_EXCLUDE))
        hashed = draft.model_copy(update={"record_hash": record_hash})
        signature = self._signer.sign_bytes(model_canonical(hashed, exclude=_SIG_EXCLUDE))
        record = hashed.model_copy(
            update={"signature_hex": signature, "public_key_hex": self._signer.public_key_hex}
        )

        self._records.append(record)
        self._last_hash = record_hash
        self._seq += 1
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(record.model_dump_json() + "\n")
        return record

    def verify(self, expected_count: int | None = None) -> tuple[bool, list[str]]:
        """Re-validate the whole chain: sequence, links, hashes, and signatures.

        Interior edits (mutation, reordering, mid-chain deletion) are caught by the chain
        itself. Tail truncation leaves a self-consistent prefix, so pass ``expected_count``
        (a trusted committed length — the arena knows how many trades it appended) to catch
        dropped trailing records.
        """
        issues: list[str] = []
        if expected_count is not None and len(self._records) != expected_count:
            issues.append(
                f"truncation: expected {expected_count} records, found {len(self._records)}"
            )
        prev = GENESIS_HASH
        for index, record in enumerate(self._records):
            if record.seq != index:
                issues.append(f"sequence mismatch at index {index} (seq={record.seq})")
            if record.prev_hash != prev:
                issues.append(f"chain break at seq {record.seq}")
            recomputed = sha256_hex(model_canonical(record, exclude=_CORE_EXCLUDE))
            if recomputed != record.record_hash:
                issues.append(f"record hash mismatch at seq {record.seq}")
            payload = model_canonical(record, exclude=_SIG_EXCLUDE)
            if not verify_bytes(record.public_key_hex, record.signature_hex, payload):
                issues.append(f"invalid signature at seq {record.seq}")
            prev = record.record_hash
        return (not issues, issues)

    def required_fields_rows(self) -> list[dict]:
        """Rows with exactly the Bitget-required trade-log fields."""
        return [
            {
                "timestamp_ms": r.ts,
                "pair": r.symbol,
                "direction": r.side.value,
                "price": r.price,
                "quantity": r.quantity,
                "balance_change_usd": round(r.balance_change_usd, 6),
                "account_balance_usd": round(r.balance_after_usd, 6),
            }
            for r in self._records
        ]

    def write_csv(self, path: Path | str) -> None:
        """Write the Bitget-required fields (plus agent + decision) to CSV."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "seq", "timestamp_ms", "agent_id", "pair", "direction",
            "price", "quantity", "notional_usd", "fee_usd",
            "balance_change_usd", "account_balance_usd", "decision", "cert_hash",
        ]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for r in self._records:
                writer.writerow(
                    {
                        "seq": r.seq,
                        "timestamp_ms": r.ts,
                        "agent_id": r.agent_id,
                        "pair": r.symbol,
                        "direction": r.side.value,
                        "price": r.price,
                        "quantity": r.quantity,
                        "notional_usd": r.notional_usd,
                        "fee_usd": r.fee_usd,
                        "balance_change_usd": round(r.balance_change_usd, 6),
                        "account_balance_usd": round(r.balance_after_usd, 6),
                        "decision": r.decision.value,
                        "cert_hash": r.cert_hash,
                    }
                )

    def _load(self) -> None:
        assert self._path is not None
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            self._records.append(TradeRecord.model_validate_json(line))
        if self._records:
            self._last_hash = self._records[-1].record_hash
            self._seq = self._records[-1].seq + 1
