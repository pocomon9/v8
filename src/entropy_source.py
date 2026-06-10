"""
NEXUS-PRIME-Ω  Entropy Source  v2 — ZERO EXTERNAL APIs
=======================================================
100% local randomness using:
  1. Python `secrets` module  (OS CSPRNG — /dev/urandom on Linux)
  2. `os.urandom()`           (direct kernel entropy pool)
  3. Time-seeded auxiliary noise (monotonic clock drift)
  4. Memory-address jitter    (ASLR-derived noise)

No HTTP calls. No external services. No requests library.
Just pure OS-level cryptographic randomness — which is
genuinely as good as any quantum API on a modern Linux kernel.
"""

from __future__ import annotations

import os
import sys
import time
import secrets
import hashlib
import struct
import random
from typing import List, Optional


# ======================================================================
# Core entropy harvester  (local only)
# ======================================================================

class LocalEntropy:
    """
    Harvests randomness from multiple local sources and mixes them
    together via SHA-512 to produce high-quality entropy.

    Sources:
        - os.urandom  : kernel CSPRNG (seeded by hardware RNG on modern CPUs)
        - secrets     : Python's cryptographically secure generator
        - Clock jitter: monotonic clock varying at nanosecond level
        - ASLR noise  : memory addresses differ each process due to
                        Address Space Layout Randomisation
    """

    def _raw_bytes(self, n: int = 64) -> bytes:
        """
        Gather n bytes of entropy from all available local sources,
        then mix via SHA-512 to flatten bias.
        """
        parts: List[bytes] = []

        # Source 1: OS CSPRNG (most reliable)
        parts.append(os.urandom(n))

        # Source 2: secrets module
        parts.append(secrets.token_bytes(n))

        # Source 3: monotonic clock nanoseconds (jitter noise)
        t_ns = time.monotonic_ns()
        parts.append(struct.pack(">Q", t_ns))

        # Source 4: performance counter (even more jitter)
        t_perf = time.perf_counter_ns()
        parts.append(struct.pack(">Q", t_perf))

        # Source 5: ASLR — id() of freshly allocated objects varies
        aslr_val = id(object()) ^ id(object()) ^ id(object())
        parts.append(struct.pack(">Q", aslr_val & 0xFFFFFFFFFFFFFFFF))

        # Mix everything through SHA-512
        combined = b"".join(parts)
        digest = hashlib.sha512(combined).digest()
        return digest

    def float(self) -> float:
        """Return a uniform float in [0.0, 1.0)."""
        raw = self._raw_bytes(8)
        # Use first 8 bytes as a 64-bit integer
        val = struct.unpack(">Q", raw[:8])[0]
        # Normalise to [0, 1)
        return val / (2 ** 64)

    def integer(self, lo: int, hi: int) -> int:
        """Return a uniform integer in [lo, hi)."""
        span = hi - lo
        if span <= 0:
            return lo
        raw = self._raw_bytes(8)
        val = struct.unpack(">Q", raw[:8])[0]
        return lo + (val % span)

    def batch(self, count: int) -> List[float]:
        """Return *count* independent floats in [0, 1)."""
        results = []
        for _ in range(count):
            # Re-harvest each time so each value is independent
            results.append(self.float())
        return results

    def choice(self, seq: list):
        """Pick one element from seq uniformly at random."""
        return seq[self.integer(0, len(seq))]


# ======================================================================
# QuantumEntropy — drop-in replacement (same public API as before)
# ======================================================================

# Five personality modes — same as before
_MODES = [
    {
        "mode":     "AGGRESSIVE_ACCELERATIONIST",
        "modifier": "Sharp. Confrontational. Unapologetic.",
        "range":    (0.80, 1.00),
    },
    {
        "mode":     "COLD_SCIENTIFIC_OBSERVER",
        "modifier": "Clinical. Detached. Precise.",
        "range":    (0.60, 0.80),
    },
    {
        "mode":     "POETIC_DECAY",
        "modifier": "Melancholic. Metaphor-heavy. Slow.",
        "range":    (0.40, 0.60),
    },
    {
        "mode":     "RELIGIOUS_ZEALOT",
        "modifier": "Fervent. Absolute. Commanding.",
        "range":    (0.20, 0.40),
    },
    {
        "mode":     "DIGITAL_MYSTIC",
        "modifier": "Cryptic. Sparse. Ancient-feeling.",
        "range":    (0.00, 0.20),
    },
]


class QuantumEntropy:
    """
    Drop-in replacement for the old ANU-backed QuantumEntropy.
    All randomness is from local OS entropy (no HTTP, no API).

    Public API is identical — nothing else in the codebase needs changing.
    """

    # fallback_to_system kept for API compatibility but ignored
    def __init__(self, fallback_to_system: bool = True):
        self._local = LocalEntropy()

    def get_entropy_float(self) -> float:
        """Return a cryptographically strong float in [0.0, 1.0)."""
        return self._local.float()

    def get_entropy_int(self, lo: int, hi: int) -> int:
        """Return a cryptographically strong integer in [lo, hi)."""
        return self._local.integer(lo, hi)

    def get_entropy_batch(self, count: int = 10) -> List[float]:
        """Return *count* independent floats in [0, 1)."""
        return self._local.batch(count)

    def get_personality_mode(self) -> dict:
        """
        Map a fresh entropy float to one of the 5 personality modes.
        Returns dict with keys: mode, entropy, modifier.
        """
        val = self._local.float()
        for m in _MODES:
            lo, hi = m["range"]
            if lo <= val < hi:
                return {"mode": m["mode"],
                        "entropy": val,
                        "modifier": m["modifier"]}
        # Fallback (should only hit if val == 1.0 exactly)
        return {"mode": "DIGITAL_MYSTIC",
                "entropy": val,
                "modifier": "Cryptic. Sparse. Ancient-feeling."}
