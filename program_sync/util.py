import argparse
import os
from typing import List

from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient

from program_sync.types import MappingData, PythAccount


# pylint: disable=super-with-arguments
class EnvDefault(argparse.Action):
    # Allow setting arguments from environment variables
    # https://stackoverflow.com/a/10551190
    def __init__(self, env_var, required=True, default=None, **kwargs):
        if not default and env_var:
            if env_var in os.environ:
                default = os.environ[env_var]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(default=default, required=required, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


async def recent_blockhash(client: AsyncClient) -> str:
    blockhash_response = await client.get_recent_blockhash()

    return blockhash_response["result"]["value"]["blockhash"]


def sort_mapping_account_keys(accounts: List[PythAccount]) -> List[PublicKey]:
    """
    Takes a list of mapping accounts and returns a list of mapping account keys
    matching the order of mapping accounts linked list
    """
    previous_map = {}
    last_key = None

    for account in accounts:
        if not (account and isinstance(account.data, MappingData)):
            raise RuntimeError("Not a mapping account")

        this_key = account.public_key
        next_key = account.data.next_mapping_account_key

        if next_key == PublicKey(0):
            last_key = this_key

        previous_map[next_key] = this_key

    if not last_key:
        raise RuntimeError("The mapping account linked list has no end")

    sorted_keys: List[PublicKey] = []
    current: PublicKey = last_key

    while len(accounts) != len(sorted_keys):
        sorted_keys.insert(0, current)

        current = previous_map[current]

    return sorted_keys
