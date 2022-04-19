from typing import List

from solana.blockhash import Blockhash
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient

from program_admin.types import PythMappingAccount

MAPPING_ACCOUNT_SIZE = 20536  # https://github.com/pyth-network/pyth-client/blob/b49f73afe32ce8685a3d05e32d8f3bb51909b061/program/src/oracle/oracle.h#L88
MAPPING_ACCOUNT_PRODUCT_LIMIT = 640
PRODUCT_ACCOUNT_SIZE = 512
SOL_LAMPORTS = pow(10, 9)


async def recent_blockhash(client: AsyncClient) -> Blockhash:
    blockhash_response = await client.get_recent_blockhash()

    return Blockhash(blockhash_response["result"]["value"]["blockhash"])


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
