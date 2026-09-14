"""Deployment profiles and the capability matrix they imply.

The capability contract is the seam the whole design hangs on. A client asks
one question -- "what can this host do?" -- and renders against the answer.
That is what lets the bench host and the in-car node serve the *same* bundle,
and what makes the live paths additive later: P2 and P3 flip booleans here
rather than restructuring anything.

Every feature is listed on every profile, including the ones that are off.
A missing key would force clients to distinguish "not supported" from "older
host that never heard of this feature"; an explicit ``False`` does not.
"""

from __future__ import annotations

from enum import Enum


class Profile(str, Enum):
    """Where this process is running, and therefore what it owns."""

    BENCH = "bench"
    DRIVE = "drive"


#: Every capability the client may branch on. Keep this list closed: a feature
#: that is not here cannot be advertised, which keeps the contract honest.
FEATURES: tuple[str, ...] = (
    "corpus",          # MES log corpus is present and indexable
    "workup",          # the pre-work dossier
    "fault_tree",      # FIM-style isolation sequences
    "verdict",         # the evidence gate
    "modules",         # module registry / bus map
    "recordings",      # MES CSV recordings
    "log_read",        # verbatim log read, containment-checked
    "live_obd",        # live OBD-II link                     (P2)
    "live_can",        # CAN sniffing with the Giorgio DBC    (P6)
    "drive_recorder",  # continuous drive logging             (P3)
    "actuators",       # bidirectional writes                 (P2+, gated)
)


_BENCH: dict[str, bool] = {
    "corpus": True,
    "workup": True,
    "fault_tree": True,
    "verdict": True,
    "modules": True,
    "recordings": True,
    "log_read": True,
    "live_obd": True,       # lowered at runtime when no port resolves or MES holds it
    "live_can": True,       # passive capture; lowered with live_obd
    "drive_recorder": False,
    "actuators": False,     # stays False: the live layer has no write path
}

# The drive node carries no log corpus -- it holds recordings it made itself and
# syncs them back to the bench host, which stays the system of record. Its live
# features are False until P3 builds them; the profile exists now so the
# contract does not change shape when they arrive.
_DRIVE: dict[str, bool] = {
    "corpus": False,
    "workup": False,
    "fault_tree": False,
    "verdict": False,
    "modules": True,       # the registry is static data, it travels fine
    "recordings": True,
    "log_read": False,
    "live_obd": False,
    "live_can": False,
    "drive_recorder": False,
    "actuators": False,
}

_MATRIX: dict[Profile, dict[str, bool]] = {
    Profile.BENCH: _BENCH,
    Profile.DRIVE: _DRIVE,
}


def features_for(profile: Profile) -> dict[str, bool]:
    """The capability map for a profile, as a fresh dict.

    Returned by value so a caller that overlays runtime state -- an adapter
    that turned out to be present, a corpus root that does not exist -- cannot
    mutate the matrix for everyone else.
    """
    base = _MATRIX[profile]
    return {name: base.get(name, False) for name in FEATURES}
