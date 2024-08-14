import asyncio
import json
import os
from pathlib import Path
from typing import Any, Coroutine, Dict, List, Literal, Optional, Tuple

from loguru import logger
from solana import system_program
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solana.rpc.types import TxOpts
from solana.transaction import PACKET_DATA_SIZE, Transaction, TransactionInstruction

from program_admin import instructions as pyth_program
from program_admin.keys import load_keypair
from program_admin.parsing import parse_account
from program_admin.types import (
    Network,
    PythAuthorityPermissionAccount,
    PythMappingAccount,
    PythPriceAccount,
    PythProductAccount,
    ReferenceAuthorityPermissions,
    ReferencePermissions,
    ReferenceProduct,
    ReferencePublishers,
)
from program_admin.util import (
    MAPPING_ACCOUNT_SIZE,
    PRICE_ACCOUNT_V1_SIZE,
    PRICE_ACCOUNT_V2_SIZE,
    PRODUCT_ACCOUNT_SIZE,
    account_exists,
    compute_transaction_size,
    get_actual_signers,
    recent_blockhash,
    sort_mapping_account_keys,
)

RPC_ENDPOINTS: Dict[Network, str] = {
    "devnet": "https://api.devnet.solana.com",
    "localhost": "http://127.0.0.1:8899",
    "mainnet-beta": "https://api.mainnet-beta.solana.com",
    "testnet": "https://api.testnet.solana.com",
    "pythnet": "https://pythnet.rpcpool.com",
    "pythtest": "https://api.pythtest.pyth.network",
}


class ProgramAdmin:
    network: Network
    rpc_endpoint: str
    key_dir: Path
    program_key: PublicKey
    authority_permission_account: Optional[PythAuthorityPermissionAccount]
    _mapping_accounts: Dict[PublicKey, PythMappingAccount]
    _product_accounts: Dict[PublicKey, PythProductAccount]
    _price_accounts: Dict[PublicKey, PythPriceAccount]

    def __init__(
        self,
        network: Network,
        key_dir: str,
        program_key: str,
        commitment: Literal["confirmed", "finalized"],
        rpc_endpoint: str = "",
    ):
        self.network = network
        self.rpc_endpoint = rpc_endpoint or RPC_ENDPOINTS[network]
        self.key_dir = Path(key_dir)
        self.program_key = PublicKey(program_key)
        self.commitment = Commitment(commitment)
        self.authority_permission_account = None
        self._mapping_accounts: Dict[PublicKey, PythMappingAccount] = {}
        self._product_accounts: Dict[PublicKey, PythProductAccount] = {}
        self._price_accounts: Dict[PublicKey, PythPriceAccount] = {}

    def get_mapping_account(self, key: PublicKey) -> PythMappingAccount:
        return self._mapping_accounts[key]

    def get_price_account(self, key: PublicKey) -> PythPriceAccount:
        return self._price_accounts[key]

    def get_product_account(self, key: PublicKey) -> PythProductAccount:
        return self._product_accounts[key]

    def get_first_mapping_key(self) -> PublicKey:
        mapping_chain = sort_mapping_account_keys(list(self._mapping_accounts.values()))

        return mapping_chain[0]

    async def fetch_minimum_balance(self, size: int) -> int:
        """
        Return the minimum balance in lamports for a new account to be rent-exempt.
        """
        async with AsyncClient(self.rpc_endpoint) as client:
            return (await client.get_minimum_balance_for_rent_exemption(size)).value

    async def refresh_program_accounts(self):
        async with AsyncClient(self.rpc_endpoint) as client:
            logger.info("Refreshing program accounts")
            result = (
                await client.get_program_accounts(
                    pubkey=self.program_key,
                    encoding="base64",
                    commitment=self.commitment,
                )
            ).value

            reference_pairs = {
                (
                    "gSbePebfvPy7tRqimPoVecS2UsBvYv46ynrzWocc92s",
                    "BmA9Z6FjioHJPpjT39QazZyhDRUdZy2ezwx4GiDdE2u2",
                ),
                (
                    "8tfDNiaEyrV6Q1U4DEXrEigs9DoDtkugzFbybENEbCDz",
                    "AFmdnt9ng1uVxqCmqwQJDAYC5cKTkw8gJKSM5PnzuF6z",
                ),
                (
                    "FsJ3A3u2vn5cTVofAjvy6y5kwABJAqYWpe4975bi2epH",
                    "AHtgzX45WTKfkPG53L6WYhGEXwQkN1BVknET3sVsLL8J",
                ),
            }

            for record in result:
                account = parse_account(record)

                if not account or not account.data:
                    continue

                if isinstance(account, PythMappingAccount):
                    actual_pair = (
                        os.environ.get("PROGRAM_KEY") or str(self.program_key),
                        str(account.public_key),
                    )
                    test_mode = os.environ.get("TEST_MODE")

                    if test_mode or actual_pair in reference_pairs:
                        self._mapping_accounts[account.public_key] = account

                if isinstance(account, PythProductAccount):
                    self._product_accounts[account.public_key] = account

                if isinstance(account, PythPriceAccount):
                    self._price_accounts[account.public_key] = account

                if isinstance(account, PythAuthorityPermissionAccount):
                    self.authority_permission_account = account

            logger.debug(f"Found {len(self._mapping_accounts)} mapping account(s)")
            logger.debug(f"Found {len(self._product_accounts)} product account(s)")
            logger.debug(f"Found {len(self._price_accounts)} price account(s)")

            if self.authority_permission_account:
                logger.debug(
                    f"Found permission account: {self.authority_permission_account.data}"
                )
            else:
                logger.debug("Authority permission account not found")

    async def send_transaction(
        self, instructions: List[TransactionInstruction], signers: List[Keypair]
    ):
        if not instructions:
            return

        async with AsyncClient(self.rpc_endpoint) as client:
            logger.debug(f"Sending {len(instructions)} instructions")

            blockhash = await recent_blockhash(client)
            transaction = Transaction(
                recent_blockhash=blockhash, fee_payer=signers[0].public_key
            )  # The fee payer is the first signer
            transaction.add(instructions[0])
            transaction.sign(*get_actual_signers(signers, transaction))

            ix_index = 1

            # FIXME: Ideally, we would compute the exact additional size of each
            # instruction, add it to the current transaction size and compare
            # that with PACKET_DATA_SIZE. But there is currently no method that
            # returns that information (and no straightforward way to remove an
            # instruction from a transaction if it becomes too large), so we
            # stop adding instructions to a transaction once it reaches half of
            # the maximum size (with the assumption that no single instruction
            # will add more than PACKET_DATA_SIZE/2 bytes to a transaction).
            #
            # FIXME: Also, we probably want to give control of the instructions
            # that go in a transaction to the caller. That way, we can ensure
            # that mapping/product/price accounts are always created and
            # initialized atomically.
            while (
                compute_transaction_size(transaction) < (PACKET_DATA_SIZE / 2)
                and instructions[ix_index:]
            ):
                transaction.add(instructions[ix_index])
                transaction.sign(*get_actual_signers(signers, transaction))
                ix_index += 1

            response = await client.send_raw_transaction(
                transaction.serialize(),
                opts=TxOpts(
                    skip_confirmation=False, preflight_commitment=self.commitment
                ),
            )
            logger.debug(f"Transaction: {response.value}")
            logger.debug(f"Sent {ix_index} instructions")

            remaining_instructions = instructions[ix_index:]

            if remaining_instructions:
                logger.debug("Sending remaining instructions in separate transaction")
                await self.send_transaction(remaining_instructions, signers)

    async def sync(
        self,
        ref_products: Dict[str, ReferenceProduct],
        ref_publishers: ReferencePublishers,
        ref_permissions: ReferencePermissions,
        ref_authority_permissions: ReferenceAuthorityPermissions,
        send_transactions: bool = True,
        generate_keys: bool = False,
        allocate_price_v2: bool = True,
    ) -> List[TransactionInstruction]:
        instructions: List[TransactionInstruction] = []

        # Fetch program accounts from the network
        await self.refresh_program_accounts()

        # Sync authority permissions
        (
            authority_instructions,
            authority_signers,
        ) = await self.sync_authority_permissions_instructions(
            ref_authority_permissions
        )

        if authority_instructions:
            instructions.extend(authority_instructions)

            if send_transactions:
                await self.send_transaction(authority_instructions, authority_signers)

        # Sync mapping accounts
        mapping_instructions, mapping_keypairs = await self.sync_mapping_instructions(
            generate_keys
        )

        if mapping_instructions:
            instructions.extend(mapping_instructions)
            if send_transactions:
                await self.send_transaction(mapping_instructions, mapping_keypairs)

            await self.refresh_program_accounts()

        # FIXME: We should check if the mapping account has enough space to
        # add/remove new products. That is not urgent because we are around 10%
        # of the first mapping account capacity.

        # Sync product/price accounts

        transactions: List[asyncio.Task[None]] = []

        product_updates: bool = False

        for jump_symbol, _price_account_map in ref_permissions.items():
            ref_product = ref_products[jump_symbol]  # type: ignore

            logger.debug(f"Syncing product: {jump_symbol}")
            (
                product_instructions,
                product_keypairs,
            ) = await self.sync_product_instructions(
                ref_product, generate_keys, allocate_price_v2
            )

            if product_instructions:
                product_updates = True

                instructions.extend(product_instructions)
                if send_transactions:
                    transactions.append(
                        asyncio.create_task(
                            self.send_transaction(
                                product_instructions, product_keypairs)
                        )
                    )

        await asyncio.gather(*transactions)

        if product_updates:
            await self.refresh_program_accounts()

        # Sync publishers

        transactions = []

        for jump_symbol, _price_account_map in ref_permissions.items():
            ref_product = ref_products[jump_symbol]  # type: ignore

            logger.debug(f"Syncing price: {jump_symbol}")
            (price_instructions, price_keypairs,) = await self.sync_price_instructions(
                ref_product,
                ref_publishers,
                ref_permissions,
            )

            if price_instructions:
                instructions.extend(price_instructions)
                if send_transactions:
                    transactions.append(
                        asyncio.create_task(
                            self.send_transaction(
                                price_instructions, price_keypairs
                            )
                        )
                    )

        await asyncio.gather(*transactions)

        return instructions

    async def sync_mapping_instructions(
        self,
        generate_keys: bool,
    ) -> Tuple[List[TransactionInstruction], List[Keypair]]:
        mapping_chain = sort_mapping_account_keys(list(self._mapping_accounts.values()))
        funding_keypair = load_keypair("funding", key_dir=self.key_dir)
        mapping_0_keypair = load_keypair(
            "mapping_0", key_dir=self.key_dir, generate=generate_keys
        )
        instructions: List[TransactionInstruction] = []

        if not mapping_chain:
            logger.info("Creating new mapping account")

            if not (
                await account_exists(self.rpc_endpoint, mapping_0_keypair.public_key)
            ):
                logger.debug("Building system.program.create_account instruction")
                instructions.append(
                    system_program.create_account(
                        system_program.CreateAccountParams(
                            from_pubkey=funding_keypair.public_key,
                            new_account_pubkey=mapping_0_keypair.public_key,
                            # FIXME: Change to minimum rent-exempt amount
                            lamports=await self.fetch_minimum_balance(
                                MAPPING_ACCOUNT_SIZE
                            ),
                            space=MAPPING_ACCOUNT_SIZE,
                            program_id=self.program_key,
                        )
                    )
                )

            logger.debug("Building pyth_program.init_mapping instruction")
            instructions.append(
                pyth_program.init_mapping(
                    self.program_key,
                    funding_keypair.public_key,
                    mapping_0_keypair.public_key,
                )
            )

        return (instructions, [funding_keypair, mapping_0_keypair])

    async def sync_product_instructions(
        self,
        product: ReferenceProduct,
        generate_keys: bool,
        allocate_price_v2: bool,
    ) -> Tuple[List[TransactionInstruction], List[Keypair]]:
        instructions: List[TransactionInstruction] = []
        funding_keypair = load_keypair("funding", key_dir=self.key_dir)
        mapping_chain = sort_mapping_account_keys(list(self._mapping_accounts.values()))
        mapping_keypair = load_keypair(mapping_chain[-1], key_dir=self.key_dir)
        product_keypair = load_keypair(
            f"product_{product['jump_symbol']}",
            key_dir=self.key_dir,
            generate=generate_keys,
        )
        product_account = self._product_accounts.get(product_keypair.public_key)
        price_keypair = load_keypair(
            f"price_{product['jump_symbol']}",
            key_dir=self.key_dir,
            generate=generate_keys,
        )
        price_account = self._price_accounts.get(price_keypair.public_key)

        if not product_account:
            logger.info(f"Creating new product account for {product['jump_symbol']}")

            if not (
                await account_exists(self.rpc_endpoint, product_keypair.public_key)
            ):
                logger.debug("Building system_program.create_account instruction")
                instructions.append(
                    system_program.create_account(
                        system_program.CreateAccountParams(
                            from_pubkey=funding_keypair.public_key,
                            new_account_pubkey=product_keypair.public_key,
                            lamports=await self.fetch_minimum_balance(
                                PRODUCT_ACCOUNT_SIZE
                            ),
                            space=PRODUCT_ACCOUNT_SIZE,
                            program_id=self.program_key,
                        )
                    )
                )

            logger.debug("Building pyth_program.add_product instruction")
            instructions.append(
                pyth_program.add_product(
                    self.program_key,
                    funding_keypair.public_key,
                    mapping_keypair.public_key,
                    product_keypair.public_key,
                )
            )
            logger.debug("Building pyth_program.update_product instruction")
            instructions.append(
                pyth_program.update_product(
                    self.program_key,
                    funding_keypair.public_key,
                    product_keypair.public_key,
                    product["metadata"],
                )
            )

        if not price_account:
            logger.info(f"Creating new price account for {product['jump_symbol']}")

            if not await account_exists(self.rpc_endpoint, price_keypair.public_key):
                price_alloc_size = (
                    PRICE_ACCOUNT_V2_SIZE
                    if allocate_price_v2
                    else PRICE_ACCOUNT_V1_SIZE
                )

                logger.debug(
                    f"Building system_program.create_account instruction (allocate_price_v2: {allocate_price_v2}, {price_alloc_size} bytes)"
                )

                instructions.append(
                    system_program.create_account(
                        system_program.CreateAccountParams(
                            from_pubkey=funding_keypair.public_key,
                            new_account_pubkey=price_keypair.public_key,
                            lamports=await self.fetch_minimum_balance(price_alloc_size),
                            space=price_alloc_size,
                            program_id=self.program_key,
                        )
                    )
                )

            logger.debug("Building pyth_program.add_price instruction")
            instructions.append(
                pyth_program.add_price(
                    self.program_key,
                    funding_keypair.public_key,
                    product_keypair.public_key,
                    price_keypair.public_key,
                    int(product["exponent"]),
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
                logger.info(
                    f"Updating product account metadata for {product['jump_symbol']}"
                )
                logger.debug("Building pyth_program.update_product instruction")
                instructions.append(
                    pyth_program.update_product(
                        self.program_key,
                        funding_keypair.public_key,
                        product_keypair.public_key,
                        product["metadata"],
                    )
                )

        return (
            instructions,
            [funding_keypair, mapping_keypair, product_keypair, price_keypair],
        )

    async def sync_price_instructions(
        self,
        reference_product: ReferenceProduct,
        reference_publishers: ReferencePublishers,
        reference_permissions: ReferencePermissions,
    ) -> Tuple[List[TransactionInstruction], List[Keypair]]:
        instructions: List[TransactionInstruction] = []
        funding_keypair = load_keypair("funding", key_dir=self.key_dir)
        price_keypair = load_keypair(
            f"price_{reference_product['jump_symbol']}", key_dir=self.key_dir
        )
        price_account = self.get_price_account(price_keypair.public_key)

        # Sync min publishers (if specified)
        if reference_product["min_publishers"] is not None:
            expected_min_publishers = reference_product["min_publishers"]
            if price_account.data.min_publishers != expected_min_publishers:
                instructions.append(
                    pyth_program.set_minimum_publishers(
                        self.program_key,
                        funding_keypair.public_key,
                        price_keypair.public_key,
                        expected_min_publishers,
                    )
                )

        # Synchronize publisher permissions
        current_publisher_keys = {
            comp.publisher_key for comp in price_account.data.price_components
        }
        new_publisher_names = set(
            reference_permissions[reference_product["jump_symbol"]]["price"]
        )
        new_publisher_keys = {
            reference_publishers["keys"][name] for name in new_publisher_names
        }
        publishers_to_add = new_publisher_keys - current_publisher_keys
        publishers_to_remove = current_publisher_keys - new_publisher_keys

        for publisher_key in publishers_to_remove:
            logger.info(f"Deleting publisher key: {publisher_key}")
            logger.debug("Building pyth_program.del_publisher instruction")
            instructions.append(
                pyth_program.toggle_publisher(
                    self.program_key,
                    funding_keypair.public_key,
                    price_keypair.public_key,
                    publisher_key,
                    status=False,
                )
            )

        for publisher_key in publishers_to_add:
            logger.info(
                f"Adding publisher key: {publisher_key} ({reference_publishers['names'][publisher_key]})"
            )
            logger.debug("Building pyth_program.add_publisher instruction")
            instructions.append(
                pyth_program.toggle_publisher(
                    self.program_key,
                    funding_keypair.public_key,
                    price_keypair.public_key,
                    publisher_key,
                    status=True,
                )
            )

        return (instructions, [funding_keypair, price_keypair])

    async def sync_authority_permissions_instructions(
        self,
        reference_authority_permissions: ReferenceAuthorityPermissions,
    ) -> Tuple[List[TransactionInstruction], List[Keypair]]:
        instructions = []
        signers = []
        if (
            not self.authority_permission_account
            or not self.authority_permission_account.matches_reference_data(
                reference_authority_permissions
            )
        ):
            upgrade_authority_keypair = load_keypair(
                "upgrade_authority", key_dir=self.key_dir
            )

            logger.debug("Building pyth_program.upd_permissions instruction")
            instruction = pyth_program.upd_permissions(
                self.program_key,
                upgrade_authority_keypair.public_key,
                reference_authority_permissions,
            )
            instructions = [instruction]
            signers = [upgrade_authority_keypair]
        else:
            logger.debug("Existing authority permissions OK, not updating")

        return (instructions, signers)

    async def resize_price_accounts_v2(
        self,
        security_authority_path: Path,
        send_transactions: bool,
    ):

        security_authority: Optional[Keypair] = None
        with open(security_authority_path, encoding="utf8") as file:
            data = bytes(json.load(file))

            security_authority = Keypair.from_secret_key(data)

        if not security_authority:
            raise RuntimeError("Could not load security authority keypair")

        await self.refresh_program_accounts()

        v1_prices = {}
        v2_prices = {}
        odd_size_prices = {}

        for (pubkey, account) in self._price_accounts.items():
            # IMPORTANT: sizes must be checked in descending order
            if account.data.used_size >= PRICE_ACCOUNT_V2_SIZE:
                logger.debug(f"Price account {pubkey} is v2")
                v2_prices[pubkey] = account
            elif account.data.used_size >= PRICE_ACCOUNT_V1_SIZE:
                logger.debug(f"Price account {pubkey} is v1")
                v1_prices[pubkey] = account
            else:
                logger.warning(
                    f"Price account {pubkey} of {account.data.used_size} bytes does not match any known used size"
                )
                odd_size_prices[pubkey] = account

        if len(v1_prices) > 0:
            logger.info(f"Found {len(v1_prices)} v1 price account(s)")
        if len(v2_prices) > 0:
            logger.info(f"Found {len(v2_prices)} v2 price account(s)")
        if len(odd_size_prices) > 0:
            logger.info(f"Found {len(odd_size_prices)} unrecognized price accounts")

        instructions = []
        signers = [security_authority]

        for (pubkey, account) in v1_prices.items():
            logger.debug("Building pyth_program.resize_price_account instruction")

            instruction = pyth_program.resize_price_account_v2(
                self.program_key, security_authority.public_key, pubkey
            )
            instructions.append(instruction)

        if send_transactions:
            await self.send_transaction(instructions, signers)
