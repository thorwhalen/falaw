# falaw.bridges.service

HTTP service bridge (planned): expose falaw tools as a `qh` app.

The plan: feed `falaw.registry.list_tools()` callables to `qh.mk_app` so
each tool becomes an HTTP endpoint. Same SSOT, new surface — no rewrite
of the operations themselves.

### Functions

| `build_qh_app`(\*args, \*\*kwargs)   |    |
|--------------------------------------|----|
