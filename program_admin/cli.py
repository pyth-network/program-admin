import asyncio
import sys
from pathlib import Path

import click
from solana.publickey import PublicKey

from program_admin import ProgramAdmin
from program_admin.parsing import parse_publishers_json


@click.group()
def cli():
    pass


@click.command()
@click.option("--network", help="Solana network", envvar="NETWORK")
@click.option("--program-key", help="Pyth program key", envvar="PROGRAM_KEY")
@click.option(
    "--publishers", help="Path to reference publishers file", envvar="PUBLISHERS"
)
def list_accounts(network, program_key, publishers):
    program_admin = ProgramAdmin(
        network=network,
        program_key=program_key,
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
                    print(
                        f"      Publisher: {publishers_map['names'][component.publisher_key]}"
                    )

        mapping_key = mapping_account.data.next_mapping_account_key


@click.command()
@click.option("--network", help="Solana network", envvar="NETWORK")
@click.option("--program-key", help="Pyth program key", envvar="PROGRAM_KEY")
@click.option("--products", help="Path to reference products file", envvar="PRODUCTS")
@click.option(
    "--publishers", help="Path to reference publishers file", envvar="PUBLISHERS"
)
def sync(network, program_key, products, publishers):
    program_admin = ProgramAdmin(
        network=network,
        program_key=program_key,
    )

    asyncio.run(
        program_admin.sync(
            products_path=products,
            publishers_path=publishers,
        )
    )


cli.add_command(list_accounts)
cli.add_command(sync)
