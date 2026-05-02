"""HTTP service bridge (planned): expose pyfal tools as a `qh` app.

The plan: feed `pyfal.registry.list_tools()` callables to `qh.mk_app` so
each tool becomes an HTTP endpoint. Same SSOT, new surface --- no rewrite
of the operations themselves.
"""

from __future__ import annotations


def build_qh_app(*args, **kwargs):
    raise NotImplementedError(
        "Service bridge not yet implemented. Plan: collect callables from "
        "`pyfal.registry.list_tools()` and pass them to `qh.mk_app`. See "
        "`bridges/skill.py` for the same SSOT-to-surface pattern."
    )
