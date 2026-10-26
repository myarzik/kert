from importlib.metadata import version

from typer.testing import CliRunner

from kert.cli import app

runner = CliRunner()


def test_version_flag_prints_package_version_and_exits_zero():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"kert {version('kert')}"
