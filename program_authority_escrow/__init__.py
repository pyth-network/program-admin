"""
This package is meant to provide an interface with the on-chain program authority escrow.
https://github.com/guibescos/program-authority-escrow
The program authority escrow is an on-chain program meant to facilitate safe transfer of authority for solana programs.
It lives at address escMHe7kSqPcDHx4HU44rAHhgdTLBZkUrU39aN8kMcL.
The interface of the program is the following :
- propose : this instruction can only be called by the current upgrade authority of a program. It proposes an authority transfer from the current authority to a new authority.
- accept : this instruction can be called by the new authority to accept the proposal and acquire the authority of the program. Thus, it completed the transfer.
- revert : After calling propose but before the new authority has accepted the current_authority can call revert to cancel the proposal.
"""
