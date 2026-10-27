"""Parse a MIRRORED ELM/STN serial text stream into the MES-learn capture format.

PURE PARSING. No serial I/O, no adapter, nothing is ever transmitted. Input is
what MultiEcuScan and the adapter say to each other over a COM port (ELM327
text protocol), copied by a PC-side port mirror (see
``docs/design/SERIAL_MIRROR_CAPTURE.md``). Output is the SAME capture shape
``cuore.live.mes_learn`` records and ``cuore.live.procedure_capture`` consumes:
``[{"t": float, "id": "18DA10F1", "data": "0322DE00..."}]`` (ISO-TP framed CAN
payload as a hex string), plus the richer per-request ``exchanges`` list.

Two input shapes:

* ONE stream with direction markers (``TX``/``RX``, ``>>``/``<<``, ``->``/``<-``;
  optional ``[12.345]`` timestamp) -- :func:`parse_file`, or ``feed_line``.
* TWO separate raw streams (MES->adapter and adapter->MES) --
  :meth:`MirrorParser.feed` per direction, or :func:`parse_two_files`.

Nothing is dropped silently: lines that match no rule go to ``unparsed`` with a
reason, and ``stats`` counts every category (echo, prompts, SEARCHING..., NO
DATA, BUS INIT, config AT/ST commands, 0x78 pending, frames skipped).

State machine tracked from the tester side: ``ATSH`` / ``ATCP`` / ``ATH`` /
``ATE`` / ``ATS`` / ``ATCAF`` / ``ATSP`` / ``STP`` / ``STPX H:...`` so every
request carries the target address it was sent to. Only 29-bit ``18DA<tt><ss>``
headers become frames (the format ``learn.uds_transactions`` understands);
11-bit and functional (``18DB..``) requests stay in ``exchanges`` and are counted
as ``frames_skipped_*``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from .procedure_capture import SERVICE_NAMES, WRITE_RESET_SERVICES

_HEX = re.compile(r"^[0-9A-F]+$")
_MF_LINE = re.compile(r"^([0-9A-F]):\s*([0-9A-F ]*)$")
_MARK = re.compile(
    r"^\s*(?:\[(\d+(?:\.\d+)?)\]|(\d+\.\d+)(?=\s))?\s*(TX|RX|>>|<<|->|<-)\s*:?\s?(.*)$",
    re.IGNORECASE)
_TX_MARKS = {"TX", ">>", "->"}
_TS = re.compile(r"^\s*(?:\[(\d+(?:\.\d+)?)\]|(\d+\.\d+)(?=\s))\s?(.*)$")

#: Adapter lines that are status, not data. (text prefix -> stat key)
_STATUS_PREFIX = (
    ("SEARCHING", "searching"), ("BUS INIT", "bus_init"), ("NO DATA", "no_data"),
    ("STOPPED", "stopped"), ("UNABLE TO CONNECT", "unable_to_connect"),
    ("CAN ERROR", "can_error"), ("BUS ERROR", "bus_error"), ("BUS BUSY", "bus_busy"),
    ("BUFFER FULL", "buffer_full"), ("<DATA ERROR", "data_error"), ("DATA ERROR", "data_error"),
    ("FB ERROR", "fb_error"), ("LP ALERT", "lp_alert"), ("LV RESET", "lv_reset"),
    ("ACT ALERT", "act_alert"), ("ERROR", "error"), ("?", "unknown_command"),
)
#: A status that means the request failed on the link (not just "the ECU is silent").
_ERROR_KEYS = {"unable_to_connect", "can_error", "bus_error", "bus_busy", "buffer_full",
               "data_error", "fb_error", "error", "unknown_command", "stopped"}

#: ELM/STN protocol token -> id width. ELM facts: ATSP6/7 = ISO 15765-4 11/29-bit 500k,
#: 8/9 = 11/29-bit 250k. STP 33/34 meanings are this repo's own (cuore/live/buses.py:
#: 33 = 11-bit, 34 = 29-bit). Anything else stays "unknown": never guessed.
_PROTOCOL_BITS = {"ATSP6": 11, "ATSP7": 29, "ATSP8": 11, "ATSP9": 29,
                  "STP33": 11, "STP34": 29}


def _hex_bytes(s: str) -> Optional[list[str]]:
    """'22 10 DE' / '2210DE' -> ['22','10','DE']; None if not whole hex bytes."""
    s = s.replace(" ", "")
    if not s or len(s) % 2 or not _HEX.match(s):
        return None
    return [s[i:i + 2] for i in range(0, len(s), 2)]


def _header_info(h: Optional[str], cp: str = "18") -> dict[str, Any]:
    """Classify a header string (3, 6 or 8 hex digits)."""
    info: dict[str, Any] = {"header": h, "id": None, "id_bits": None,
                            "target": None, "tester": None, "functional": False}
    if not h or not _HEX.match(h):
        return info
    if len(h) == 3:
        info.update(id=h, id_bits=11)
    elif len(h) in (6, 8):
        full = (cp + h) if len(h) == 6 else h
        info.update(id=full, id_bits=29)
        if full.startswith("18DA"):
            info.update(target=full[4:6], tester=full[6:8])
        elif full.startswith("18DB"):
            info["functional"] = True
    return info


def _isotp_frames(cid: str, payload: list[str], t: float) -> list[dict[str, Any]]:
    """Segment a UDS payload into the CAN frames a passive listener would have seen."""
    n = len(payload)
    if n <= 7:
        return [{"t": t, "id": cid, "data": f"{n:02X}" + "".join(payload)}]
    out = [{"t": t, "id": cid,
            "data": f"{0x10 | (n >> 8):02X}{n & 0xFF:02X}" + "".join(payload[:6])}]
    rest, seq, k = payload[6:], 1, 1
    while rest:
        out.append({"t": t + k * 0.0001, "id": cid,
                    "data": f"{0x20 | (seq & 15):02X}" + "".join(rest[:7])})
        rest, seq, k = rest[7:], seq + 1, k + 1
    return out


class MirrorParser:
    """Feed it the mirrored stream; read ``exchanges`` / ``unparsed`` / ``stats``."""

    def __init__(self) -> None:
        self.exchanges: list[dict[str, Any]] = []
        self.unparsed: list[dict[str, Any]] = []
        self.stats: dict[str, int] = {}
        self.config_log: list[dict[str, Any]] = []   # ATSH/ATCP/... state changes, in order
        self.info_lines: list[dict[str, Any]] = []   # adapter replies to AT/ST config commands
        # adapter state (ELM defaults: echo on, headers off, spaces on, CAF on)
        self.header: Optional[str] = None
        self.cp = "18"
        self.h_on = False
        self.e_on = True
        self.s_on = True
        self.caf_on = True
        self.protocol: Optional[str] = None
        # parser state
        self._cur: Optional[dict[str, Any]] = None
        self._expect = "none"           # "data" | "info" | "none"
        self._last_cmd = ""
        self._echo_done = True
        self._mf: Optional[dict[str, Any]] = None       # headerless multi-frame assembly
        self._asm: dict[str, dict[str, Any]] = {}       # headered assemblies per source
        self._buf = {"TX": "", "RX": ""}
        self._clock = 0.0
        self._closed = False

    # ------------------------------------------------------------ plumbing
    def _count(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n

    def _t(self, t: Optional[float]) -> float:
        if t is None:
            self._clock += 0.001
            self._count("synthetic_time")
            return self._clock
        self._clock = max(self._clock, t)
        return t

    def _unparsed(self, d: str, t: float, text: str, reason: str) -> None:
        self.unparsed.append({"t": t, "direction": d, "text": text, "reason": reason})
        self._count("unparsed")

    # ------------------------------------------------------------ input
    def feed(self, direction: str, data: "str | bytes", t: Optional[float] = None) -> None:
        """Raw stream chunk. ``direction``: "TX" (MES -> adapter) or "RX" (adapter -> MES).
        Lines end at CR/LF; on RX a ``>`` is a prompt and also ends a line."""
        d = direction.upper()
        if d not in ("TX", "RX"):
            raise ValueError("direction must be 'TX' or 'RX'")
        if isinstance(data, bytes):
            data = data.decode("ascii", errors="replace")
        buf = self._buf[d]
        for ch in data:
            if ch in "\r\n":
                if buf.strip():
                    self.feed_line(d, buf, t)
                buf = ""
            elif ch == ">" and d == "RX":
                if buf.strip():
                    self.feed_line(d, buf, t)
                buf = ""
                self.feed_line(d, ">", t)
            else:
                buf += ch
        self._buf[d] = buf

    def feed_line(self, direction: str, text: str, t: Optional[float] = None) -> None:
        d = direction.upper()
        tt = self._t(t)
        text = text.replace("\x00", "").strip()
        if not text:
            return
        if d == "TX":
            self._tx(tt, text)
        else:
            self._rx(tt, text)

    def close(self) -> "MirrorParser":
        for d in ("TX", "RX"):
            if self._buf[d].strip():
                self.feed_line(d, self._buf[d])
            self._buf[d] = ""
        self._finalize()
        self._closed = True
        return self

    # ------------------------------------------------------------ tester side
    def _tx(self, t: float, text: str) -> None:
        self._finalize()
        c = text.upper().replace(" ", "")
        self._last_cmd, self._echo_done = c, False
        if c.startswith("STPX"):
            self._stpx(t, text)
        elif c.startswith("AT"):
            self._at(t, c)
        elif c.startswith("ST"):
            if re.fullmatch(r"STP\d+", c):
                self.protocol = c
            self._config(t, c, c)
        elif self._tx_hex(c) is not None:
            self._request(t, "raw", self._tx_hex(c), self.header, expect_reply=True)
        else:
            self._expect = "none"
            self._unparsed("TX", t, text, "tester line is not an AT/ST command or hex request")

    @staticmethod
    def _tx_hex(c: str) -> Optional[list[str]]:
        """Hex request; a trailing odd digit is ELM's "expected reply count"."""
        b = _hex_bytes(c)
        if b is None and len(c) % 2 == 1:
            b = _hex_bytes(c[:-1])
        return b

    def _config(self, t: float, c: str, label: str) -> None:
        self._expect = "info"
        self._count("config_commands")
        self.config_log.append({"t": t, "cmd": label})

    def _at(self, t: float, c: str) -> None:
        arg = c[4:]
        if c.startswith("ATSH"):
            self.header = arg if _HEX.match(arg or "x") else None
            if self.header is None:
                self._unparsed("TX", t, c, "ATSH with a non-hex header")
        elif c.startswith("ATCP"):
            self.cp = arg.zfill(2)[-2:] if _HEX.match(arg or "x") else self.cp
        elif c.startswith("ATCAF"):
            self.caf_on = arg != "0"
        elif c.startswith("ATSP") or c.startswith("ATTP"):
            self.protocol = "ATSP" + arg
        elif c in ("ATH1", "ATH0"):
            self.h_on = c == "ATH1"
        elif c in ("ATE1", "ATE0"):
            self.e_on = c == "ATE1"
        elif c in ("ATS1", "ATS0"):
            self.s_on = c == "ATS1"
        elif c in ("ATZ", "ATD", "ATWS"):
            self.header, self.cp, self.h_on, self.e_on, self.s_on, self.caf_on = \
                None, "18", False, True, True, True
        self._config(t, c, c)

    def _stpx(self, t: float, text: str) -> None:
        # STN: STPX H:18DA10F1, D:2210DE, R:1, T:200
        fields = {}
        for part in re.split(r",", text.upper()[4:]):
            m = re.match(r"\s*([HDRT])\s*:\s*(.*?)\s*$", part)
            if m:
                fields[m.group(1)] = m.group(2)
        b = _hex_bytes(fields.get("D", ""))
        if b is None:
            self._expect = "none"
            self._unparsed("TX", t, text, "STPX without parseable D: data")
            return
        h = fields.get("H", "").replace(" ", "") or self.header
        self._request(t, "STPX", b, h, expect_reply=fields.get("R", "1") != "0")

    def _request(self, t: float, via: str, payload: list[str], header: Optional[str],
                 expect_reply: bool) -> None:
        info = _header_info(header, self.cp)
        ex = {"n": len(self.exchanges) + 1, "t": t, "t_resp": None, "via": via,
              "protocol": self.protocol, "request": "".join(payload),
              "service": payload[0], "responses": [], "nrc": None, "pending_78": 0,
              "status": None, "status_lines": [], "flags": [], "expect_reply": expect_reply,
              **info}
        if info["id_bits"] is None:
            ex["flags"].append("no_header")
        if payload[0] == "27":
            ex["flags"].append("security_access")
        if payload[0] in WRITE_RESET_SERVICES:
            ex["flags"].append("write_reset")
        proto = (self.protocol or "").replace(" ", "")
        ex["protocol_id_bits"] = _PROTOCOL_BITS.get(proto)
        self._cur, self._expect = ex, "data"
        self._mf = None
        self._asm = {}

    # ------------------------------------------------------------ adapter side
    def _rx(self, t: float, text: str) -> None:
        if text.startswith(">"):
            self._count("prompts")
            self._finalize()
            rest = text[1:].strip()
            if rest:
                self._rx(t, rest)
            return
        u = text.upper()
        c = u.replace(" ", "")
        if not self._echo_done and c == self._last_cmd:
            self._echo_done = True
            self._count("echo_lines")
            return
        if self._expect == "info":
            self.info_lines.append({"t": t, "text": text})
            self._count("info_lines")
            return
        status = next((k for p, k in _STATUS_PREFIX if u.startswith(p)), None)
        if self._cur is None or self._expect != "data":
            if status:
                self._count(status)       # e.g. SEARCHING... with nothing pending: counted, not lost
                return
            self._unparsed("RX", t, text, "adapter line with no outstanding request")
            return
        ex = self._cur
        if status:
            self._count(status)
            ex["status_lines"].append(text)
            if status in _ERROR_KEYS:
                ex["status"] = f"error: {text}"
            elif status == "bus_init" and "ERROR" in u:
                ex["status"] = f"error: {text}"
            elif status == "no_data" and ex["status"] is None:
                ex["status"] = "no_data"
            return
        if self._data_line(t, u, text):
            return
        self._unparsed("RX", t, text, "unrecognised reply line")

    def _data_line(self, t: float, u: str, raw: str) -> bool:
        ex = self._cur
        assert ex is not None
        c = u.replace(" ", "")
        # headerless multi-frame (CAF on): "014" then "0: ..", "1: .."
        m = _MF_LINE.match(u)
        if m and self._mf is not None:
            b = _hex_bytes(m.group(2))
            if b is None:
                return False
            self._mf["buf"].extend(b)
            if len(self._mf["buf"]) >= self._mf["len"]:
                self._add_payload(self._mf["t"], ex.get("target"), self._mf["buf"][:self._mf["len"]])
                self._mf = None
            return True
        if m and self._mf is None:
            return False
        if not self.h_on and len(c) == 3 and _HEX.match(c):
            self._mf = {"len": int(c, 16), "buf": [], "t": t}
            self._count("multiframe_headerless")
            return True
        headered = self.h_on or c.startswith("18DAF1")
        src = ex.get("target")
        if headered:
            hl = 8 if (c.startswith("18") and len(c) >= 10) else 3
            h, rest = c[:hl], c[hl:]
            if hl == 8 and h.startswith("18DA"):
                src = h[6:8]
            b = _hex_bytes(rest)
            if b is None:
                return False
            return self._framed(t, src or h, b)
        b = _hex_bytes(c)
        if b is None:
            return False
        if int(b[0], 16) < 0x40:
            return self._framed(t, src or "", b)   # PCI byte still present (CAF off)
        self._add_payload(t, src, b)
        return True

    def _framed(self, t: float, src: str, b: list[str]) -> bool:
        """A line that still carries its ISO-TP PCI byte (headers on, or CAF off)."""
        v = int(b[0], 16)
        if v >= 0x40:                       # already a bare payload (CAF stripped it)
            self._add_payload(t, src, b)
            return True
        kind = v >> 4
        if kind == 0:
            n = v & 15
            if n == 0 or len(b) < 1 + n:
                return False
            self._add_payload(t, src, b[1:1 + n])
        elif kind == 1:
            n = ((v & 15) << 8) | int(b[1], 16) if len(b) > 1 else 0
            self._asm[src] = {"len": n, "buf": b[2:], "t": t}
            self._maybe_done(src)
        elif kind == 2:
            a = self._asm.get(src)
            if a is None:
                return False
            a["buf"].extend(b[1:])
            self._maybe_done(src)
        elif kind == 3:
            self._count("flow_control_lines")
        else:
            return False
        return True

    def _maybe_done(self, src: str) -> None:
        a = self._asm[src]
        if len(a["buf"]) >= a["len"]:
            self._add_payload(a["t"], src, a["buf"][:a["len"]])
            del self._asm[src]

    def _add_payload(self, t: float, src: Optional[str], payload: list[str]) -> None:
        ex = self._cur
        assert ex is not None
        if len(payload) >= 3 and payload[0] == "7F" and payload[2] == "78":
            ex["pending_78"] += 1                       # responsePending: not the answer
            self._count("pending_78")
            return
        if payload[0] == "7F" and len(payload) >= 3:
            ex["nrc"] = payload[2]
        ex["responses"].append({"t": t, "source": src, "payload": "".join(payload)})
        if ex["t_resp"] is None:
            ex["t_resp"] = t

    # ------------------------------------------------------------ finalise
    def _finalize(self) -> None:
        ex = self._cur
        if ex is None:
            self._expect = "none"
            return
        if self._mf is not None or self._asm:
            ex["flags"].append("incomplete_multiframe")
            self._count("incomplete_multiframe")
            self._unparsed("RX", ex["t"], ex["request"],
                           "multi-frame reply incomplete when the exchange ended")
        if ex["status"] is None:
            if ex["responses"]:
                ex["status"] = "nrc" if ex["nrc"] and not any(
                    not r["payload"].startswith("7F") for r in ex["responses"]) else "ok"
            elif not ex["expect_reply"]:
                ex["status"] = "no_reply_expected"
            elif ex["pending_78"]:
                ex["status"] = "pending_only"
            else:
                ex["status"] = "unanswered"
        self.exchanges.append(ex)
        self._cur, self._expect, self._mf, self._asm = None, "none", None, {}

    # ------------------------------------------------------------ results
    def flags(self) -> dict[str, Any]:
        ex = self.exchanges
        sec = [e["n"] for e in ex if "security_access" in e["flags"]]
        wr = sorted({e["service"] for e in ex if "write_reset" in e["flags"]})
        return {"security_access": bool(sec), "security_access_exchanges": sec,
                "write_reset_services": wr,
                "services_seen": sorted({e["service"] for e in ex})}


# ===========================================================================
# capture builder
# ===========================================================================

def to_capture(parser: MirrorParser, *, port: str = "serial-mirror", bitrate: int = 500000,
               vin: str = "", mes_port: Optional[str] = None,
               started_at: Optional[str] = None, stopped_at: Optional[str] = None,
               bus: str = "can_c") -> dict[str, Any]:
    """The mes_learn-compatible capture: ``header`` + ``frames`` (+ extras).

    ``frames`` feed ``procedure_capture.review`` / ``gate`` unchanged. The header
    carries the same keys ``mes_learn._header`` writes, plus ``source`` so a
    reader can tell a mirrored capture from a CAN-listen one. ``bitrate`` is what
    the OWNER declares for the bus MES was on (a serial mirror cannot observe it),
    so the gate's bitrate check is only as good as that declaration.
    """
    if not parser._closed:
        parser.close()
    frames: list[dict[str, Any]] = []
    skipped = {"frames_skipped_11bit": 0, "frames_skipped_functional": 0,
               "frames_skipped_no_header": 0, "frames_skipped_other_id": 0}
    for e in parser.exchanges:
        if e["id_bits"] is None:
            skipped["frames_skipped_no_header"] += 1
            continue
        if e["id_bits"] == 11:
            skipped["frames_skipped_11bit"] += 1
            continue
        if e["functional"]:
            skipped["frames_skipped_functional"] += 1
            continue
        if e["target"] is None:
            skipped["frames_skipped_other_id"] += 1
            continue
        tgt, tester = e["target"], e["tester"]
        frames += _isotp_frames(f"18DA{tgt}{tester}", [e["request"][i:i + 2]
                                                      for i in range(0, len(e["request"]), 2)], e["t"])
        for r in e["responses"]:
            p = r["payload"]
            frames += _isotp_frames(f"18DA{tester}{r['source'] or tgt}",
                                    [p[i:i + 2] for i in range(0, len(p), 2)], r["t"])
    frames.sort(key=lambda f: f["t"])
    stats = dict(parser.stats)
    stats.update({k: v for k, v in skipped.items() if v})
    header = {"type": "header", "port": port, "bitrate": bitrate, "bus": bus,
              "mes_port": mes_port, "vin": vin, "started_at": started_at,
              "stopped_at": stopped_at, "source": "serial_mirror"}
    return {"header": header, "frames": frames, "exchanges": parser.exchanges,
            "unparsed": parser.unparsed, "unparsed_count": len(parser.unparsed),
            "stats": stats, "flags": parser.flags(), "config_log": parser.config_log,
            "info_lines": parser.info_lines}


def write_capture(cap: dict[str, Any], path: "str | Path") -> Path:
    """Write ``header`` + frames as JSONL exactly like mes_learn (never overwrites),
    plus a ``.exchanges.json`` sidecar. Caller chooses the path; no default dir."""
    p = Path(path)
    if p.exists():
        raise FileExistsError(f"{p} exists; a capture is never overwritten")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(cap["header"]) + "\n")
        for f in cap["frames"]:
            fh.write(json.dumps({"t": f["t"], "id": f["id"], "data": f["data"]}) + "\n")
    side = p.with_name(p.stem + ".exchanges.json")
    side.write_text(json.dumps({k: cap[k] for k in ("exchanges", "unparsed", "stats", "flags",
                                                      "config_log")}, indent=1), encoding="utf-8")
    return p


# ===========================================================================
# saved logs
# ===========================================================================

def parse_lines(lines: Iterable[str]) -> MirrorParser:
    """One stream with direction markers, e.g. ``[1.250] TX: ATSH 18DA10F1``."""
    p = MirrorParser()
    last_t: Optional[float] = None
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            p._count("comment_lines")
            continue
        m = _MARK.match(line)
        if not m:
            p._unparsed("?", last_t or 0.0, line, "no direction marker")
            continue
        ts = m.group(1) or m.group(2)
        if ts is not None:
            last_t = float(ts)
        d = "TX" if m.group(3).upper() in _TX_MARKS else "RX"
        text = m.group(4)
        if d == "RX":
            p.feed("RX", text + "\r", last_t)   # lets '>' split like the raw stream
        else:
            p.feed_line("TX", text, last_t)
    return p.close()


def parse_file(path: "str | Path") -> MirrorParser:
    """Saved single-stream mirror log (direction-marked lines)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_lines(fh)


def parse_two_files(tx_path: "str | Path", rx_path: "str | Path") -> MirrorParser:
    """Two raw stream logs, each line ``[ts] text``. Merged by time (TX first on ties)."""
    ev: list[tuple[float, int, str, str]] = []
    p = MirrorParser()
    for d, path, rank in (("TX", tx_path, 0), ("RX", rx_path, 1)):
        last = 0.0
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, raw in enumerate(fh):
                line = raw.rstrip("\r\n")
                if not line.strip():
                    continue
                m = _TS.match(line)
                if m:
                    last = float(m.group(1) or m.group(2))
                    line = m.group(3)
                else:
                    p._count("synthetic_time")
                    last += 0.001
                ev.append((last, rank, d, line))
    for t, _, d, line in sorted(ev, key=lambda e: (e[0], e[1])):
        if d == "RX":
            p.feed("RX", line + "\r", t)
        else:
            p.feed_line("TX", line, t)
    return p.close()


def summary_text(cap: dict[str, Any]) -> str:
    """Short human summary, with services named."""
    lines = [f"Serial-mirror capture: {len(cap['exchanges'])} request(s), {len(cap['frames'])} frame(s), "
             f"{cap['unparsed_count']} unparsed line(s)."]
    for e in cap["exchanges"]:
        lines.append(f"  #{e['n']} -> {e['target'] or e['header'] or '?'}: "
                     f"{e['service']} {SERVICE_NAMES.get(e['service'], '?')} [{e['status']}]"
                     + (" 0x27 FLAGGED" if "security_access" in e["flags"] else ""))
    return "\n".join(lines)
