"""Runtime configuration.

Settings come from CLI flags first, then ``CUORE_*`` environment variables,
then these defaults.

Two defaults are deliberate and should not be loosened casually:

* ``host`` binds to loopback. The MCP server this service wraps was a local
  process; this one speaks HTTP, and the moment it binds ``0.0.0.0`` every
  device on the network can read the log corpus -- which contains customer
  VINs. Serving the shop LAN is a normal thing to want, but it should be a
  decision someone typed, not the default.
* ``token`` is empty, which disables auth. Combined with loopback that is
  safe. Set it whenever ``host`` is widened.

Log-corpus locations are *not* configured here. They belong to ``mes.paths``
and are driven by ``MES_LOG_DIR`` / ``MES_LOG_DIRS`` / ``MES_CSV_DIR`` /
``MES_CSV_DIRS``; duplicating them would create two answers to one question.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .profiles import Profile


class Settings(BaseSettings):
    """Everything the server needs to start."""

    model_config = SettingsConfigDict(
        env_prefix="CUORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    profile: Profile = Field(
        default=Profile.BENCH,
        description="Which half of the system this process is.",
    )
    host: str = Field(
        default="127.0.0.1",
        description="Bind address. Use 0.0.0.0 to serve the LAN -- set a "
                    "token as well when you do.",
    )
    port: int = Field(default=5000, ge=1, le=65535)
    token: str = Field(
        default="",
        description="Optional shared secret. When set, every request must "
                    "carry it as X-Cuore-Token or ?token=.",
    )
    reload: bool = Field(
        default=False,
        description="Development autoreload. Never enable on the drive node.",
    )

    @property
    def lan_exposed(self) -> bool:
        """True when this bind address is reachable from another machine."""
        return self.host not in ("127.0.0.1", "localhost", "::1")

    @property
    def unguarded_lan(self) -> bool:
        """Exposed to the network with no token -- worth warning about."""
        return self.lan_exposed and not self.token.strip()


def load(**overrides: object) -> Settings:
    """Build settings, with CLI overrides winning over the environment.

    ``None`` values are dropped so an unset CLI flag falls through to the
    environment rather than clobbering it with a null.
    """
    clean = {k: v for k, v in overrides.items() if v is not None}
    return Settings(**clean)  # type: ignore[arg-type]
