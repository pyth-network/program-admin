import asyncio
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import pytest
import requests
import ujson as json
from solana.publickey import PublicKey

from program_admin import ProgramAdmin
from program_admin.keys import load_keypair
from program_admin.parsing import (
    parse_authority_permissions_json,
    parse_permissions_with_overrides,
    parse_products_json,
    parse_publishers_json,
)
from program_admin.types import Network, ReferenceOverrides, ReferencePermissions
from program_admin.util import apply_overrides

LOGGER = logging.getLogger(__name__)

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
        "min_publishers": 7,
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
    "metadata": {"jump_id": "186", "jump_symbol": "AAPL", "price_exp": -5},
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
    "metadata": {"jump_id": "12345", "jump_symbol": "ETHUSD", "price_exp": -8},
}


@pytest.fixture
def set_test_env_var():
    """
    Sets an env required for program-admin sync() testing
    """
    os.environ["TEST_MODE"] = "1"


@pytest.fixture
async def oracle():
    """
    Downloads the latest version of the oracle from the pyth-client repo
    """
    api_url = "https://api.github.com/repos/pyth-network/pyth-client/releases/latest"
    filename = "pyth_oracle_pythnet.so"
    outfile = "tests/pyth_oracle.so"

    try:
        response = requests.get(api_url, timeout=300)
        response.raise_for_status()
        release_info = response.json()

        # Find the desired asset in the release assets
        asset_url = None
        for asset in release_info["assets"]:
            if asset["name"] == filename:
                asset_url = asset["browser_download_url"]
                break

        if not asset_url:
            raise Exception(f"Unable to find asset URL for {filename}")

        # Download the asset
        download_response = requests.get(asset_url, timeout=300)
        download_response.raise_for_status()

        # Save the file to the specified path
        with open(outfile, "wb") as file:
            file.write(download_response.content)

        LOGGER.debug(f"File {filename} downloaded successfully to {outfile}.")

    except requests.exceptions.RequestException as error:
        LOGGER.error(f"An error occurred: {error}")
        raise error

    yield outfile


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
                    "pythnet": {"AAPL": True, "BTCUSD": False},
                    "localhost": {"AAPL": False},
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
            LOGGER.debug(f"[stdout]\n{stdout.decode()}")
        if stderr:
            LOGGER.debug(f"[stderr]\n{stderr.decode()}")

        raise RuntimeError("Failed to generate funding key")

    yield f"{key_dir}/funding.json"


@pytest.fixture
def authority_permissions_json(key_dir, pyth_keypair):
    funding_keypair = load_keypair("funding", key_dir=key_dir)
    funding_key = funding_keypair.public_key
    with NamedTemporaryFile() as jsonfile:
        value = {
            "master_authority": str(funding_key),
            "data_curation_authority": str(funding_key),
            "security_authority": str(funding_key),
        }

        LOGGER.debug("Writing authority permissions JSON:\n%s", value)
        jsonfile.write(json.dumps(value).encode())
        jsonfile.flush()

        yield jsonfile.name


@pytest.fixture
async def upgrade_authority_keypair(key_dir, validator):
    keypair_path = f"{key_dir}/upgrade_authority.json"

    process = await asyncio.create_subprocess_shell(
        f"solana-keygen new --no-bip39-passphrase -o {keypair_path}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.wait()

    if process.returncode != 0:
        stdout, stderr = await process.communicate()

        if stdout:
            LOGGER.debug(f"[stdout]\n{stdout.decode()}")
        if stderr:
            LOGGER.debug(f"[stderr]\n{stderr.decode()}")

        raise RuntimeError("Failed to generate upgrade authority key")

    # Fund the keypair
    process = await asyncio.create_subprocess_shell(
        f"solana airdrop 100 -k {keypair_path} -u localhost",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.wait()

    stdout, stderr = await process.communicate()
    LOGGER.debug(f"[cmd exited with {process.returncode}]")
    if stdout:
        LOGGER.debug(f"[stdout]\n{stdout.decode()}")
    if stderr:
        LOGGER.debug(f"[stderr]\n{stderr.decode()}")

    yield keypair_path


# pylint: disable=redefined-outer-name,unused-argument
@pytest.fixture
async def pyth_program(pyth_keypair, upgrade_authority_keypair, oracle):
    process = await asyncio.create_subprocess_shell(
        f"solana airdrop 100 -k {pyth_keypair} -u localhost",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.wait()

    stdout, stderr = await process.communicate()
    LOGGER.debug(f"[cmd exited with {process.returncode}]")
    if stdout:
        LOGGER.debug(f"[stdout]\n{stdout.decode()}")
    if stderr:
        LOGGER.debug(f"[stderr]\n{stderr.decode()}")

    process = await asyncio.create_subprocess_shell(
        f"solana program deploy \
        -k {pyth_keypair} \
        -u localhost \
        --upgrade-authority {upgrade_authority_keypair} \
        {oracle} \
        && sleep 10",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.wait()

    stdout, stderr = await process.communicate()
    LOGGER.debug(f"[cmd exited with {process.returncode}]")
    if stdout:
        LOGGER.debug(f"[stdout]\n{stdout.decode()}")
    if stderr:
        LOGGER.debug(f"[stderr]\n{stderr.decode()}")

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
    result = apply_overrides(permissions, overrides, "localhost")
    assert result == permissions

    overrides = {
        "localhost": {"BTCUSD": False, "AAPL": True},
        "pythnet": {"ETHUSD": False},
    }

    result = apply_overrides(permissions, overrides, "mainnet-beta")
    assert result == permissions

    result = apply_overrides(permissions, overrides, "localhost")
    expected = {
        "AAPL": {"price": ["random"]},
        "BTCUSD": {"price": []},
        "ETHUSD": {"price": ["random"]},
    }
    assert result == expected

    result = apply_overrides(permissions, overrides, "pythnet")
    expected = {
        "AAPL": {"price": ["random"]},
        "BTCUSD": {"price": ["random"]},
        "ETHUSD": {"price": []},
    }

    assert result == expected


# pylint: disable=protected-access,redefined-outer-name
async def test_sync(
    set_test_env_var,
    key_dir,
    pyth_program,
    products_json,
    products2_json,
    publishers_json,
    permissions_json,
    permissions2_json,
    authority_permissions_json,
    empty_overrides_json,
    localhost_overrides_json,
    pyth_keypair,
):
    network = "localhost"
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
        authority_permissions_path=authority_permissions_json,
        overrides_path=empty_overrides_json,
        network=network,
        allocate_price_v2=True,
        generate_keys=True,
    )

    await program_admin.refresh_program_accounts()

    product_accounts = list(program_admin._product_accounts.values())
    price_accounts = list(program_admin._price_accounts.values())
    authority_permission_account = program_admin.authority_permission_account
    if authority_permission_account:
        authority_permissions = authority_permission_account.data
    else:
        raise Exception("Authority permissions not found")

    reference_symbols = ["Crypto.BTC/USD", "Equity.US.AAPL/USD"]

    with open(publishers_json, encoding="utf8") as file:
        random_publisher = PublicKey(json.load(file)["random"])

    assert product_accounts[0].data.metadata["symbol"] in reference_symbols
    assert product_accounts[1].data.metadata["symbol"] in reference_symbols

    assert price_accounts[0].data.price_components[0].publisher_key == random_publisher
    assert price_accounts[1].data.price_components[0].publisher_key == random_publisher

    funding_keypair = load_keypair("funding", key_dir=key_dir)
    funding_key = funding_keypair.public_key
    assert str(authority_permissions.master_authority) == str(funding_key)
    assert str(authority_permissions.data_curation_authority) == str(funding_key)
    assert str(authority_permissions.security_authority) == str(funding_key)

    # Map from symbol names to the corresponding price account
    symbol_price_account_map = {}
    for product_account in product_accounts:
        symbol_price_account_map[product_account.data.metadata["symbol"]] = [
            acc
            for acc in price_accounts
            if acc.public_key == product_account.data.first_price_account_key
        ][0]

    assert symbol_price_account_map["Crypto.BTC/USD"].data.min_publishers == 7
    # Warning: this test hardcodes the default minimum number of publishers for the account.
    # This default may change if you upgrade the oracle program.
    assert symbol_price_account_map["Equity.US.AAPL/USD"].data.min_publishers == 20

    # Syncing again with generate_keys=False should succeed
    await sync_from_files(
        program_admin,
        products_path=products_json,
        publishers_path=publishers_json,
        permissions_path=permissions_json,
        authority_permissions_path=authority_permissions_json,
        overrides_path=empty_overrides_json,
        network=network,
        allocate_price_v2=True,
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
            authority_permissions_path=authority_permissions_json,
            overrides_path=empty_overrides_json,
            network=network,
            allocate_price_v2=True,
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
        authority_permissions_path=authority_permissions_json,
        overrides_path=localhost_overrides_json,
        network=network,
        allocate_price_v2=True,
        generate_keys=False,
    )

    # Test override configuration
    await program_admin.refresh_program_accounts()
    product_accounts = list(program_admin._product_accounts.values())
    is_enabled = {"Crypto.BTC/USD": True, "Equity.US.AAPL/USD": False}

    for product_account in product_accounts:
        symbol = product_account.data.metadata["symbol"]
        price_account = program_admin.get_price_account(
            product_account.data.first_price_account_key
        )

        if is_enabled[symbol]:
            assert (
                price_account.data.price_components[0].publisher_key == random_publisher
            )
        else:
            assert len(price_account.data.price_components) == 0


async def sync_from_files(
    program_admin,
    products_path: str,
    publishers_path: str,
    permissions_path: str,
    authority_permissions_path: str,
    overrides_path: str,
    network: Network,
    allocate_price_v2: bool,
    send_transactions: bool = True,
    generate_keys: bool = False,
):
    ref_products = parse_products_json(Path(products_path))
    ref_publishers = parse_publishers_json(Path(publishers_path))
    ref_permissions = parse_permissions_with_overrides(
        Path(permissions_path), Path(overrides_path), network
    )
    ref_authority_permissions = parse_authority_permissions_json(
        Path(authority_permissions_path)
    )

    return await program_admin.sync(
        ref_products,
        ref_publishers,
        ref_permissions,
        ref_authority_permissions,
        send_transactions,
        generate_keys,
        allocate_price_v2=allocate_price_v2,
    )
