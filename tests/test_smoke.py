from suunto_analytics import cli


def test_cli_importable():
    assert callable(cli.main)
