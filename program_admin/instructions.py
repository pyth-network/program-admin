from typing import Dict

from construct import Bytes, Int32sl, Int32ul, Struct
from solana.publickey import PublicKey
from solana.system_program import SYS_PROGRAM_ID
from solana.transaction import AccountMeta, TransactionInstruction

from program_admin.types import ReferenceAuthorityPermissions
from program_admin.util import encode_product_metadata

# TODO: Implement add_mapping instruction

COMMAND_INIT_MAPPING = 0
COMMAND_ADD_PRODUCT = 2
COMMAND_UPD_PRODUCT = 3
COMMAND_ADD_PRICE = 4
COMMAND_ADD_PUBLISHER = 5
COMMAND_DEL_PUBLISHER = 6
COMMAND_MIN_PUBLISHERS = 12
COMMAND_RESIZE_PRICE_ACCOUNT = 14
COMMAND_DEL_PRICE = 15
COMMAND_DEL_PRODUCT = 16
COMMAND_UPD_PERMISSIONS = 17

PRICE_TYPE_PRICE = 1
PROGRAM_VERSION = 2

AUTHORITY_PERMISSIONS_PDA_SEED = b"permissions"

# NOTE(2023-07-11): currently the loader's address is not part of our version of solana-py
BPF_UPGRADEABLE_LOADER_ID = "BPFLoaderUpgradeab1e11111111111111111111111"


def init_mapping(
    program_key: PublicKey, funding_key: PublicKey, mapping_key: PublicKey
) -> TransactionInstruction:
    """
    Pyth program init_mapping instruction

    accounts:
    - funding account (signer, writable)
    - mapping account (signer, writable)
    """
    layout = Struct("version" / Int32ul, "command" / Int32sl)
    data = layout.build(dict(version=PROGRAM_VERSION, command=COMMAND_INIT_MAPPING))

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=mapping_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )


def add_product(
    program_key: PublicKey,
    funding_key: PublicKey,
    mapping_key: PublicKey,
    new_product_key: PublicKey,
) -> TransactionInstruction:
    """
    Pyth program add_product instruction

    accounts:
    - funding account (signer, writable)
    - mapping account (signer, writable)
    - new product account (signer, writable)
    """
    layout = Struct("version" / Int32ul, "command" / Int32sl)
    data = layout.build(dict(version=PROGRAM_VERSION, command=COMMAND_ADD_PRODUCT))

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=mapping_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=new_product_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )


def delete_product(
    program_key: PublicKey,
    funding_key: PublicKey,
    mapping_key: PublicKey,
    product_key: PublicKey,
) -> TransactionInstruction:
    """
    - funding account (signer, writable)
    - mapping account (signer, writable)
    - product account (signer, writable)
    """
    layout = Struct("version" / Int32ul, "command" / Int32sl)
    data = layout.build(dict(version=PROGRAM_VERSION, command=COMMAND_DEL_PRODUCT))

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=mapping_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=product_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )


def update_product(
    program_key: PublicKey,
    funding_key: PublicKey,
    product_key: PublicKey,
    product_metadata: Dict[str, str],
) -> TransactionInstruction:
    """
    Pyth program upd_product instruction

    accounts:
    - funding account (signer, writable)
    - product account (signer, writable)
    """
    layout = Struct("version" / Int32ul, "command" / Int32sl)
    data = layout.build(dict(version=PROGRAM_VERSION, command=COMMAND_UPD_PRODUCT))
    data_extra = encode_product_metadata(product_metadata)

    return TransactionInstruction(
        data=data + data_extra,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=product_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )


def add_price(
    program_key: PublicKey,
    funding_key: PublicKey,
    product_key: PublicKey,
    new_price_key: PublicKey,
    exponent: int,
    price_type: int = PRICE_TYPE_PRICE,
) -> TransactionInstruction:
    """
    Pyth program add_price instruction

    accounts:
    - funding account (signer, writable)
    - product account (signer, writable)
    - new price account (signer, writable)
    """
    layout = Struct(
        "version" / Int32ul, "command" / Int32sl, "exponent" / Int32sl, "type" / Int32ul
    )
    data = layout.build(
        dict(
            version=PROGRAM_VERSION,
            command=COMMAND_ADD_PRICE,
            exponent=exponent,
            type=price_type,
        )
    )

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=product_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=new_price_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )


def delete_price(
    program_key: PublicKey,
    funding_key: PublicKey,
    product_key: PublicKey,
    price_key: PublicKey,
) -> TransactionInstruction:
    """
    - funding account (signer, writable)
    - product account (signer, writable)
    - price account (signer, writable)
    """
    layout = Struct("version" / Int32ul, "command" / Int32sl)
    data = layout.build(dict(version=PROGRAM_VERSION, command=COMMAND_DEL_PRICE))

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=product_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=price_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )


def set_minimum_publishers(
    program_key: PublicKey,
    funding_key: PublicKey,
    price_account_key: PublicKey,
    minimum_publishers: int,
) -> TransactionInstruction:
    """
    Pyth program set_minimum_publishers instruction

    accounts:
    - funding account (signer, writable)
    - price account (writable)
    """
    layout = Struct(
        "version" / Int32ul, "command" / Int32sl, "minimum_publishers" / Int32sl
    )
    data = layout.build(
        dict(
            version=PROGRAM_VERSION,
            command=COMMAND_MIN_PUBLISHERS,
            minimum_publishers=minimum_publishers,
        )
    )

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=price_account_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )


def toggle_publisher(
    program_key: PublicKey,
    funding_key: PublicKey,
    price_account_key: PublicKey,
    publisher_key: PublicKey,
    status: bool,
) -> TransactionInstruction:
    """
    Pyth program add_publisher instruction

    accounts:
    - funding account (signer, writable)
    - price account (signer, writable)
    """
    layout = Struct(
        "version" / Int32ul, "command" / Int32sl, "publisher_key" / Bytes(32)
    )
    data = layout.build(
        dict(
            version=PROGRAM_VERSION,
            command=(COMMAND_ADD_PUBLISHER if status else COMMAND_DEL_PUBLISHER),
            publisher_key=bytes(publisher_key),
        )
    )

    return TransactionInstruction(
        data=data,
        keys=[
            AccountMeta(pubkey=funding_key, is_signer=True, is_writable=True),
            AccountMeta(pubkey=price_account_key, is_signer=True, is_writable=True),
        ],
        program_id=program_key,
    )


def upd_permissions(
    program_key: PublicKey,
    upgrade_authority: PublicKey,
    refdata: ReferenceAuthorityPermissions,
) -> TransactionInstruction:
    """
    Pyth program upd_permissions instruction. Sets contents of the
    permission account which allows us to name various authorities:
    - master_authority        - Authorized to do CRUD on mapping, product and price accounts.
    - data_curation_authority - Authorized for (de)permissioning publishers, can also call set_min_publishers.
    - security_authority      - Authorized for the ResizePriceAccount instruction.

    The authority pubkeys are passed in instruction data.

    Accounts:
    - upgrade authority    (signer, writable)     - must own the oracle program data.
    - program data account (non-signer, readonly) - must be program data for the oracle, must be owned by upgrade authority.
    - permissions account  (non-signer, writable) - PDA of the oracle program, generated automatically, stores the permission information
    - system program       (non-signer, readonly) - Allows the create_account() call if the permissions account is uninitialized

    """
    ix_data_layout = Struct(
        "version" / Int32ul,
        "command" / Int32sl,
        "master_authority" / Bytes(32),
        "data_curation_authority" / Bytes(32),
        "security_authority" / Bytes(32),
    )

    ix_data = ix_data_layout.build(
        dict(
            version=PROGRAM_VERSION,
            command=COMMAND_UPD_PERMISSIONS,
            master_authority=bytes(refdata["master_authority"]),
            data_curation_authority=bytes(refdata["data_curation_authority"]),
            security_authority=bytes(refdata["security_authority"]),
        )
    )

    [permissions_account, _bump] = PublicKey.find_program_address(
        [AUTHORITY_PERMISSIONS_PDA_SEED],
        program_key,
    )

    # Under the BPF upgradeable loader, the program data key is a PDA
    # of the loader program address, taking the consumer program ID as
    # seed. In our case, oracle program ID is the seed.
    [oracle_program_data_key, _bump] = PublicKey.find_program_address(
        [bytes(program_key)],
        PublicKey(BPF_UPGRADEABLE_LOADER_ID),
    )

    return TransactionInstruction(
        data=ix_data,
        keys=[
            AccountMeta(pubkey=upgrade_authority, is_signer=True, is_writable=True),
            AccountMeta(
                pubkey=oracle_program_data_key, is_signer=False, is_writable=False
            ),
            AccountMeta(pubkey=permissions_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
        ],
        program_id=program_key,
    )


def resize_price_account_v2(
    program_key: PublicKey, security_authority: PublicKey, price_account: PublicKey
) -> TransactionInstruction:
    """
    Pyth program resize_price_account instruction. It migrates the
    specified price account to a new v2 format. The new format
    includes more price component slots, allowing more publishers per
    price account. Additionally, PriceCumulative is included

    The authority pubkeys are passed in instruction data.

    Accounts:
    - security authority  (signer, writable)     - must be the pubkey set as security_authority in permission account.
    - price account       (signer, writable)     - The price account to resize
    - system program      (non-signer, readonly) - Allows the resize_account() call
    - permissions account (non-signer, readonly) - PDA of the oracle program, generated automatically, stores the permission information
    """
    ix_data_layout = Struct(
        "version" / Int32ul,
        "command" / Int32sl,
    )

    ix_data = ix_data_layout.build(
        dict(version=PROGRAM_VERSION, command=COMMAND_RESIZE_PRICE_ACCOUNT)
    )

    [permissions_account, _bump] = PublicKey.find_program_address(
        [AUTHORITY_PERMISSIONS_PDA_SEED],
        program_key,
    )

    return TransactionInstruction(
        data=ix_data,
        keys=[
            AccountMeta(pubkey=security_authority, is_signer=True, is_writable=True),
            AccountMeta(pubkey=price_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=permissions_account, is_signer=False, is_writable=False),
        ],
        program_id=program_key,
    )
