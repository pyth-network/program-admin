from pathlib import Path
from typing import Dict, List, Set, Tuple

from loguru import logger
from solana import system_program
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.transaction import Transaction, TransactionInstruction

from program_admin import instructions as pyth_program
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
    PRICE_ACCOUNT_SIZE,
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

    async def fetch_minimum_balance(self, size: int) -> int:
        """
        Return the minimum balance in lamports for a new account to be rent-exempt.
        """
        async with AsyncClient(RPC_ENDPOINTS[self.network]) as client:
            return (await client.get_minimum_balance_for_rent_exemption(size))["result"]

    async def refresh_program_accounts(self):
        async with AsyncClient(RPC_ENDPOINTS[self.network]) as client:
            logger.debug("Refreshing program accounts")
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
                    logger.debug(f"Found mapping account: {account.public_key}")
                    self._mapping_accounts[account.public_key] = account

                if isinstance(account, PythProductAccount):
                    logger.debug(f"Found product account: {account.public_key}")
                    self._product_accounts[account.public_key] = account

                if isinstance(account, PythPriceAccount):
                    logger.debug(f"Found price account: {account.public_key}")
                    self._price_accounts[account.public_key] = account

    async def send_transaction(
        self, tx_instructions: List[TransactionInstruction], tx_signers: List[Keypair]
    ):
        async with AsyncClient(RPC_ENDPOINTS[self.network]) as client:
            blockhash = await recent_blockhash(client)
            transaction = Transaction(recent_blockhash=blockhash)

            transaction.add(*tx_instructions)
            transaction.sign(*tx_signers)

            response = await client.send_raw_transaction(
                transaction.serialize(),
                opts=TxOpts(skip_confirmation=False),
            )
            logger.debug(f"Transaction: {response['result']}")

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
        # Fetch program accounts from the network
        await self.refresh_program_accounts()

        # Sync mapping accounts
        mapping_instructions, mapping_keypairs = await self.sync_mapping_instructions()

        if mapping_instructions:
            await self.send_transaction(mapping_instructions, mapping_keypairs)
            await self.refresh_program_accounts()

        # TODO: Ensure tail mapping account has enough space for new product accounts

        # Sync product/price accounts
        ref_products = parse_products_json(Path(products_path))
        ref_publishers = parse_publishers_json(Path(publishers_path))

        for jump_symbol, price_accounts in ref_publishers["permissions"].items():
            ref_product = ref_products[jump_symbol]
            publishers = price_accounts["price"]

            (
                product_instructions,
                product_keypairs,
            ) = await self.sync_product_instructions(ref_product, publishers)

            if product_instructions:
                await self.send_transaction(product_instructions, product_keypairs)

        # TODO: Sync publisher keys

    async def sync_mapping_instructions(
        self,
    ) -> Tuple[List[TransactionInstruction], List[Keypair]]:
        mapping_chain = sort_mapping_account_keys(list(self._mapping_accounts.values()))
        program_keypair = load_keypair("program")
        funding_keypair = program_keypair
        mapping_0_keypair = load_keypair("mapping_0", generate=True)
        instruction_list: List[TransactionInstruction] = []

        if not mapping_chain:
            logger.info("Creating new mapping account")
            instruction_list.append(
                system_program.create_account(
                    system_program.CreateAccountParams(
                        from_pubkey=funding_keypair.public_key,
                        new_account_pubkey=mapping_0_keypair.public_key,
                        # FIXME: Change to minimum rent-exempt amount
                        lamports=await self.fetch_minimum_balance(MAPPING_ACCOUNT_SIZE),
                        space=MAPPING_ACCOUNT_SIZE,
                        program_id=self.program_key,
                    )
                )
            )
            instruction_list.append(
                pyth_program.init_mapping(
                    self.program_key,
                    funding_keypair.public_key,
                    mapping_0_keypair.public_key,
                )
            )

        return (instruction_list, [funding_keypair, mapping_0_keypair])

    async def sync_product_instructions(
        self,
        product: Product,
        _publishers: List[str],
    ) -> Tuple[List[TransactionInstruction], List[Keypair]]:
        instructions: List[TransactionInstruction] = []
        funding_keypair = load_keypair("program")
        mapping_chain = sort_mapping_account_keys(list(self._mapping_accounts.values()))
        mapping_keypair = load_keypair(mapping_chain[-1])
        product_keypair = load_keypair(
            f"product_{product['jump_symbol']}", generate=True
        )
        product_account = self._product_accounts.get(product_keypair.public_key)
        price_keypair = load_keypair(f"price_{product['jump_symbol']}", generate=True)
        price_account = self._price_accounts.get(price_keypair.public_key)

        if not product_account:
            logger.info(f"Creating new product account for {product['jump_symbol']}")
            instructions.append(
                system_program.create_account(
                    system_program.CreateAccountParams(
                        from_pubkey=funding_keypair.public_key,
                        new_account_pubkey=product_keypair.public_key,
                        lamports=await self.fetch_minimum_balance(PRODUCT_ACCOUNT_SIZE),
                        space=PRODUCT_ACCOUNT_SIZE,
                        program_id=self.program_key,
                    )
                )
            )
            instructions.append(
                pyth_program.add_product(
                    self.program_key,
                    funding_keypair.public_key,
                    mapping_keypair.public_key,
                    product_keypair.public_key,
                )
            )
            instructions.append(
                pyth_program.update_product(
                    self.program_key,
                    funding_keypair.public_key,
                    product_keypair.public_key,
                    product["metadata"],
                )
            )
            instructions.append(
                system_program.create_account(
                    system_program.CreateAccountParams(
                        from_pubkey=funding_keypair.public_key,
                        new_account_pubkey=price_keypair.public_key,
                        lamports=await self.fetch_minimum_balance(PRICE_ACCOUNT_SIZE),
                        space=PRICE_ACCOUNT_SIZE,
                        program_id=self.program_key,
                    )
                )
            )
            instructions.append(
                pyth_program.add_price(
                    self.program_key,
                    funding_keypair.public_key,
                    product_keypair.public_key,
                    price_keypair.public_key,
                    product["exponent"],
                )
            )

        # When product/price account exists, we check if metadata is up to date
        if product_account and price_account:
            same_product_metadata = True

            for key, value in product["metadata"].items():
                if product_account.data.metadata.get(key) != value:
                    same_product_metadata = False
                    break

            if not same_product_metadata:
                instructions.append(
                    pyth_program.update_product(
                        self.program_key,
                        funding_keypair.public_key,
                        product_keypair.public_key,
                        product["metadata"],
                    )
                )

        # TODO: Sync publishers here

        return (
            instructions,
            [funding_keypair, mapping_keypair, product_keypair, price_keypair],
        )

    def list_program_symbols(self) -> Set[str]:
        symbols = set()

        for _key, account in self._product_accounts.items():
            symbols.add(account.data.metadata["symbol"])

        return symbols
