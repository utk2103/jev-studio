from jev_studio.instructions import DEFAULT_MODE, MODES, build_instructions, resolve_mode


def test_resolve_mode_defaults():
    assert resolve_mode(None) == DEFAULT_MODE
    assert resolve_mode("") == DEFAULT_MODE
    assert resolve_mode("nonsense") == DEFAULT_MODE


def test_resolve_mode_known():
    for m in MODES:
        assert resolve_mode(m) == m
        assert resolve_mode(m.upper()) == m


def test_build_instructions_returns_string():
    for m in MODES:
        out = build_instructions(m)
        assert isinstance(out, str) and out
