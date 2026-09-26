"""Request and response models.

Deliberately few. The analysis payloads -- a workup dossier, a fault tree, a
DTC history -- are shaped by the :mod:`mes` library and evolve with it; wrapping
each in a Pydantic mirror would create a second definition to keep in step, and
the mirror would silently drop any field the library added. Those endpoints
return the library's dict as-is.

What *is* modelled here is the contract CUORE itself owns: the capability
document a client branches on, the health payload, the error body, and the
evidence-gate submission -- the one request with real user input in it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .profiles import Profile


class CorpusInfo(BaseModel):
    """Inventory of the MES log corpus this host can see."""

    roots: list[str] = Field(default_factory=list)
    roots_present: list[str] = Field(default_factory=list)
    total_logs: int = 0
    real_logs: int = 0
    simulated_logs: int = 0
    fes_logs: int = 0
    scan_logs: int = 0
    vehicles: int = 0
    oldest: str | None = None
    newest: str | None = None
    parse_errors: list[Any] = Field(default_factory=list)


class AdapterInfo(BaseModel):
    """State of the OBD-II link, as the live layer reports it.

    ``present`` means the next live call would be able to open the port: a
    port resolved, MES is not connected, and no other process holds the lock.
    ``blocked_by`` says who has it otherwise. The port is never held between
    calls, so there is no "connected" state to report.
    """

    present: bool = False
    port: str | None = None
    blocked_by: str | None = None
    note: str = "port opened per operation"


class Capabilities(BaseModel):
    """The document every client fetches first.

    A client never assumes which host it reached; it renders against this.
    Both profiles list every feature, including the ones set ``False``, so
    "unsupported" is never confused with "older host that never heard of it".
    """

    profile: Profile
    version: str
    features: dict[str, bool]
    corpus: CorpusInfo
    adapter: AdapterInfo
    lan_exposed: bool = False
    authenticated: bool = False


class Health(BaseModel):
    """Liveness plus the two things worth knowing at a glance."""

    ok: bool = True
    profile: Profile
    version: str
    corpus_reachable: bool
    cache: dict[str, Any] = Field(default_factory=dict)


class ErrorBody(BaseModel):
    """Uniform failure shape, so clients parse one thing."""

    error: str
    detail: str
    status: int


MeasurementType = Literal["actuator", "freeze_frame", "parameter",
                          "recording_event", "manual", "live", "note"]


class Measurement(BaseModel):
    """One evidence citation offered to the gate.

    Which fields matter depends on ``type``; the library verifies each against
    the corpus and reports whether it could be confirmed, so extra or missing
    fields degrade into "unverified" rather than an error.
    """

    type: MeasurementType
    operation: str | None = None      # actuator
    code: str | None = None           # freeze_frame
    name: str | None = None           # parameter
    file: str | None = None           # parameter / recording_event
    condition: str | None = None      # recording_event
    description: str | None = None    # manual
    kind: str | None = None           # live: dtc | permanent | readiness | module_dtc | did
    monitor: str | None = None        # live readiness
    ecu: str | None = None            # live did
    did: str | None = None            # live did
    id: str | None = None             # note: the technician note's id


class VerdictRequest(BaseModel):
    """A proposed diagnosis, submitted for gating.

    Nothing here reaches the car. The gate reads the corpus and answers one
    question: has this diagnosis been *demonstrated*, or is it a guess wearing
    a diagnosis's clothes.
    """

    codes: str = Field(..., description="One or more DTCs, comma or space separated.")
    component: str = Field(default="", description="The part being accused.")
    mechanism: str = Field(
        default="",
        description="The causal chain in a sentence -- 'X failed in way Y, "
                    "producing symptom Z'. A part name alone does not pass.")
    measurements: list[Measurement] = Field(default_factory=list)
    disconfirming_test: str = Field(
        default="",
        description="The test that would have exonerated the part, and its "
                    "result.")
