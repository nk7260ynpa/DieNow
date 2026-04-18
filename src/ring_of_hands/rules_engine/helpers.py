"""Rules Engine 共用工具函式."""

from __future__ import annotations

from ring_of_hands.world_model.types import Coord


def chebyshev_distance(a: Coord, b: Coord) -> int:
    """回傳兩座標的 Chebyshev 距離."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def in_bounds(coord: Coord, room_size: Coord) -> bool:
    """回傳座標是否落在房間內."""
    x, y = coord
    w, h = room_size
    return 0 <= x < w and 0 <= y < h


__all__ = ["chebyshev_distance", "in_bounds"]
