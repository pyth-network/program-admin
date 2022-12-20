from click.testing import CliRunner

from program_admin import cli


def test_minimum_publishers():
    runner = CliRunner()
    result = runner.invoke(
        cli.set_minimum_publishers,
        [
            "--funding-key",
            "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg",
            "--program-key",
            "3LCB76Eyh4F47g5Vq2jYgDMiAuUNyUbysyMavhVNABEa",
            "--price-key",
            "6bRsDGmuSfUCND9vZioUbWfB56dkrCqNE8f2DW7eNU5D",
            "--value",
            20,
        ],
    )
    assert result.exit_code == 0
    assert "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg" in result.output


def test_toggle_publisher():
    runner = CliRunner()
    result = runner.invoke(
        cli.toggle_publisher,
        [
            "--funding-key",
            "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg",
            "--program-key",
            "3LCB76Eyh4F47g5Vq2jYgDMiAuUNyUbysyMavhVNABEa",
            "--price-key",
            "6bRsDGmuSfUCND9vZioUbWfB56dkrCqNE8f2DW7eNU5D",
            "--publisher-key",
            "6bRsDGmuSfUCND9vZioUbWfB56dkrCqNE8f2DW7eNU5E",
            "--status",
            True,
        ],
    )
    assert result.exit_code == 0
    assert "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg" in result.output


def test_update_product():
    runner = CliRunner()
    result = runner.invoke(
        cli.update_product_metadata,
        [
            "--funding-key",
            "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg",
            "--program-key",
            "3LCB76Eyh4F47g5Vq2jYgDMiAuUNyUbysyMavhVNABEa",
            "--product-key",
            "6bRsDGmuSfUCND9vZioUbWfB56dkrCqNE8f2DW7eNU5D",
            "--metadata",
            {"data": "meta"},
        ],
    )
    assert result.exit_code == 0
    assert "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg" in result.output
