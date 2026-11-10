"""Configuration for the Magicbricks Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT               port the API listens on (default 8000)
    MAGICBRICKS_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                       (default: none — direct). magicbricks.com sits behind
                       Akamai, which refuses most datacenter IPs. Your own home
                       or office connection in India works as is; on a cloud
                       server, set an Indian residential proxy here so every
                       retry after a block leaves through a fresh IP.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# After a block, a worker thread keeps using a fresh session for this long
# before trying its first connection again.
MAGICBRICKS_BLOCK_HOLD_S = 600

MAGICBRICKS_PROXY = os.environ.get("MAGICBRICKS_PROXY") or None


def magicbricks_proxy():
    """The proxy for one curl session (None = direct)."""
    return os.environ.get("MAGICBRICKS_PROXY") or None


def magicbricks_fallback_proxy():
    """The proxy for the session a thread uses right after a block (the same
    MAGICBRICKS_PROXY: a rotating proxy hands the new session a new IP)."""
    return os.environ.get("MAGICBRICKS_PROXY") or None
