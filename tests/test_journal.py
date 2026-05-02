from falai.journal import Journal


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
