"""
Helpers pour la collecte des métriques Fronius.
Les définitions et la logique de collecte sont dans collector.py.
"""

from typing import Any


def safe_float(obj: Any, default: float = 0.0) -> float:
    """Extrait une valeur numérique depuis un champ API (scalar ou {Value: x})."""
    if obj is None:
        return default
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, dict) and "Value" in obj:
        return safe_float(obj["Value"], default)
    return default
