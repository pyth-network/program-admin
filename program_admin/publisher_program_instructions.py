from typing import Tuple

from construct import Bytes, Int8ul, Struct
from solana import system_program
from solana.publickey import PublicKey
from solana.system_program import SYS_PROGRAM_ID, CreateAccountWithSeedParams
from solana.transaction import AccountMeta, TransactionInstruction


def config_account_pubkey(program_key: PublicKey) -> PublicKey:
    [config_account, _] = PublicKey.find_program_address(
        [b"CONFIG"],
        program_key,
    )
    return config_account


def publisher_config_account_pubkey(
    publisher_key: PublicKey, program_key: PublicKey
) -> PublicKey:
    [publisher_config_account, _] = PublicKey.find_program_address(
        [b"PUBLISHER_CONFIG", bytes(publisher_key)],
        program_key,
    )
    return publisher_config_account


def initialize_publisher_program(
    program_key: PublicKey,
    authority: PublicKey,
) -> TransactionInstruction:
    """
    Pyth publisher program initialize instruction with the given authority

    accounts:
    - payer account (signer, writable) - we pass the authority as the payer
    - config account (writable)
    - system program
    """

    [config_account, bump] = PublicKey.find_program_address(
        [b"CONFIG"],
        program_key,
    )

    ix_data_layout = Struct(
        "bump" / Int8ul,
        "authority" / Bytes(32),
    )

    ix_data = ix_data_layout.build(
        dict(
            bump=bump,
            authority=bytes(authority),
        )
    )

    return TransactionInstruction(
        data=ix_data,
        keys=[
            AccountMeta(pubkey=authority, is_signer=True, is_writable=True),
            AccountMeta(pubkey=config_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
        ],
        program_id=program_key,
    )


def create_buffer_account(
    program_key: PublicKey,
    base_pubkey: PublicKey,
    publisher_pubkey: PublicKey,
    space: int,
    lamports: int,
) -> Tuple[PublicKey, TransactionInstruction]:
    # The seed should be str but later is used in rust as
    # &str and therefore we use latin1 encoding to map byte
    # i to char i
    seed = bytes(publisher_pubkey).decode("latin-1")
    new_account_pubkey = PublicKey.create_with_seed(
        base_pubkey,
        seed,
        program_key,
    )

    return (
        new_account_pubkey,
        system_program.create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=base_pubkey,
                new_account_pubkey=new_account_pubkey,
                base_pubkey=base_pubkey,
                seed=seed,
                program_id=program_key,
                lamports=lamports,
                space=space,
            )
        ),
    )


def initialize_publisher_config(
    program_key: PublicKey,
    publisher_key: PublicKey,
    authority: PublicKey,
    buffer_account: PublicKey,
) -> TransactionInstruction:
    """
    Pyth publisher program initialize publisher config instruction with the given authority

    accounts:
    - authority account (signer, writable)
    - config account
    - publisher config account (writable)
    - buffer account (writable)
    - system program
    """

    [config_account, config_bump] = PublicKey.find_program_address(
        [b"CONFIG"],
        program_key,
    )

    [publisher_config_account, publisher_config_bump] = PublicKey.find_program_address(
        [b"PUBLISHER_CONFIG", bytes(publisher_key)],
        program_key,
    )

    ix_data_layout = Struct(
        "config_bump" / Int8ul,
        "publisher_config_bump" / Int8ul,
        "publisher" / Bytes(32),
    )

    ix_data = ix_data_layout.build(
        dict(
            config_bump=config_bump,
            publisher_config_bump=publisher_config_bump,
            publisher=bytes(publisher_key),
        )
    )

    return TransactionInstruction(
        data=ix_data,
        keys=[
            AccountMeta(pubkey=authority, is_signer=True, is_writable=True),
            AccountMeta(pubkey=config_account, is_signer=False, is_writable=True),
            AccountMeta(
                pubkey=publisher_config_account, is_signer=False, is_writable=True
            ),
            AccountMeta(pubkey=buffer_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
        ],
        program_id=program_key,
    )
