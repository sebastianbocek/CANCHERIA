from cancheria.infrastructure.persistence.json_store import JSONStore

def test_json_store_roundtrip(tmp_path):
    store=JSONStore(tmp_path/"state.json")
    assert store.read({}) == {}
    store.write({"ok": True})
    assert store.read({}) == {"ok": True}
