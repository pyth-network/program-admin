import asyncio
import sys
from pathlib import Path
from typing import Dict

import click
from solana.publickey import PublicKey

from program_admin import ProgramAdmin
from program_admin.keys import restore_symlink
from program_admin.parsing import parse_products_json, parse_publishers_json


@click.group()
def cli():
    pass


@click.command()
@click.option("--network", help="Solana network", envvar="NETWORK")
@click.option("--program-key", help="Pyth program key", envvar="PROGRAM_KEY")
@click.option("--keys", help="Path to keys directory", envvar="KEYS")
@click.option(
    "--publishers", help="Path to reference publishers file", envvar="PUBLISHERS"
)
@click.option(
    "--commitment",
    help="Confirmation level to use",
    envvar="COMMITMENT",
    default="finalized",
)
def list_accounts(network, program_key, keys, publishers, commitment):
    program_admin = ProgramAdmin(
        network=network,
        key_dir=keys,
        program_key=program_key,
        commitment=commitment,
    )

    asyncio.run(program_admin.refresh_program_accounts())

    try:
        mapping_key = program_admin.get_first_mapping_key()
    except IndexError:
        print("Program has no mapping accounts")
        sys.exit(1)

    publishers_map = parse_publishers_json(Path(publishers))

    while mapping_key != PublicKey(0):
        mapping_account = program_admin.get_mapping_account(mapping_key)
        print(f"Mapping: {mapping_account.public_key}")

        for product_key in mapping_account.data.product_account_keys:
            product_account = program_admin.get_product_account(product_key)
            print(f"  Product: {product_account.data.metadata['symbol']}")

            if product_account.data.first_price_account_key != PublicKey(0):
                price_account = program_admin.get_price_account(
                    product_account.data.first_price_account_key
                )
                print(
                    f"    Price: {price_account.data.exponent} exponent ({price_account.data.components_count} components)"
                )

                for component in price_account.data.price_components:
                    try:
                        name = publishers_map["names"][component.publisher_key]
                    except KeyError:
                        name = f"??? ({component.publisher_key})"

                    print(f"      Publisher: {name}")

        mapping_key = mapping_account.data.next_mapping_account_key


@click.command()
@click.option("--network", help="Solana network", envvar="NETWORK")
@click.option("--program-key", help="Pyth program key", envvar="PROGRAM_KEY")
@click.option("--keys", help="Path to keys directory", envvar="KEYS")
@click.option("--products", help="Path to reference products file", envvar="PRODUCTS")
@click.option(
    "--commitment",
    help="Confirmation level to use",
    envvar="COMMITMENT",
    default="finalized",
)
def restore_links(network, program_key, keys, products, commitment):
    program_admin = ProgramAdmin(
        network=network,
        key_dir=keys,
        program_key=program_key,
        commitment=commitment,
    )
    reference_products = parse_products_json(Path(products))
    mapping_account_counter = 0
    jump_symbols: Dict[str, str] = {}

    for jump_symbol, product in reference_products.items():
        jump_symbols[product["metadata"]["symbol"]] = jump_symbol

    asyncio.run(program_admin.refresh_program_accounts())

    try:
        mapping_key = program_admin.get_first_mapping_key()
    except IndexError:
        print("Program has no mapping accounts")
        sys.exit(1)

    while mapping_key != PublicKey(0):
        mapping_account = program_admin.get_mapping_account(mapping_key)

        restore_symlink(
            mapping_key, f"mapping_{mapping_account_counter}", program_admin.key_dir
        )

        for product_key in mapping_account.data.product_account_keys:
            product_account = program_admin.get_product_account(product_key)
            symbol = product_account.data.metadata["symbol"]
            jump_symbol = jump_symbols[symbol]

            restore_symlink(
                product_key, f"product_{jump_symbol}", program_admin.key_dir
            )

            # FIXME: Assumes there is only  a single first price account
            if product_account.data.first_price_account_key != PublicKey(0):
                restore_symlink(
                    product_account.data.first_price_account_key,
                    f"price_{jump_symbol}",
                    program_admin.key_dir,
                )

        mapping_key = mapping_account.data.next_mapping_account_key
        mapping_account_counter += 1


@click.command()
@click.option("--network", help="Solana network", envvar="NETWORK")
@click.option("--program-key", help="Pyth program key", envvar="PROGRAM_KEY")
@click.option("--keys", help="Path to keys directory", envvar="KEYS")
@click.option("--products", help="Path to reference products file", envvar="PRODUCTS")
@click.option(
    "--publishers", help="Path to reference publishers file", envvar="PUBLISHERS"
)
@click.option(
    "--permissions", help="Path to reference permissions file", envvar="PERMISSIONS"
)
@click.option(
    "--commitment",
    help="Confirmation level to use",
    envvar="COMMITMENT",
    default="finalized",
)
@click.option(
    "--send-transactions",
    help="Whether to send transactions or just print instructions (set to 'true' or 'false')",
    envvar="SEND_TRANSACTIONS",
    default="true",
)
def sync(
    network,
    program_key,
    keys,
    products,
    publishers,
    permissions,
    commitment,
    send_transactions,
):
    program_admin = ProgramAdmin(
        network=network,
        key_dir=keys,
        program_key=program_key,
        commitment=commitment,
    )

    asyncio.run(
        program_admin.sync(
            products_path=products,
            publishers_path=publishers,
            permissions_path=permissions,
            send_transactions=(send_transactions == "true"),
        )
    )


cli.add_command(list_accounts)
cli.add_command(restore_links)
cli.add_command(sync)
