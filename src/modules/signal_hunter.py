import logging

log = logging.getLogger('poco.modules.signal_hunter')

class SignalHunter:
    """Wraps the engine trend research to find emerging, under-covered narratives."""
    def __init__(self, engine=None):
        self.engine = engine

    def hunt_emerging_narratives(self, hints=None):
        """Hunt for emerging narratives. hints dict may contain optional keywords."""
        log.info('SignalHunter: Scanning for emerging under-covered narratives.')
        if self.engine and hasattr(self.engine, 'research_trends'):
            try:
                return self.engine.research_trends()
            except Exception as e:
                log.warning(f'SignalHunter: research_trends failed: {e}')
                return []
        return []
