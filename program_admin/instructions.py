from typing import Dict

from construct import Int32ul, Struct
from solana.publickey import PublicKey
from solana.transaction import AccountMeta, TransactionInstruction

from program_admin.util import encode_product_metadata

PROGRAM_VERSION = 2
COMMAND_INIT_MAPPING = 0
COMMAND_ADD_PRODUCT = 2
COMMAND_UPD_PRODUCT = 3


def init_mapping(
    program_key: PublicKey, funding_key: PublicKey, mapping_key: PublicKey
) -> TransactionInstruction:
    """
    Pyth program init_mapping instruction

    accounts:
    - funding account (signer, writable)
    - mapping account (signer, writable)
    """
    layout = Struct("version" / Int32ul, "command" / Int32ul)
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
    layout = Struct("version" / Int32ul, "command" / Int32ul)
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
    layout = Struct("version" / Int32ul, "command" / Int32ul)
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
