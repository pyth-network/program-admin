import asyncio

import click

from program_admin.sync import Sync


@click.group()
def cli():
    pass


@click.command()
@click.option("--network", help="Solana network", envvar="NETWORK")
@click.option("--program-key", help="Pyth program key", envvar="PROGRAM_KEY")
@click.option("--products", help="Path to reference products file", envvar="PRODUCTS")
@click.option(
    "--publishers", help="Path to reference publishers file", envvar="PUBLISHERS"
)
def sync(network, program_key, products, publishers):
    asyncio.run(
        Sync(
            network=network,
            program_key=program_key,
            products=products,
            publishers=publishers,
        ).run()
    )


cli.add_command(sync)
