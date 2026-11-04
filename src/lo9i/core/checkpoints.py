"""Pruning a conversation's checkpoints. LangGraph saves one after every step, each holding the whole
state, so a conversation's checkpoints grow with the square of its length. Only the latest of each
namespace (the conversation, and each subagent call) is ever read: it holds every message, and its
pending writes are what an interrupted run resumes from. The older ones are deleted when a run ends;
the SQLite saver doesn't implement `aprune`. The subagent calls' namespaces are listed here too, for
reading what their checkpoints hold (the files their tools brought).

This holds while the graph keeps no DeltaChannel, whose value is rebuilt from older checkpoints
(tests/core/test_checkpoints.py checks it).
"""

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# For each row, the latest checkpoint of its thread and namespace. Checkpoint ids are time-ordered
# (UUID v6), the order the saver itself reads them in.
_LATEST = (
    "(SELECT MAX(latest.checkpoint_id) FROM checkpoints AS latest "
    "WHERE latest.thread_id = {table}.thread_id AND latest.checkpoint_ns = {table}.checkpoint_ns)"
)
_OLD_CHECKPOINTS = (
    f"DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_id < {_LATEST.format(table='checkpoints')}"
)
_OLD_WRITES = f"DELETE FROM writes WHERE thread_id = ? AND checkpoint_id < {_LATEST.format(table='writes')}"
_SUBGRAPHS = "SELECT DISTINCT checkpoint_ns FROM checkpoints WHERE thread_id = ? AND checkpoint_ns != '' ORDER BY 1"
_PRUNABLE = "SELECT DISTINCT thread_id FROM checkpoints GROUP BY thread_id, checkpoint_ns HAVING COUNT(*) > 1"


async def prune(saver: AsyncSqliteSaver, thread_id: str) -> int:
    """Deletes the conversation's checkpoints older than the latest of each namespace, and their writes.
    The caller holds the conversation's lock, so no run adds one meanwhile. Returns how many went."""
    async with saver.lock, saver.conn.cursor() as cursor:
        await cursor.execute(_OLD_CHECKPOINTS, (thread_id,))
        deleted = cursor.rowcount
        await cursor.execute(_OLD_WRITES, (thread_id,))
        await saver.conn.commit()
    return deleted


async def prunable(saver: AsyncSqliteSaver) -> list[str]:
    """Conversations with checkpoints to prune: those saved before pruning existed."""
    async with saver.lock, saver.conn.execute(_PRUNABLE) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def subgraph_namespaces(saver: AsyncSqliteSaver, thread_id: str) -> list[str]:
    """The namespaces the conversation's subgraphs saved checkpoints under: each delegate call's subagent
    (core/subagent.py)."""
    async with saver.lock, saver.conn.execute(_SUBGRAPHS, (thread_id,)) as cursor:
        return [row[0] for row in await cursor.fetchall()]
