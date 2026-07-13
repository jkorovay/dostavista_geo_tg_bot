"""
Tests for FSM state machine and handler logic.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock

from bot import OrderForm, cmd_start, process_start
from bot import dp


class MockMessage:
    """Mock aiogram Message for testing."""

    def __init__(self, text: str = "", user_id: int = 12345, chat_id: int = 12345):
        self.text = text
        self.from_user = MagicMock()
        self.from_user.id = user_id
        self.chat = MagicMock()
        self.chat.id = chat_id
        self.answers = []  # Store sent messages

    async def answer(self, text: str, **kwargs):
        self.answers.append((text, kwargs))
        return MagicMock(message_id=1)

    async def edit_text(self, text: str, **kwargs):
        self.answers.append(("EDIT:" + text, kwargs))
        return MagicMock()


class MockBot:
    """Mock aiogram Bot for testing."""

    def __init__(self):
        self.id = 99999


@pytest.fixture
def mock_bot():
    """Mock bot instance."""
    return MockBot()


@pytest_asyncio.fixture
async def fsm_context(mock_bot):
    """FSM context with MemoryStorage for testing."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    storage = MemoryStorage()
    key = StorageKey(bot_id=mock_bot.id, chat_id=12345, user_id=12345)
    context = FSMContext(storage=storage, key=key)
    yield context
    await storage.close()


class TestFSMStates:
    """Tests for FSM state definitions."""

    def test_states_exist(self):
        """All required states are defined."""
        assert hasattr(OrderForm, 'waiting_for_start')
        assert hasattr(OrderForm, 'waiting_for_pickup')
        assert hasattr(OrderForm, 'waiting_for_delivery')
        assert hasattr(OrderForm, 'waiting_for_price')


@pytest.mark.asyncio
class TestStartHandler:
    """Tests for /start command handler."""

    async def test_cmd_start_clears_state_and_sets_waiting_for_start(self, fsm_context):
        """Start clears state and sets waiting_for_start."""
        message = MockMessage(text="/start")

        await cmd_start(message, fsm_context)

        # Check state was set
        state = await fsm_context.get_state()
        assert state == OrderForm.waiting_for_start.state

    async def test_cmd_start_sends_keyboard(self, fsm_context):
        """Start sends keyboard with location button."""
        message = MockMessage(text="/start")

        await cmd_start(message, fsm_context)

        # Verify keyboard was sent
        assert message.answers
        assert "Где ты сейчас?" in message.answers[0][0]


@pytest.mark.asyncio
class TestProcessStart:
    """Tests for process_start handler."""

    async def test_process_start_with_location(self, fsm_context):
        """Process start with location message."""
        message = MockMessage(text="")
        message.location = MagicMock()
        message.location.latitude = 55.7558
        message.location.longitude = 37.6173

        # Inject mock HTTP client into dispatcher
        mock_http = AsyncMock()
        dp["http"] = mock_http

        await process_start(message, fsm_context)

        # Check state was updated
        state = await fsm_context.get_state()
        assert state == OrderForm.waiting_for_pickup.state

        # Check data was stored
        data = await fsm_context.get_data()
        assert data['start_coords'] == [37.6173, 55.7558]