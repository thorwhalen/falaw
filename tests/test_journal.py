from falaw.journal import Journal


def test_journal_append_iter(tmp_path):
    j = Journal(str(tmp_path))
    j.append(kind="note", text="hello")
    j.append(kind="issue", text="boom", suggestion="try X", tags=("flux",))
    entries = list(j)
    assert [e.kind for e in entries] == ["note", "issue"]
    assert entries[1].suggestion == "try X"
    assert "flux" in entries[1].tags


def test_journal_filter_and_recent(tmp_path):
    j = Journal(str(tmp_path))
    for i in range(5):
        j.append(kind="note", text=f"n{i}", tags=("a",) if i % 2 == 0 else ("b",))
    assert len(j.recent(3)) == 3
    assert len(j.filter(tag="a")) == 3
    assert len(j.filter(kind="note")) == 5


def test_appends_within_one_clock_tick_keep_insertion_order(tmp_path, monkeypatch):
    """falaw#25: on Windows `time.time_ns()` advances in coarse ticks, so
    back-to-back appends can share a timestamp — and the filename then fell
    back to UUID order, i.e. random. Freezing the clock reproduces the
    Windows tie deterministically on every platform; the sequence counter
    must keep insertion order anyway.

    20 entries make an accidental pass under UUID ordering a 1-in-20!
    event, so this cannot go green by luck.
    """
    from falaw import journal as journal_module

    monkeypatch.setattr(
        journal_module.time, "time_ns", lambda: 1_755_000_000_000_000_000
    )
    j = Journal(str(tmp_path))
    texts = [f"entry-{i:02d}" for i in range(20)]
    for text in texts:
        j.append(kind="note", text=text)
    assert [e.text for e in j] == texts
