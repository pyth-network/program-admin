import argparse
import asyncio

from loguru import logger

from program_admin.sync import ProgramSync
from program_admin.util import EnvDefault


def main():
    parser = argparse.ArgumentParser(description="Sync Pyth program")

    parser.add_argument(
        "--network",
        help="Network where program is deployed",
        type=str,
        action=EnvDefault,
        env_var="NETWORK",
        required=True,
        choices=["devnet", "localhost", "mainnet-beta", "testnet"],
    )
    parser.add_argument(
        "--program-key",
        help="Public key of the Pyth program account",
        type=str,
        action=EnvDefault,
        env_var="PROGRAM_KEY",
        required=True,
    )
    parser.add_argument(
        "--products",
        help="Path to products.json file",
        type=str,
        action=EnvDefault,
        env_var="PRODUCTS",
        required=True,
    )
    parser.add_argument(
        "--publishers",
        help="Path to publishers.json file",
        type=str,
        action=EnvDefault,
        env_var="PUBLISHERS",
        required=True,
    )

    args = parser.parse_args()

    try:
        program_sync = ProgramSync(
            network=args.network,
            program_key=args.program_key,
            products=args.products,
            publishers=args.publishers,
        )

        asyncio.run(program_sync.run())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
