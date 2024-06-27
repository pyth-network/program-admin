import json

from click.testing import CliRunner

from program_admin import cli

PERMISSIONS_ACCOUNT = "C3dX9x4N9HYq9TTPj1gH3xFBR6JmE8cBJiLPgxXcZGiv"


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
    assert (
        result.output
        == f'[{{"program_id": "3LCB76Eyh4F47g5Vq2jYgDMiAuUNyUbysyMavhVNABEa", "data": "020000000c00000014000000", "accounts": [{{"pubkey": "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg", "is_signer": true, "is_writable": true}}, {{"pubkey": "6bRsDGmuSfUCND9vZioUbWfB56dkrCqNE8f2DW7eNU5D", "is_signer": true, "is_writable": true}}, {{"pubkey": "{PERMISSIONS_ACCOUNT}", "is_signer": false, "is_writable": true}}]}}]'
    )
    json_data = json.loads(result.output)
    for key in ["program_id", "data", "accounts"]:
        assert key in json_data[0].keys()


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
    assert (
        result.output
        == f'[{{"program_id": "3LCB76Eyh4F47g5Vq2jYgDMiAuUNyUbysyMavhVNABEa", "data": "0200000005000000531c4c42ec1c272ea2a88f736f9ae65152763e92583ebbc0d634777bdf3a5259", "accounts": [{{"pubkey": "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg", "is_signer": true, "is_writable": true}}, {{"pubkey": "6bRsDGmuSfUCND9vZioUbWfB56dkrCqNE8f2DW7eNU5D", "is_signer": true, "is_writable": true}}, {{"pubkey": "{PERMISSIONS_ACCOUNT}", "is_signer": false, "is_writable": true}}]}}]'
    )
    json_data = json.loads(result.output)
    for key in ["program_id", "data", "accounts"]:
        assert key in json_data[0].keys()


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
    assert (
        result.output
        == f'[{{"program_id": "3LCB76Eyh4F47g5Vq2jYgDMiAuUNyUbysyMavhVNABEa", "data": "02000000030000000464617461046d657461", "accounts": [{{"pubkey": "3LCB76EyhJF47g5Vq2jYgDMiAuUNyUbysyMavhVNABEg", "is_signer": true, "is_writable": true}}, {{"pubkey": "6bRsDGmuSfUCND9vZioUbWfB56dkrCqNE8f2DW7eNU5D", "is_signer": true, "is_writable": true}}, {{"pubkey": "{PERMISSIONS_ACCOUNT}", "is_signer": false, "is_writable": true}}]}}]'
    )

    json_data = json.loads(result.output)
    for key in ["program_id", "data", "accounts"]:
        assert key in json_data[0].keys()
