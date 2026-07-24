from __future__ import annotations

import random
import re
from typing import Optional

# Deliberately excludes plain {placeholder} (no pipe) -- that's render_template()'s job.
_SPINTAX_RE = re.compile(r"\{([^{}]*\|[^{}]*)\}")

_MAX_PASSES = 50  # guards against pathological/malformed input looping forever


def resolve_spintax(text: str, rng: Optional[random.Random] = None) -> str:
    """Resolves every {a|b|c} group to one random choice; repeats inside-out so nested groups like {a|{b|c}} resolve correctly."""
    chooser = rng.choice if rng is not None else random.choice

    def _replace(match: "re.Match[str]") -> str:
        return chooser(match.group(1).split("|"))

    resolved = text
    for _ in range(_MAX_PASSES):
        new_resolved = _SPINTAX_RE.sub(_replace, resolved)
        if new_resolved == resolved:
            break
        resolved = new_resolved
    return resolved
