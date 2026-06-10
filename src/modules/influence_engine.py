import logging
import json
from datetime import datetime

log = logging.getLogger('poco.modules.influence_engine')

INFLUENCE_SLOT = 'vault.influence'

class InfluenceEngine:
    """Tracks which accounts react and which writing styles perform best."""

    def __init__(self, memory=None):
        self.memory = memory

    def track_reaction(self, account_handle: str, style_tags: list, post_content: str = ''):
        """Record that a specific account reacted to a post with style metadata."""
        log.info(f'InfluenceEngine: Tracking reaction from @{account_handle}')
        if not self.memory:
            return
        try:
            slot = self.memory.get_working_memory(INFLUENCE_SLOT)
            raw = slot.get('content', '[]') if isinstance(slot, dict) else '[]'
            records = json.loads(raw) if raw else []
            records.append({
                'handle': account_handle,
                'tags': style_tags,
                'preview': post_content[:100],
                'ts': datetime.utcnow().isoformat()
            })
            self.memory.set_working_memory(INFLUENCE_SLOT, json.dumps(records[-200:]), {})
        except Exception as e:
            log.warning(f'InfluenceEngine: track_reaction failed: {e}')
