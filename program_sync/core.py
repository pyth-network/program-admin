from pathlib import Path
from typing import Dict, Set, cast

from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient

from program_sync.parsing import (
    parse_account,
    parse_products_json,
    parse_publishers_json,
)
from program_sync.types import (
    MappingData,
    Network,
    PriceData,
    Product,
    ProductData,
    Publishers,
    PythAccount,
)

RPC_ENDPOINTS: Dict[Network, str] = {
    "devnet": "https://api.devnet.solana.com",
    "localhost": "http://127.0.0.1:8899",
    "mainnet-beta": "https://api.mainnet-beta.solana.com",
    "testnet": "https://api.testnet.solana.com",
}


class ProgramSync:
    network: Network
    program_key: PublicKey
    products: Dict[str, Product]
    publishers: Publishers
    mapping_accounts: Dict[PublicKey, PythAccount]
    product_accounts: Dict[PublicKey, PythAccount]
    price_accounts: Dict[PublicKey, PythAccount]

    def __init__(
        self, network: Network, program_key: str, products: str, publishers: str
    ):
        self.network = network
        self.program_key = PublicKey(program_key)
        self.products = parse_products_json(Path(products))
        self.publishers = parse_publishers_json(Path(publishers))
        self.mapping_accounts: Dict[PublicKey, PythAccount] = {}
        self.product_accounts: Dict[PublicKey, PythAccount] = {}
        self.price_accounts: Dict[PublicKey, PythAccount] = {}

    async def run(self):
        """
        1. Fetch program accounts
        2. Remove old product and price accounts
        3. Create new product and price accounts
        4. Remove old publisher keys
        5. Add new publisher keys
        6. Update outdated product and price accounts
        """

        # 1. Fetch program accounts
        await self.fetch_program_accounts()

        # 2. Create new product and price accounts
        old_products = self.list_old_products()

        if old_products:
            print(f"Old product accounts: {old_products}")

        # 3. Create new product and price accounts
        new_products = self.list_new_products()

        if new_products:
            print(f"New product accounts: {new_products}")

        for jump_symbol, _price_accounts in self.publishers["permissions"].items():
            # 4. Remove old publisher key (assumes a single price account)
            old_publishers = self.list_old_publishers(jump_symbol)

            if old_publishers:
                print(f"Old {jump_symbol} publishers: {old_publishers}")

            # 5. Create new publisher key (assumes a single price account)
            new_publishers = self.list_new_publishers(jump_symbol)

            if new_publishers:
                print(f"New {jump_symbol} publishers: {new_publishers}")

    async def fetch_program_accounts(self):
        async with AsyncClient(RPC_ENDPOINTS[self.network]) as client:
            result = (
                await client.get_program_accounts(
                    pubkey=self.program_key, encoding="base64"
                )
            )["result"]

            for record in result:
                account = parse_account(record)

                if not account or not account.data:
                    continue

                if isinstance(account.data, MappingData):
                    self.mapping_accounts[account.public_key] = account

                if isinstance(account.data, ProductData):
                    self.product_accounts[account.public_key] = account

                if isinstance(account.data, PriceData):
                    self.price_accounts[account.public_key] = account

    def list_program_symbols(self) -> Set[str]:
        symbols = set()

        for _key, account in self.product_accounts.items():
            symbols.add(cast(ProductData, account.data).metadata["symbol"])

        return symbols

    def list_reference_symbols(self) -> Set[str]:
        symbols = set()

        for jump_symbol in self.publishers["permissions"].keys():
            symbols.add(self.products[jump_symbol]["metadata"]["symbol"])

        return symbols

    def list_reference_publishers(self, jump_symbol: str) -> Set[str]:
        # FIXME: Handle multiple price accounts
        return set(self.publishers["permissions"][jump_symbol]["price"])

    def list_program_publishers(self, jump_symbol: str) -> Set[str]:
        """
        Return a list of publisher IDs for the corresponding product account of
        the given symbol.
        """
        symbol = self.products[jump_symbol]["metadata"]["symbol"]
        symbol_product_data = None

        for _key, account in self.product_accounts.items():
            product_data = cast(ProductData, account.data)

            if product_data.metadata["symbol"] == symbol:
                symbol_product_data = product_data

        if not symbol_product_data:
            raise RuntimeError(f"No product account for symbol {symbol}")

        # FIXME: Handle multiple price accounts
        price_account = self.price_accounts[symbol_product_data.first_price_account_key]
        price_components = cast(PriceData, price_account.data).price_components
        publishers: Set[str] = set()

        for component in price_components:
            if component.publisher_key in self.publishers["names"]:
                publishers.add(self.publishers["names"][component.publisher_key])
            else:
                publishers.add(f"??? ({str(component.publisher_key)})")

        return publishers

    def list_new_products(self) -> Set[str]:
        return self.list_reference_symbols() - self.list_program_symbols()

    def list_old_products(self) -> Set[str]:
        return self.list_program_symbols() - self.list_reference_symbols()

    def list_new_publishers(self, jump_symbol: str) -> Set[str]:
        return self.list_reference_publishers(
            jump_symbol
        ) - self.list_program_publishers(jump_symbol)

    def list_old_publishers(self, jump_symbol: str) -> Set[str]:
        return self.list_program_publishers(
            jump_symbol
        ) - self.list_reference_publishers(jump_symbol)
