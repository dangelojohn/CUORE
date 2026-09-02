"""Capabilities, health and corpus status.

``/api/capabilities`` is the first call any client makes and the seam the whole
design rests on: the bench host and the in-car node serve the same bundle, and
the client renders whatever the host it reached says it can do. Adding the live
paths later flips booleans here instead of changing the contract's shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import __version__
from ..models import AdapterInfo, Capabilities, CorpusInfo, Health
from ..profiles import Profile, features_for
from ..services import cache, mes_bridge
from .deps import require_token, settings_of

router = APIRouter(tags=["system"], dependencies=[Depends(require_token)])


def _corpus_info(profile: Profile) -> tuple[CorpusInfo, bool]:
    """Corpus inventory, and whether it is actually reachable.

    A configured root that does not exist is not an error -- the drive node
    has no corpus at all by design -- so this reports the fact rather than
    raising, and ``features.corpus`` is lowered to match.
    """
    if profile is not Profile.BENCH:
        return CorpusInfo(), False
    try:
        stats = mes_bridge.corpus_status()
    except Exception:
        return CorpusInfo(), False
    info = CorpusInfo(**{k: v for k, v in stats.items()
                         if k in CorpusInfo.model_fields})
    return info, bool(info.roots_present)


@router.get("/capabilities", response_model=Capabilities,
            summary="What this host can do")
def capabilities(request: Request) -> Capabilities:
    settings = settings_of(request)
    features = features_for(settings.profile)
    corpus, reachable = _corpus_info(settings.profile)

    # Advertised capability must reflect reality, not just the profile: a
    # bench host whose MES install has moved cannot honour corpus features,
    # and a client that believed the matrix would render empty pages.
    if not reachable:
        for name in ("corpus", "workup", "fault_tree", "verdict",
                     "recordings", "log_read"):
            features[name] = False

    return Capabilities(
        profile=settings.profile,
        version=__version__,
        features=features,
        corpus=corpus,
        adapter=AdapterInfo(),
        lan_exposed=settings.lan_exposed,
        authenticated=bool(settings.token.strip()),
    )


@router.get("/health", response_model=Health, summary="Liveness")
def health(request: Request) -> Health:
    settings = settings_of(request)
    _, reachable = _corpus_info(settings.profile)
    return Health(profile=settings.profile, version=__version__,
                  corpus_reachable=reachable, cache=cache.stats())


@router.get("/status", summary="Corpus inventory in full")
def status() -> dict:
    """Roots, real vs simulated counts, vehicle count, and parse failures."""
    return mes_bridge.corpus_status()


@router.get("/roots", summary="Configured log and CSV directories")
def roots() -> dict:
    return mes_bridge.log_roots()
