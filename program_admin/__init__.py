from pathlib import Path
from typing import Dict, List, Set

from loguru import logger
from solana import system_program
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction, TransactionInstruction

from program_admin import instructions
from program_admin.keys import generate_keypair, load_keypair
from program_admin.parsing import (
    parse_account,
    parse_products_json,
    parse_publishers_json,
)
from program_admin.types import (
    MappingData,
    Network,
    PriceData,
    Product,
    ProductData,
    Publishers,
    PythMappingAccount,
    PythPriceAccount,
    PythProductAccount,
)
from program_admin.util import (
    MAPPING_ACCOUNT_PRODUCT_LIMIT,
    MAPPING_ACCOUNT_SIZE,
    PRODUCT_ACCOUNT_SIZE,
    SOL_LAMPORTS,
    recent_blockhash,
    sort_mapping_account_keys,
)

RPC_ENDPOINTS: Dict[Network, str] = {
    "devnet": "https://api.devnet.solana.com",
    "localhost": "http://127.0.0.1:8899",
    "mainnet-beta": "https://api.mainnet-beta.solana.com",
    "testnet": "https://api.testnet.solana.com",
}


class ProgramAdmin:
    network: Network
    program_key: PublicKey
    _mapping_accounts: Dict[PublicKey, PythMappingAccount]
    _product_accounts: Dict[PublicKey, PythProductAccount]
    _price_accounts: Dict[PublicKey, PythPriceAccount]

    def __init__(
        self,
        network: Network,
        program_key: str,
    ):
        self.network = network
        self.program_key = PublicKey(program_key)
        self._mapping_accounts: Dict[PublicKey, PythMappingAccount] = {}
        self._product_accounts: Dict[PublicKey, PythProductAccount] = {}
        self._price_accounts: Dict[PublicKey, PythPriceAccount] = {}

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

                if isinstance(account, PythMappingAccount):
                    self._mapping_accounts[account.public_key] = account

                if isinstance(account, PythProductAccount):
                    self._product_accounts[account.public_key] = account

                if isinstance(account, PythPriceAccount):
                    self._price_accounts[account.public_key] = account

    async def send_transaction(
        self, tx_instructions: List[TransactionInstruction], signers: List[Keypair]
    ):
        async with AsyncClient(RPC_ENDPOINTS[self.network]) as client:
            blockhash = await recent_blockhash(client)
            transaction = Transaction(
                recent_blockhash=blockhash, fee_payer=signers[0].public_key
            )

            transaction.add(*tx_instructions)
            transaction.sign(*signers)

            response = await client.send_transaction(
                transaction, *signers, recent_blockhash=blockhash
            )
            logger.info(response)

    def get_mapping_account(self, key: PublicKey) -> PythMappingAccount:
        return self._mapping_accounts[key]

    def get_price_account(self, key: PublicKey) -> PythPriceAccount:
        return self._price_accounts[key]

    def get_product_account(self, key: PublicKey) -> PythProductAccount:
        return self._product_accounts[key]

    def get_first_mapping_key(self) -> PublicKey:
        mapping_chain = sort_mapping_account_keys(list(self._mapping_accounts.values()))

        return mapping_chain[0]

    async def sync(self, products_path: str, publishers_path: str):
        program_keypair = load_keypair("program")
        mapping_chain = sort_mapping_account_keys(list(self._mapping_accounts.values()))

        #
        # Fetch program accounts
        #
        await self.fetch_program_accounts()

        #
        # Ensure mapping account exists and is initialized
        #
        mapping_0_keypair = load_keypair("mapping_0", generate=True)

        if not mapping_chain:
            logger.info("Creating first mapping account")
            # blockhash = await recent_blockhash(rpc_client)
            create_account_ix = system_program.create_account(
                system_program.CreateAccountParams(
                    from_pubkey=program_keypair.public_key,
                    new_account_pubkey=mapping_0_keypair.public_key,
                    # FIXME: Change to minimum rent-exempt amount
                    lamports=1 * SOL_LAMPORTS,
                    space=MAPPING_ACCOUNT_SIZE,
                    program_id=self.program_key,
                )
            )
            init_mapping_ix = instructions.init_mapping(
                self.program_key,
                program_keypair.public_key,
                mapping_0_keypair.public_key,
            )
            await self.send_transaction(
                [create_account_ix, init_mapping_ix],
                [program_keypair, mapping_0_keypair],
            )
        else:
            mapping_account = self.get_mapping_account(mapping_0_keypair.public_key)

            if mapping_account.data.product_count >= MAPPING_ACCOUNT_PRODUCT_LIMIT:
                # FIXME: Implement creation of next mapping account if first one is full
                raise RuntimeError("No more room in first mapping account")

        #
        # Create new products
        #
        ref_products = parse_products_json(Path(products_path))
        ref_publishers = parse_publishers_json(Path(publishers_path))
        program_symbols = self.list_program_symbols()
        reference_symbols = set()
        jump_symbols: Dict[str, str] = {}

        for jump_symbol in ref_publishers["permissions"].keys():
            symbol = ref_products[jump_symbol]["metadata"]["symbol"]
            reference_symbols.add(symbol)
            # Keep track of symbol -> jump_symbol mapping
            jump_symbols[symbol] = jump_symbol

        new_symbols = reference_symbols - program_symbols

        for symbol in new_symbols:
            mapping_keypair = load_keypair(mapping_chain[-1])
            product_keypair = load_keypair(
                f"product_{jump_symbols[symbol]}", generate=True
            )
            create_account_ix = system_program.create_account(
                system_program.CreateAccountParams(
                    from_pubkey=program_keypair.public_key,
                    new_account_pubkey=product_keypair.public_key,
                    # FIXME: Change to minimum rent-exempt amount
                    lamports=1 * SOL_LAMPORTS,
                    space=PRODUCT_ACCOUNT_SIZE,
                    program_id=self.program_key,
                )
            )
            add_product_ix = instructions.add_product(
                self.program_key,
                program_keypair.public_key,
                mapping_keypair.public_key,
                product_keypair.public_key,
            )

            logger.info(f"Creating {symbol} product account")
            await self.send_transaction(
                [create_account_ix, add_product_ix],
                [program_keypair, mapping_keypair, product_keypair],
            )

        return

        # 2. Create new product and price accounts
        old_products = self.list_old_products()

        if old_products:
            print(f"Old product accounts: {old_products}")

        # 3. Create new product and price accounts

        if new_products:
            print(f"New product accounts: {new_products}")

        for jump_symbol, _price_accounts in publishers["permissions"].items():
            # 4. Remove old publisher key (assumes a single price account)
            old_publishers = self.list_old_publishers(jump_symbol)

            if old_publishers:
                print(f"Old {jump_symbol} publishers: {old_publishers}")

            # 5. Create new publisher key (assumes a single price account)
            new_publishers = self.list_new_publishers(jump_symbol)

            if new_publishers:
                print(f"New {jump_symbol} publishers: {new_publishers}")

    def list_program_symbols(self) -> Set[str]:
        symbols = set()

        for _key, account in self._product_accounts.items():
            symbols.add(account.data.metadata["symbol"])

        return symbols

    # def list_reference_publishers(self, jump_symbol: str) -> Set[str]:
    #    # FIXME: Handle multiple price accounts
    #    return set(self.publishers["permissions"][jump_symbol]["price"])

    # def list_program_publishers(self, jump_symbol: str) -> Set[str]:
    #    """
    #    Return a list of publisher IDs for the corresponding product account of
    #    the given symbol.
    #    """
    #    symbol = self.products[jump_symbol]["metadata"]["symbol"]
    #    symbol_product_data = None

    #    for _key, account in self.product_accounts.items():
    #        product_data = cast(ProductData, account.data)

    #        if product_data.metadata["symbol"] == symbol:
    #            symbol_product_data = product_data

    #    if not symbol_product_data:
    #        raise RuntimeError(f"No product account for symbol {symbol}")

    #    # FIXME: Handle multiple price accounts
    #    price_account = self.price_accounts[symbol_product_data.first_price_account_key]
    #    price_components = cast(PriceData, price_account.data).price_components
    #    publishers: Set[str] = set()

    #    for component in price_components:
    #        if component.publisher_key in self.publishers["names"]:
    #            publishers.add(self.publishers["names"][component.publisher_key])
    #        else:
    #            publishers.add(f"??? ({str(component.publisher_key)})")

    #    return publishers

    # def list_new_products(self) -> Set[str]:
    #    return self.list_reference_symbols() - self.list_program_symbols()

    # def list_old_products(self) -> Set[str]:
    #    return self.list_program_symbols() - self.list_reference_symbols()

    # def list_new_publishers(self, jump_symbol: str) -> Set[str]:
    #    return self.list_reference_publishers(
    #        jump_symbol
    #    ) - self.list_program_publishers(jump_symbol)

    # def list_old_publishers(self, jump_symbol: str) -> Set[str]:
    #    return self.list_program_publishers(
    #        jump_symbol
    #    ) - self.list_reference_publishers(jump_symbol)
