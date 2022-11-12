from typing import Dict, List

from solana.blockhash import Blockhash
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solana.transaction import SIG_LENGTH, Transaction
from solana.utils import shortvec_encoding as shortvec

from program_admin.types import (
    Network,
    PythMappingAccount,
    ReferenceOverrides,
    ReferencePermissions,
)

MAPPING_ACCOUNT_SIZE = 20536  # https://github.com/pyth-network/pyth-client/blob/b49f73afe32ce8685a3d05e32d8f3bb51909b061/program/src/oracle/oracle.h#L88
MAPPING_ACCOUNT_PRODUCT_LIMIT = 640
PRICE_ACCOUNT_SIZE = 3312
PRODUCT_ACCOUNT_SIZE = 512
SOL_LAMPORTS = pow(10, 9)


async def recent_blockhash(client: AsyncClient) -> Blockhash:
    blockhash_response = await client.get_recent_blockhash(
        commitment=Commitment("finalized")
    )

    if not "result" in blockhash_response:
        raise RuntimeError("Failed to get recent blockhash")

    return Blockhash(blockhash_response["result"]["value"]["blockhash"])


def compute_transaction_size(transaction: Transaction) -> int:
    """
    Returns the total over-the-wire size of a transaction

    This is the same code from solana.transaction.Transaction.__serialize()
    """
    payload = bytearray()
    signature_count = shortvec.encode_length(len(transaction.signatures))

    payload.extend(signature_count)

    for sig_pair in transaction.signatures:
        if sig_pair.signature:
            payload.extend(sig_pair.signature)
        else:
            payload.extend(bytearray(SIG_LENGTH))

    payload.extend(transaction.serialize_message())

    return len(payload)


def encode_product_metadata(data: Dict[str, str]) -> bytes:
    buffer = b""

    for key, value in data.items():
        key_bytes = key.encode("utf8")
        key_len = len(key_bytes).to_bytes(1, byteorder="little")
        value_bytes = value.encode("utf8")
        value_len = len(value_bytes).to_bytes(1, byteorder="little")

        buffer += key_len + key_bytes + value_len + value_bytes

    return buffer


def sort_mapping_account_keys(accounts: List[PythMappingAccount]) -> List[PublicKey]:
    """
    Takes a list of mapping accounts and returns a list of mapping account keys
    matching the order of the mapping linked list
    """
    if not accounts:
        return []

    # We can easily tell which is the last key (its next key is 0), so start
    # from it and build a reverse linked list as a "previous keys" dict.
    previous_keys = {}
    last_key = None

    for account in accounts:
        this_key = account.public_key
        next_key = account.data.next_mapping_account_key

        if next_key == PublicKey(0):
            last_key = this_key

        previous_keys[next_key] = this_key

    if not last_key:
        raise RuntimeError("The linked list has no end")

    # Now traverse the inverted linked list and build a list in the right order
    sorted_keys: List[PublicKey] = []
    current: PublicKey = last_key

    while len(accounts) != len(sorted_keys):
        sorted_keys.insert(0, current)

        # There is no previous key to the first key
        if previous_keys.get(current):
            current = previous_keys[current]

    return sorted_keys


def apply_overrides(
    ref_permissions: ReferencePermissions,
    ref_overrides: ReferenceOverrides,
    network: Network,
) -> ReferencePermissions:
    network_overrides = ref_overrides.get(network, {})

    overridden_permissions: ReferencePermissions = {}
    for key, value in ref_permissions.items():
        if key in network_overrides and not network_overrides[key]:
            # Remove all publishers from all account types for this symbol
            overridden_permissions[key] = {k: [] for k in value.keys()}
        else:
            overridden_permissions[key] = value
    return overridden_permissions
