from nobrokerhood.utils import pick_fields


def test_returns_data_unchanged_when_fields_is_none():
    data = {"a": 1, "b": 2}
    assert pick_fields(data, None) is data


def test_returns_data_unchanged_when_fields_is_empty():
    data = {"a": 1, "b": 2}
    assert pick_fields(data, []) is data


def test_picks_top_level_field():
    data = {"a": 1, "b": 2, "c": 3}
    assert pick_fields(data, ["a", "c"]) == {"a": 1, "c": 3}


def test_picks_nested_field():
    data = {"data": {"user": {"name": "Alice", "age": 30}}}
    expected = {"data": {"user": {"name": "Alice"}}}
    assert pick_fields(data, ["data.user.name"]) == expected


def test_picks_multiple_nested_fields_with_shared_prefix():
    data = {"data": {"user": {"name": "Alice", "age": 30, "email": "a@b.com"}}}
    result = pick_fields(data, ["data.user.name", "data.user.age"])
    assert result == {"data": {"user": {"name": "Alice", "age": 30}}}


def test_picks_from_list():
    data = {
        "items": [
            {"id": 1, "name": "a", "extra": "x"},
            {"id": 2, "name": "b", "extra": "y"},
        ]
    }
    result = pick_fields(data, ["items.id", "items.name"])
    assert result == {"items": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]}


def test_missing_key_is_skipped():
    data = {"a": 1}
    assert pick_fields(data, ["b"]) == {}


def test_missing_nested_key_is_skipped():
    data = {"a": {"b": 1}}
    assert pick_fields(data, ["a.c"]) == {"a": {}}


def test_none_source_is_handled():
    assert pick_fields(None, ["a"]) == {}


def test_scalar_at_non_terminal_path():
    data = {"a": 42}
    assert pick_fields(data, ["a.b"]) == {"a": 42}
