"""Phase 1 — Unit tests for utils.exceptions.

Covers exception hierarchy, structured logging adapter, and correlation-id context vars.
"""

import logging

import pytest

from utils.exceptions import (
    ActionEngineException,
    ParsingException,
    ExecutionException,
    ActionNotFound,
    ActionNotActive,
    ProviderConfigurationError,
    ActionRequiresConfirmationError,
    CorrelationIdAdapter,
    get_correlation_id,
    set_correlation_id,
    _correlation_id_var,
)


@pytest.mark.unit
class TestExceptionHierarchy:
    """Every exception class must participate in the expected inheritance tree."""

    def test_base_hierarchy(self):
        assert issubclass(ParsingException, ActionEngineException)
        assert issubclass(ExecutionException, ActionEngineException)
        assert issubclass(ActionNotFound, ExecutionException)
        assert issubclass(ActionNotActive, ExecutionException)
        assert issubclass(ProviderConfigurationError, ExecutionException)

    def test_parsing_subclasses(self):
        from utils.exceptions import (
            MissingField,
            InvalidActionStructure,
            InvalidActionField,
            UnsupportedActionType,
            InvalidParamValueType,
            InvalidParamType,
            InvalidResponseMode,
        )
        for cls in [
            MissingField,
            InvalidActionStructure,
            InvalidActionField,
            UnsupportedActionType,
            InvalidParamValueType,
            InvalidParamType,
            InvalidResponseMode,
        ]:
            assert issubclass(cls, ParsingException)

    def test_execution_subclasses(self):
        from utils.exceptions import (
            PathParamNotFound,
            BodyParamOnGetRequest,
            UserDeniedConfirmation,
            ProtoNotFound,
            ServiceNotFound,
            MethodNotFound,
            UnsupportedDatabaseDriver,
            EmbeddingGenerationError,
            VectorSearchError,
        )
        for cls in [
            PathParamNotFound,
            BodyParamOnGetRequest,
            UserDeniedConfirmation,
            ProtoNotFound,
            ServiceNotFound,
            MethodNotFound,
            UnsupportedDatabaseDriver,
            EmbeddingGenerationError,
            VectorSearchError,
        ]:
            assert issubclass(cls, ExecutionException)


@pytest.mark.unit
class TestActionRequiresConfirmationError:
    """The confirmation exception must carry action metadata."""

    def test_attributes(self):
        exc = ActionRequiresConfirmationError("Paused", "delete_user", {"id": "42"})
        assert exc.action_name == "delete_user"
        assert exc.params == {"id": "42"}
        assert str(exc) == "Paused"

    def test_inheritance(self):
        exc = ActionRequiresConfirmationError("Paused", "act", {})
        assert isinstance(exc, ActionEngineException)


@pytest.mark.unit
class TestCorrelationId:
    """Context-var correlation ID lifecycle and adapter injection."""

    def test_get_default_is_none(self):
        # Ensure clean state
        _correlation_id_var.set(None)
        assert get_correlation_id() is None

    def test_set_and_get(self):
        token = set_correlation_id("abc-123")
        assert get_correlation_id() == "abc-123"
        # Cleanup
        _correlation_id_var.set(None)

    def test_set_returns_token(self):
        token = set_correlation_id("xyz-789")
        assert token is not None
        _correlation_id_var.set(None)

    def test_correlation_id_adapter(self, caplog):
        logger = logging.getLogger("test_correlation")
        adapter = CorrelationIdAdapter(logger, {})

        set_correlation_id("test-cid")
        try:
            msg, kwargs = adapter.process("Hello world", {})
            assert "[correlation_id=test-cid]" in msg
            assert "Hello world" in msg
        finally:
            _correlation_id_var.set(None)

    def test_adapter_no_correlation_id(self, caplog):
        _correlation_id_var.set(None)
        logger = logging.getLogger("test_correlation_2")
        adapter = CorrelationIdAdapter(logger, {})
        msg, kwargs = adapter.process("No CID", {})
        assert msg == "No CID"
        assert "correlation_id" not in msg

    def test_isolation_between_contexts(self):
        """Correlation IDs set in one context must not leak to another."""
        set_correlation_id("first")
        cid1 = get_correlation_id()
        set_correlation_id("second")
        cid2 = get_correlation_id()
        assert cid1 == "first"
        assert cid2 == "second"
        _correlation_id_var.set(None)
