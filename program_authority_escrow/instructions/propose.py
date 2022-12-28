from __future__ import annotations

import typing

from solana.publickey import PublicKey
from solana.transaction import AccountMeta, TransactionInstruction

from ..program_id import BPF_UPGRADABLE_LOADER, PROGRAM_ID


class ProposeAccounts(typing.TypedDict):
    current_authority: PublicKey
    new_authority: PublicKey
    program_account: PublicKey


def propose(
    accounts: ProposeAccounts,
    program_id: PublicKey = PROGRAM_ID,
    remaining_accounts: typing.Optional[typing.List[AccountMeta]] = None,
) -> TransactionInstruction:

    escrow_authority = PublicKey.find_program_address(
        [bytes(accounts["current_authority"]), bytes(accounts["new_authority"])],
        PROGRAM_ID,
    )[0]

    program_data = PublicKey.find_program_address(
        [bytes(accounts["program_account"])], BPF_UPGRADABLE_LOADER
    )[0]

    keys: list[AccountMeta] = [
        AccountMeta(
            pubkey=accounts["current_authority"], is_signer=True, is_writable=False
        ),
        AccountMeta(
            pubkey=accounts["new_authority"], is_signer=False, is_writable=False
        ),
        AccountMeta(pubkey=escrow_authority, is_signer=False, is_writable=False),
        AccountMeta(
            pubkey=accounts["program_account"], is_signer=False, is_writable=False
        ),
        AccountMeta(pubkey=program_data, is_signer=False, is_writable=True),
        AccountMeta(pubkey=BPF_UPGRADABLE_LOADER, is_signer=False, is_writable=False),
    ]
    if remaining_accounts is not None:
        keys += remaining_accounts
    identifier = b"]\xfdR\xa8v!fZ"  # Anchor discriminator (a hash of the name of the instruction)
    encoded_args = b""
    data = identifier + encoded_args
    return TransactionInstruction(keys, program_id, data)
