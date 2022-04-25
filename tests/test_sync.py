import asyncio
from tempfile import NamedTemporaryFile, TemporaryDirectory

import pytest
import ujson as json

from program_admin import ProgramAdmin


@pytest.fixture
def key_dir():
    with TemporaryDirectory() as directory:
        yield directory


@pytest.fixture
def products_json():
    with NamedTemporaryFile(delete=False) as jsonfile:
        jsonfile.write(
            json.dumps(
                [
                    {
                        "account": "",
                        "attr_dict": {
                            "symbol": "Crypto.BTC/USD",
                            "asset_type": "Crypto",
                            "base": "BTC",
                            "quote_currency": "USD",
                            "generic_symbol": "BTCUSD",
                            "description": "BTC/USD",
                        },
                        "metadata": {
                            "jump_id": "78876709",
                            "jump_symbol": "BTCUSD",
                            "price_exp": -8,
                        },
                    },
                    {
                        "account": "",
                        "attr_dict": {
                            "asset_type": "Equity",
                            "country": "US",
                            "description": "APPLE INC",
                            "quote_currency": "USD",
                            "cms_symbol": "AAPL",
                            "cqs_symbol": "AAPL",
                            "nasdaq_symbol": "AAPL",
                            "symbol": "Equity.US.AAPL/USD",
                            "base": "AAPL",
                        },
                        "metadata": {
                            "jump_id": "186",
                            "jump_symbol": "AAPL",
                            "price_exp": -5,
                        },
                    },
                ]
            ).encode()
        )
        jsonfile.flush()

        yield jsonfile.name


@pytest.fixture
def publishers_json():
    with NamedTemporaryFile() as jsonfile:
        jsonfile.write(
            json.dumps(
                {
                    "publisher_keys": {
                        "random": "23CGbZq2AAzZcHk1vVBs9Zq4AkNJhjxRbjMiCFTy8vJP",  # random key
                    },
                    "publisher_permissions": {
                        "AAPL": {"price": ["random"]},
                        "BTCUSD": {"price": ["random"]},
                    },
                },
            ).encode()
        )
        jsonfile.flush()

        yield jsonfile.name


# pylint: disable=redefined-outer-name
@pytest.fixture
async def pyth_keypair(key_dir):
    process = await asyncio.create_subprocess_shell(
        f"solana-keygen new -o {key_dir}/program.json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.wait()

    yield f"{key_dir}/program.json"


# pylint: disable=redefined-outer-name,unused-argument
@pytest.fixture
async def pyth_program(pyth_keypair):
    process = await asyncio.create_subprocess_shell(
        f" && solana airdrop 100 -k {pyth_keypair} --commitment=finalized",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.wait()

    stdout, stderr = await process.communicate()
    print(f"[cmd exited with {process.returncode}]")
    if stdout:
        print(f"[stdout]\n{stdout.decode()}")
    if stderr:
        print(f"[stderr]\n{stderr.decode()}")

    process = await asyncio.create_subprocess_shell(
        f"solana program deploy -k {pyth_keypair} --commitment=finalized tests/oracle.so",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.wait()

    stdout, stderr = await process.communicate()
    print(f"[cmd exited with {process.returncode}]")
    if stdout:
        print(f"[stdout]\n{stdout.decode()}")
    if stderr:
        print(f"[stderr]\n{stderr.decode()}")

    _, _, program_id = stdout.decode("ascii").split()

    yield program_id


# pylint: disable=protected-access,redefined-outer-name
async def test_sync(key_dir, pyth_program, products_json, publishers_json):
    program_admin = ProgramAdmin(
        network="localhost",
        key_dir=key_dir,
        program_key=pyth_program,
    )

    await program_admin.sync(
        products_path=products_json,
        publishers_path=publishers_json,
    )

    await program_admin.refresh_program_accounts(commitment="confirmed")

    product_accounts = list(program_admin._product_accounts.values())

    assert product_accounts[0].data.metadata["symbol"] == "Crypto.BTC/USD"
    assert product_accounts[1].data.metadata["symbol"] == "Equity.US.AAPL/USD"
