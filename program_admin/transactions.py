from solana import system_program
from solana.blockhash import Blockhash
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.transaction import Transaction

from program_admin.instructions import init_mapping
from program_admin.util import SOL_LAMPORTS


async def initialize_mapping_account(
    blockhash: Blockhash,
    program_key: PublicKey,
    funding_keypair: Keypair,
    mapping_keypair: Keypair,
) -> Transaction:
    instruction = init_mapping(
        program_key,
        funding_keypair.public_key,
        mapping_keypair.public_key,
    )
    transaction = Transaction(
        recent_blockhash=blockhash,
        fee_payer=funding_keypair.public_key,
    )

    transaction.add(instruction)
    transaction.sign(funding_keypair, mapping_keypair)

    return transaction


async def create_account(
    blockhash: Blockhash,
    program_key: PublicKey,
    from_keypair: Keypair,
    new_account_keypair: Keypair,
):
    instruction = system_program.create_account(
        system_program.CreateAccountParams(
            from_pubkey=from_keypair.public_key,
            new_account_pubkey=new_account_keypair.public_key,
            lamports=1 * SOL_LAMPORTS,
            space=20536,
            program_id=program_key,
        )
    )
    transaction = Transaction(
        recent_blockhash=blockhash, fee_payer=from_keypair.public_key
    )

    transaction.add(instruction)
    transaction.sign(from_keypair)

    return transaction
