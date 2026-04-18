"""攜手之戒關卡 CLI 入口骨架.

提供 `python -m ring_of_hands.cli run --config <path>` 指令. 實作細節於
Task 8.4 填入; 此檔案於 Task 1.1 先建立 entrypoint 骨架以便 `pyproject.toml`
的 console script 指向它.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口.

    Args:
        argv: 命令列參數清單. 若為 `None` 則使用 `sys.argv[1:]`.

    Returns:
        進程退出碼. `0` 表示成功.
    """
    # Task 8.4 會填入實際邏輯; 此處僅為骨架讓 `pyproject.toml` 的 script 可以
    # 指向. 以下 late import 避免在 Task 1 階段就要求其他模組存在.
    from ring_of_hands.scenario_runner.cli_main import cli_main  # noqa: PLC0415

    return cli_main(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
