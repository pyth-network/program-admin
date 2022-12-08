import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Literal, Tuple

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
from program_admin.parsing import (
    parse_account,
    parse_overrides_json,
    parse_permissions_json,
    parse_products_json,
    parse_publishers_json,
)
from program_admin.types import (
    Network,
    PythMappingAccount,
    PythPriceAccount,
    PythProductAccount,
    ReferencePermissions,
    ReferenceProduct,
    ReferencePublishers,
)
from program_admin.util import (
    MAPPING_ACCOUNT_SIZE,
    PRICE_ACCOUNT_SIZE,
    PRODUCT_ACCOUNT_SIZE,
    compute_transaction_size,
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
    _mapping_accounts: Dict[PublicKey, PythMappingAccount]
    _product_accounts: Dict[PublicKey, PythProductAccount]
    _price_accounts: Dict[PublicKey, PythPriceAccount]

    def __init__(
        self,
        network: Network,
        key_dir: str,
        program_key: str,
        commitment: Literal["confirmed", "finalized"],
        rpc_endpoint: str = None,
    ):
        self.network = network
        self.rpc_endpoint = rpc_endpoint or RPC_ENDPOINTS[network]
        self.key_dir = Path(key_dir)
        self.program_key = PublicKey(program_key)
        self.commitment = Commitment(commitment)
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
            return (await client.get_minimum_balance_for_rent_exemption(size))["result"]

    async def refresh_program_accounts(self):
        async with AsyncClient(self.rpc_endpoint) as client:
            logger.info("Refreshing program accounts")
            result = (
                await client.get_program_accounts(
                    pubkey=self.program_key,
                    encoding="base64",
                    commitment=self.commitment,
                )
            )["result"]

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

            logger.debug(f"Found {len(self._mapping_accounts)} mapping account(s)")
            logger.debug(f"Found {len(self._product_accounts)} product account(s)")
            logger.debug(f"Found {len(self._price_accounts)} price account(s)")

    async def send_transaction(
        self,
        instructions: List[TransactionInstruction],
        signers: List[Keypair],
        dump_instructions: bool = False,
    ):
        if not instructions:
            return

        async with AsyncClient(self.rpc_endpoint) as client:
            logger.debug(f"Sending {len(instructions)} instructions")

            blockhash = await recent_blockhash(client)
            transaction = Transaction(recent_blockhash=blockhash)

            transaction.add(instructions[0])
            transaction.sign(*signers)

            ix_index = 1

            if dump_instructions:
                dump_output = []
                for instruction in instructions:
                    instruction_output = {
                        "program_id": instruction.program_id,
                        "data": instruction.data.decode(),
                    }
                    accounts = []
                    for account in instruction.keys:
                        account_data = {
                            "pubkey": str(account.pubkey),
                            "is_signer": account.is_signer,
                            "is_writable": account.is_writable,
                        }
                        accounts.append(account_data)
                    instruction_output["accounts"] = accounts
                    dump_output.append(instruction_output)
                sys.stdout.write(json.dumps(dump_output))
                if not os.environ.get("TEST_MODE"):
                    with open(
                        "/var/test/instruction.json", "w", encoding="utf-8"
                    ) as out_file:
                        out_file.write(json.dumps(dump_output))

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
                transaction.sign(*signers)
                ix_index += 1

            if not dump_instructions:
                response = await client.send_raw_transaction(
                    transaction.serialize(),
                    opts=TxOpts(
                        skip_confirmation=False, preflight_commitment=self.commitment
                    ),
                )
                logger.debug(f"Transaction: {response['result']}")

            logger.debug(f"Sent {ix_index} instructions")

            remaining_instructions = instructions[ix_index:]

            if remaining_instructions:
                logger.debug("Sending remaining instructions in separate transaction")
                await self.send_transaction(remaining_instructions, signers)
            else:
                if dump_instructions:
                    return dump_output

    async def sync(
        self,
        ref_products: ReferenceProduct,
        ref_publishers: ReferencePublishers,
        ref_permissions: ReferencePermissions,
        send_transactions: bool = True,
        generate_keys: bool = False,
    ) -> List[TransactionInstruction]:
        instructions: List[TransactionInstruction] = []

        # Fetch program accounts from the network
        await self.refresh_program_accounts()

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

        product_updates: bool = False

        for jump_symbol, _price_account_map in ref_permissions.items():
            ref_product = ref_products[jump_symbol]  # type: ignore

            logger.debug(f"Syncing product: {jump_symbol}")
            (
                product_instructions,
                product_keypairs,
            ) = await self.sync_product_instructions(ref_product, generate_keys)

            if product_instructions:
                product_updates = True

                instructions.extend(product_instructions)
                if send_transactions:
                    await self.send_transaction(product_instructions, product_keypairs)

        if product_updates:
            await self.refresh_program_accounts()

        # Sync publishers
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
                    await self.send_transaction(price_instructions, price_keypairs)

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

            logger.debug("Building system.program.create_account instruction")
            instructions.append(
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
            logger.debug("Building system_program.create_account instruction")
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
            logger.debug("Building system_program.create_account instruction")
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
            logger.debug("Building pyth_program.add_price instruction")
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
