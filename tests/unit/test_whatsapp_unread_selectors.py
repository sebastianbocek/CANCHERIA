from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_unread_filter_never_clicks_an_arbitrary_label_item():
    text = (ROOT / "legacy" / "WPSetter_legacy.py").read_text(encoding="utf-8")
    function = text.split("async def click_no_leidos(page):", 1)[1].split(
        "async def click_first_chat(page):", 1
    )[0]
    assert "button[contains(@id, 'label_item')]" not in function
    assert "button[aria-label='No leídos']" in function
    assert "chat-list-filter-unread" in function


def test_chat_picker_prefers_semantic_rows_scoped_to_sidebar():
    text = (ROOT / "legacy" / "WPSetter_legacy.py").read_text(encoding="utf-8")
    assert '"#pane-side div[role=\'listitem\']"' in text
    assert '"#pane-side div[role=\'row\']"' in text
    assert "icon-unread-count" in text
