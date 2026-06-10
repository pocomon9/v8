import logging
import json
from datetime import datetime, timedelta

log = logging.getLogger('poco.modules.memory_vault')

class MemoryVault:
    """Persistent prediction and discovery layer using the existing MemorySystem."""

    PREDICTION_SLOT = 'vault.predictions'

    def __init__(self, base_memory):
        self.memory = base_memory

    def _load_predictions(self):
        try:
            slot = self.memory.get_working_memory(self.PREDICTION_SLOT)
            raw = slot.get('content', '[]') if isinstance(slot, dict) else '[]'
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def _save_predictions(self, predictions):
        try:
            self.memory.set_working_memory(
                self.PREDICTION_SLOT,
                json.dumps(predictions),
                {'updated': datetime.utcnow().isoformat()}
            )
        except Exception as e:
            log.warning(f'MemoryVault: failed to save predictions: {e}')

    def store_prediction(self, thesis: str, timeframe_days: int):
        """Store a new prediction thesis with a target resolution timeframe."""
        log.info(f'MemoryVault: Storing prediction: {thesis[:80]}')
        predictions = self._load_predictions()
        predictions.append({
            'thesis': thesis,
            'date': datetime.utcnow().isoformat(),
            'timeframe_days': timeframe_days,
            'status': 'pending'
        })
        self._save_predictions(predictions[-50:])

    def review_predictions(self):
        """Return all pending predictions whose resolution window may have passed."""
        log.info('MemoryVault: Reviewing past predictions for continuity follow-ups.')
        predictions = self._load_predictions()
        due = []
        now = datetime.utcnow()
        for p in predictions:
            if p.get('status') != 'pending':
                continue
            try:
                created = datetime.fromisoformat(p['date'])
                delta = timedelta(days=p.get('timeframe_days', 30))
                if now >= created + delta:
                    due.append(p)
            except Exception:
                pass
        return due

    def mark_prediction_resolved(self, thesis: str):
        """Mark a prediction as resolved so it stops appearing in reviews."""
        predictions = self._load_predictions()
        for p in predictions:
            if p.get('thesis') == thesis:
                p['status'] = 'resolved'
        self._save_predictions(predictions)
