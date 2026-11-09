"""Versioned, process-independent seeds and component-owned random streams."""

import hashlib
import json
import random


def derive_seed(seed: int, *components: str) -> int:
    """Derive a stable 64-bit seed without Python's process-randomized hash()."""
    payload = json.dumps(
        ["fedsim-rng-v1", int(seed), *components], ensure_ascii=False, separators=(",", ":")
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


class RandomStreams:
    """Keep independent advancing streams for an actor's named components."""

    def __init__(self, seed: int | None, *namespace: str):
        self.seed = seed
        self.namespace = namespace
        self._streams: dict[tuple[str, ...], random.Random] = {}

    def stream(self, *components: str) -> random.Random:
        if components not in self._streams:
            stream_seed = (
                None if self.seed is None else derive_seed(self.seed, *self.namespace, *components)
            )
            self._streams[components] = random.Random(stream_seed)
        return self._streams[components]
