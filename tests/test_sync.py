import asyncio
import os
from tempfile import NamedTemporaryFile, TemporaryDirectory
from pathlib import Path

import pytest
import ujson as json
from solana.publickey import PublicKey

from program_admin import ProgramAdmin
from program_admin.parsing import parse_products_json, parse_publishers_json, parse_overrides_json, parse_permissions_json
from program_admin.types import Network, ReferencePermissions, ReferenceOverrides
from program_admin.util import apply_overrides

BTC_USD = {
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
}
AAPL_USD = {
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
}
ETH_USD = {
    "account": "",
    "attr_dict": {
        "symbol": "Crypto.ETH/USD",
        "asset_type": "Crypto",
        "base": "ETH",
        "quote_currency": "USD",
        "generic_symbol": "ETHUSD",
        "description": "ETH/USD",
    },
    "metadata": {
        "jump_id": "12345",
        "jump_symbol": "ETHUSD",
        "price_exp": -8,
    },
}


@pytest.fixture
def key_dir():
    with TemporaryDirectory() as directory:
        yield directory


@pytest.fixture
def products_json():
    with NamedTemporaryFile(delete=False) as jsonfile:
        jsonfile.write(json.dumps([BTC_USD, AAPL_USD]).encode())
        jsonfile.flush()

        yield jsonfile.name


@pytest.fixture
def products2_json():
    with NamedTemporaryFile(delete=False) as jsonfile:
        jsonfile.write(json.dumps([BTC_USD, AAPL_USD, ETH_USD]).encode())
        jsonfile.flush()

        yield jsonfile.name


@pytest.fixture
def publishers_json():
    with NamedTemporaryFile() as jsonfile:
        jsonfile.write(
            json.dumps(
                {
                    "random": "23CGbZq2AAzZcHk1vVBs9Zq4AkNJhjxRbjMiCFTy8vJP",  # random key
                },
            ).encode()
        )
        jsonfile.flush()

        yield jsonfile.name


@pytest.fixture
def permissions_json():
    with NamedTemporaryFile() as jsonfile:
        jsonfile.write(
            json.dumps(
                {
                    "AAPL": {"price": ["random"]},
                    "BTCUSD": {"price": ["random"]},
                },
            ).encode()
        )
        jsonfile.flush()

        yield jsonfile.name


@pytest.fixture
def permissions2_json():
    with NamedTemporaryFile() as jsonfile:
        jsonfile.write(
            json.dumps(
                {
                    "AAPL": {"price": ["random"]},
                    "BTCUSD": {"price": ["random"]},
                    "ETHUSD": {"price": ["random"]},
                },
            ).encode()
        )
        jsonfile.flush()

        yield jsonfile.name

@pytest.fixture
def empty_overrides_json():
    with NamedTemporaryFile() as jsonfile:
        jsonfile.write(
            json.dumps(
                {},
            ).encode()
        )
        jsonfile.flush()

        yield jsonfile.name

@pytest.fixture
def localhost_overrides_json():
    with NamedTemporaryFile() as jsonfile:
        jsonfile.write(
            json.dumps(
                {
                    'pythnet': {'AAPL': True, 'BTCUSD': False},
                    'localhost': {'AAPL': False},
                },
            ).encode()
        )
        jsonfile.flush()

        yield jsonfile.name


@pytest.fixture
async def validator():
    process = await asyncio.create_subprocess_shell(
        "solana-test-validator",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await asyncio.sleep(5.0)

    yield process.pid

    process.terminate()
    await process.wait()


# pylint: disable=redefined-outer-name,unused-argument
@pytest.fixture
async def pyth_keypair(key_dir, validator):
    process = await asyncio.create_subprocess_shell(
        f"solana-keygen new --no-bip39-passphrase -o {key_dir}/funding.json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.wait()

    if process.returncode != 0:
        stdout, stderr = await process.communicate()

        if stdout:
            print(f"[stdout]\n{stdout.decode()}")
        if stderr:
            print(f"[stderr]\n{stderr.decode()}")

        raise RuntimeError("Failed to generate funding key")

    yield f"{key_dir}/funding.json"


# pylint: disable=redefined-outer-name,unused-argument
@pytest.fixture
async def pyth_program(pyth_keypair):
    process = await asyncio.create_subprocess_shell(
        f"solana airdrop 100 -k {pyth_keypair} -u localhost",
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
        f"solana program deploy -k {pyth_keypair} -u localhost tests/pyth_oracle.so",
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

    # FIXME: This is so the mapping account kludge can work (we are bypassing
    # the input args and using env. variables directly).
    os.environ["PROGRAM_KEY"] = program_id

    yield program_id


def test_apply_overrides():
    permissions: ReferencePermissions = {
        "AAPL": {"price": ["random"]},
        "BTCUSD": {"price": ["random"]},
        "ETHUSD": {"price": ["random"]},
    }

    overrides: ReferenceOverrides = {}
    result = apply_overrides(permissions, overrides, 'localhost')
    assert(result == permissions)

    overrides = {
        'localhost': {
            'BTCUSD': False,
            'AAPL': True
        },
        'pythnet': {
            'ETHUSD': False
        }
    }

    result = apply_overrides(permissions, overrides, 'mainnet-beta')
    assert(result == permissions)

    result = apply_overrides(permissions, overrides, 'localhost')
    expected = {
        "AAPL": {"price": ["random"]},
        "BTCUSD": {"price": []},
        "ETHUSD": {"price": ["random"]},
    }
    assert(result == expected)

    result = apply_overrides(permissions, overrides, 'pythnet')
    expected = {
        "AAPL": {"price": ["random"]},
        "BTCUSD": {"price": ["random"]},
        "ETHUSD": {"price": []},
    }

    assert(result == expected)

# pylint: disable=protected-access,redefined-outer-name
async def test_sync(
    key_dir,
    pyth_program,
    products_json,
    products2_json,
    publishers_json,
    permissions_json,
    permissions2_json,
    empty_overrides_json,
    localhost_overrides_json,
):
    network = 'localhost'
    program_admin = ProgramAdmin(
        network=network,
        key_dir=key_dir,
        program_key=pyth_program,
        commitment="confirmed",
    )

    await sync_from_files(
        program_admin,
        products_path=products_json,
        publishers_path=publishers_json,
        permissions_path=permissions_json,
        overrides_path=empty_overrides_json,
        network=network,
        generate_keys=True,
    )

    await program_admin.refresh_program_accounts()

    product_accounts = list(program_admin._product_accounts.values())
    price_accounts = list(program_admin._price_accounts.values())
    reference_symbols = ["Crypto.BTC/USD", "Equity.US.AAPL/USD"]

    with open(publishers_json, encoding="utf8") as file:
        random_publisher = PublicKey(json.load(file)["random"])

    assert product_accounts[0].data.metadata["symbol"] in reference_symbols
    assert product_accounts[1].data.metadata["symbol"] in reference_symbols

    assert price_accounts[0].data.price_components[0].publisher_key == random_publisher
    assert price_accounts[1].data.price_components[0].publisher_key == random_publisher

    # Syncing again with generate_keys=False should succeed
    await sync_from_files(
        program_admin,
        products_path=products_json,
        publishers_path=publishers_json,
        permissions_path=permissions_json,
        overrides_path=empty_overrides_json,
        network=network,
        generate_keys=False,
    )

    # Syncing a different product list should fail
    threw_error = False
    try:
        await sync_from_files(
            program_admin,
            products_path=products2_json,
            publishers_path=publishers_json,
            permissions_path=permissions2_json,
            overrides_path=empty_overrides_json,
            network=network,
            generate_keys=False,
        )
    except RuntimeError:
        threw_error = True

    assert threw_error

    # Test overriding network configurations
    await sync_from_files(
        program_admin,
        products_path=products_json,
        publishers_path=publishers_json,
        permissions_path=permissions_json,
        overrides_path=localhost_overrides_json,
        network=network,
        generate_keys=False,
    )

    await program_admin.refresh_program_accounts()
    product_accounts = list(program_admin._product_accounts.values())
    price_accounts = list(program_admin._price_accounts.values())

    is_enabled = {
        "Crypto.BTC/USD": True,
        "Equity.US.AAPL/USD": False
    }

    for product_account in product_accounts:
        symbol = product_account.data.metadata["symbol"]
        price_account = program_admin.get_price_account(product_account.data.first_price_account_key)

        if is_enabled[symbol]:
            assert(price_account.data.price_components[0].publisher_key == random_publisher)
        else:
            assert(len(price_account.data.price_components) == 0)

async def sync_from_files(
    program_admin,
    products_path: str,
    publishers_path: str,
    permissions_path: str,
    overrides_path: str,
    network: Network,
    send_transactions: bool = True,
    generate_keys: bool = False,
):
    ref_products = parse_products_json(Path(products_path))
    ref_publishers = parse_publishers_json(Path(publishers_path))
    ref_permissions = parse_permissions_json(Path(permissions_path))
    ref_overrides = parse_overrides_json(Path(overrides_path))
    updated_permissions = apply_overrides(ref_permissions, ref_overrides, network)

    return await program_admin.sync(ref_products, ref_publishers, updated_permissions, send_transactions, generate_keys)
