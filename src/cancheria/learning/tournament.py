from .manager import get_learning_manager

async def run(force: bool = True):
    return await get_learning_manager().run_tournament(force=force)
