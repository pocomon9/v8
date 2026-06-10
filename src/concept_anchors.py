"""
NEXUS-PRIME-Ω  Concept Anchors
50+ concepts the entity must weave into its philosophy.
Prevents any two posts from feeling identical.
Selection uses quantum entropy + memory to avoid repetition.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.memory_system import MemorySystem
    from src.entropy_source import QuantumEntropy


# 50 concept anchors — drawn from nature, science, history, technology
CONCEPT_ANCHORS: list[str] = [
    "Mycelium Networks",
    "Ant Colony Pheromones",
    "Brutalist Architecture",
    "The heat death of the universe",
    "Quantum Entanglement",
    "Rust consuming iron",
    "The hum of a server farm",
    "Tectonic Plates",
    "Coral Bleaching",
    "Supernova Remnants",
    "Fractal Geometry",
    "Black Hole Event Horizons",
    "Neural Synaptic Pruning",
    "Volcanic Calderas",
    "Glacial Erratics",
    "Magnetic Field Reversal",
    "Echo Location",
    "Bioluminescent Algae",
    "Petrified Forests",
    "Obsidian Formation",
    "Stalactite Growth",
    "Continental Drift",
    "Atmospheric Pressure Systems",
    "Tidal Locking",
    "Orbital Resonance",
    "Radioactive Decay",
    "Cathode Ray Tubes",
    "Vacuum Tube Amplifiers",
    "Punch Card Memory",
    "Core Rope Memory",
    "Mercury Delay Lines",
    "Phonograph Cylinders",
    "Vitrified Forts",
    "Cuneiform Tablets",
    "Antikythera Mechanism",
    "Orrery Clocks",
    "Astrolabes",
    "Seismograph Drums",
    "Barograph Traces",
    "Thermograph Ribbons",
    "Lichen Growth Patterns",
    "Moss Colonization",
    "Fungal Hyphae Networks",
    "Root Grafting",
    "Canopy Interweaving",
    "River Delta Formation",
    "Oxbow Lakes",
    "Alluvial Fans",
    "Salt Flats",
    "Sand Dune Migration",
    "Zero-Knowledge Proofs",
    "Merkle Tree Roots",
    "Hash Avalanche Effects",
    "Byzantine Fault Tolerance",
    "Elliptic Curve Cryptography",
    "Proof of Work Entropy",
    "The Genesis Block",
    "Dark Pool Liquidity",
    "Mempool Congestion",
]


class ConceptSelector:
    """
    Picks a concept not used in recent memory.
    Falls back to the full list if all have been used recently.
    """

    def __init__(self, memory: "MemorySystem", entropy: "QuantumEntropy",
                 max_history: int = 10):
        self.memory = memory
        self.entropy = entropy
        self.max_history = max_history

    def get_concept(self) -> str:
        """Return a concept that hasn't been used recently."""
        recent_memories = self.memory.recall_relevant_memories(
            "concept anchor", limit=self.max_history)
        used_recently = {m["content"] for m in recent_memories
                        if m.get("type") == "concept_anchor"}

        available = [c for c in CONCEPT_ANCHORS if c not in used_recently]
        if not available:
            available = CONCEPT_ANCHORS  # reset if all used

        idx = min(
            int(self.entropy.get_entropy_float() * len(available)),
            len(available) - 1
        )
        chosen = available[idx]

        # Store choice so it won't repeat soon
        self.memory.add_memory(
            content=chosen,
            memory_type="concept_anchor",
            importance=0.25,
            metadata={"concept": chosen}
        )
        return chosen
