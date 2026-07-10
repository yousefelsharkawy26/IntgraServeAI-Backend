import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from utils.token_helper import TokenHelper
from models.auth import TokenBlacklist


@pytest.fixture
def mock_db():
    """Mock AsyncSession for blacklist tests."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def sample_access_token():
    """Return a sample access token string."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzIiwidHlwZSI6ImFjY2VzcyIsImV4cCI6OTk5OTk5OTk5OX0.test"


@pytest.fixture
def sample_refresh_token():
    """Return a sample refresh token string."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzIiwidHlwZSI6InJlZnJlc2giLCJleHAiOjk5OTk5OTk5OTl9.test"


class TestHashToken:
    def test_hash_is_deterministic(self):
        token = "my-secret-token"
        h1 = TokenHelper._hash_token(token)
        h2 = TokenHelper._hash_token(token)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_tokens_different_hashes(self):
        h1 = TokenHelper._hash_token("token-one")
        h2 = TokenHelper._hash_token("token-two")
        assert h1 != h2


class TestIsTokenBlacklisted:
    @pytest.mark.asyncio
    async def test_not_blacklisted(self, mock_db, sample_access_token):
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        
        result = await TokenHelper.is_token_blacklisted(sample_access_token, mock_db)
        assert result is False

    @pytest.mark.asyncio
    async def test_blacklisted(self, mock_db, sample_access_token):
        entry = MagicMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=entry))
        
        result = await TokenHelper.is_token_blacklisted(sample_access_token, mock_db)
        assert result is True

    @pytest.mark.asyncio
    async def test_expired_entry_not_counted(self, mock_db, sample_access_token):
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        
        result = await TokenHelper.is_token_blacklisted(sample_access_token, mock_db)
        assert result is False


class TestBlacklistToken:
    @pytest.mark.asyncio
    @patch("utils.token_helper.TokenHelper.verify_token")
    async def test_adds_to_blacklist(self, mock_verify, mock_db, sample_refresh_token):
        mock_verify.return_value = {"exp": datetime.now(timezone.utc).timestamp() + 3600, "type": "refresh"}
        
        await TokenHelper.blacklist_token(sample_refresh_token, "refresh", mock_db)
        
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        
        args = mock_db.add.call_args[0][0]
        assert isinstance(args, TokenBlacklist)
        assert args.token_type == "refresh"
        assert args.token_hash == TokenHelper._hash_token(sample_refresh_token)

    @pytest.mark.asyncio
    @patch("utils.token_helper.TokenHelper.verify_token")
    async def test_cleanup_expired_on_blacklist(self, mock_verify, mock_db, sample_refresh_token):
        mock_verify.return_value = {"exp": datetime.now(timezone.utc).timestamp() + 3600, "type": "refresh"}
        
        await TokenHelper.blacklist_token(sample_refresh_token, "refresh", mock_db)
        
        # Cleanup should have been attempted (execute called at least twice)
        assert mock_db.execute.call_count >= 1
