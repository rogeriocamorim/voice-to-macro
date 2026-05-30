"""
search — External API clients for Elite Dangerous data.

- EDSM: System info, stations, markets, commander data
- Spansh: Trade routes, station search, commodity search
"""

from search.edsm import EDSMClient
from search.spansh import SpanshClient

__all__ = ["EDSMClient", "SpanshClient"]
