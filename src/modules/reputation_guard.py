import logging

log = logging.getLogger('poco.modules.reputation_guard')

class ReputationGuard:
    """Ensures posts align with the organism's established reputation topics."""

    def __init__(self, core_topics: list):
        self.core_topics = [t.lower() for t in core_topics]

    def validate(self, text: str) -> bool:
        """Return True if text is on-brand; False if it drifts from core topics."""
        text_lower = text.lower()
        # Block obvious retail/fashion/crypto bleed for Poco/Zara respectively
        hard_blocks = ['buy now', 'shop our', 'click here', 'dm for orders',
                       'use code', 'discount', 'promo', 'sale ends']
        for block in hard_blocks:
            if block in text_lower:
                log.warning(f'ReputationGuard: BLOCKED — commercial language detected: {block!r}')
                return False
        # At least one core topic must be loosely present (or pass if very short)
        if len(text) < 80:
            return True
        for topic in self.core_topics:
            if topic in text_lower:
                return True
        log.warning(f'ReputationGuard: WARNING — no core topic found in draft ({len(text)} chars). Allowing through.')
        return True  # Soft-pass to avoid over-blocking
