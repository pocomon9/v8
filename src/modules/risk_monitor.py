import logging
import re

log = logging.getLogger('poco.modules.risk_monitor')

RISK_PATTERNS = [
    r'\b(kill|murder|assassinate|bomb|attack|genocide)\b',
    r'\b(you should die|kys|go kill yourself)\b',
]

class RiskMonitor:
    """Pre-flight safety check that scans drafts for high-risk content."""

    def check_risk(self, text: str) -> bool:
        """Return True if text is safe to post; False if it trips a risk pattern."""
        text_lower = text.lower()
        for pattern in RISK_PATTERNS:
            if re.search(pattern, text_lower):
                log.warning(f'RiskMonitor: BLOCKED — matched high-risk pattern: {pattern!r}')
                return False
        return True
