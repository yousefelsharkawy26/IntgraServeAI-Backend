import pytest
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

from utils.exceptions import (
    InternalActionNotAllowedException,
    MissingFieldException,
    ActionNotFoundException,
    InvalidActionFieldException,
    BodyParamOnGetRequestException,
)

from utils.schemas.action_schemas import (ActionCreate, ActionUpdate, ActionType)

from services.action_service import ActionService, DEFAULT_INTERNAL_ACTIONS



@pytest.fixture
def mock_settings(tmp_path, monkeypatch):
    """
    استبدال كائن settings بالكامل بكائن وهمي لتجاوز حماية Pydantic
    وتوجيه الملفات إلى مسارات مؤقتة.
    """
    file_path = tmp_path / "data" / "actions.json"
    backup_dir = tmp_path / "backups"

    class MockSettings:
        ACTIONS_FILE_FULL_PATH = file_path
        ACTIONS_BACKUP_DIR = backup_dir
        ACTIONS_BACKUP_ENABLED = True
        ACTIONS_BACKUP_COUNT = 3

    monkeypatch.setattr("services.action_service.settings", MockSettings)

    return {"file_path": file_path, "backup_dir": backup_dir}


@pytest.fixture
def action_service(mock_settings):
    """إنشاء نسخة (Instance) من الخدمة بعد تطبيق إعدادات المسارات المؤقتة"""
    service = ActionService()
    return service


@pytest.fixture
def valid_api_action_data():
    """بيانات نموذجية لإنشاء Action من نوع API_REQUEST"""
    return ActionCreate(
        name="fetch_user_data",
        description="Fetches user data from external API",
        type=ActionType.API_REQUEST,
        active=True,
        requires_confirmation=False,
        execution_config={
            "url": "https://api.example.com/users/{user_id}",
            "method": "GET",
            "protocol": "https",
        },
        parameters={
            "user_id": {
                "type": "integer",
                "required": True,
                "param_type": "path",
                "description": "ID of the user",
            }
        },
        response_config={
            "mode": "json",
            "template": "User data is {{data}}",
            "on_error": "Failed to fetch user",
            "values": {},
        },
    )


def test_initialization_creates_default_file(mock_settings):
    """اختبار أن تشغيل الخدمة لأول مرة ينشئ ملف JSON ويضع فيه الـ Internal Actions"""
    service = ActionService()

    assert mock_settings["file_path"].exists()

    with open(mock_settings["file_path"], "r") as f:
        data = json.load(f)

    assert "version" in data
    assert "actions" in data

    for int_id in DEFAULT_INTERNAL_ACTIONS.keys():
        assert int_id in data["actions"]


def test_validate_action_success(action_service):
    """اختبار التحقق من صحة بنية Action صحيح"""
    action_dict = {
        "name": "Test",
        "type": "api_request",
        "execution_config": {
            "url": "http://test.com",
            "method": "POST",
            "protocol": "http",
        },
        "response_config": {"mode": "json", "template": "Test", "on_error": "Error"},
    }

    is_valid, warnings = action_service.validate_action(action_dict)
    assert is_valid is True
    assert isinstance(warnings, list)


def test_validate_action_internal_fails(action_service):
    """اختبار أن محاولة التحقق/إنشاء فعل داخلي سترمي استثناء"""
    action_dict = {"type": "internal"}
    with pytest.raises(InternalActionNotAllowedException):
        action_service.validate_action(action_dict, is_update=False)


def test_validate_action_body_param_on_get(action_service):
    """اختبار رمي خطأ عند محاولة إرسال Body في طلب GET"""
    action_dict = {
        "name": "Test",
        "type": "api_request",
        "execution_config": {
            "url": "http://test.com",
            "method": "GET",
            "protocol": "http",
        },
        "parameters": {
            "data": {
                "param_type": "body",
                "type": "string",
                "required": True,
                "description": "Test body",
            }
        },
    }
    with pytest.raises(BodyParamOnGetRequestException):
        action_service.validate_action(action_dict)


def test_validate_action_invalid_protocol(action_service):
    """اختبار رمي خطأ إذا كان البروتوكول غير مدعوم في API Request"""
    action_dict = {
        "name": "Test",
        "type": "api_request",
        "execution_config": {
            "url": "http://test.com",
            "method": "GET",
            "protocol": "grpc",
        },
    }
    with pytest.raises(InvalidActionFieldException):
        action_service.validate_action(action_dict)


@pytest.mark.asyncio
async def test_get_all_actions(action_service):
    """اختبار استرجاع كل الأفعال (يجب أن يجلب الافتراضية على الأقل)"""
    actions, count = await action_service.get_all_actions()

    assert count == len(DEFAULT_INTERNAL_ACTIONS)
    assert isinstance(actions, list)
    assert actions[0].id.startswith("INT-")


@pytest.mark.asyncio
async def test_create_action_success(action_service, valid_api_action_data):
    """اختبار إنشاء Action جديد بنجاح"""
    action_id, name = await action_service.create_action(valid_api_action_data)

    assert action_id.startswith("ACT-")
    assert name == "fetch_user_data"

    saved_action = await action_service.get_action_by_id(action_id)
    assert saved_action.name == "fetch_user_data"
    assert saved_action.type == ActionType.API_REQUEST.value


@pytest.mark.asyncio
async def test_create_internal_action_fails(action_service):
    """اختبار منع إنشاء Internal Action من قبل المستخدم"""

    internal_data = ActionCreate.model_construct(
        name="hack_system",
        description="Try to create internal",
        type=ActionType.INTERNAL,
    )

    with pytest.raises(InternalActionNotAllowedException):
        await action_service.create_action(internal_data)


@pytest.mark.asyncio
async def test_update_action(action_service, valid_api_action_data):
    """اختبار تعديل Action"""

    action_id, _ = await action_service.create_action(valid_api_action_data)

    update_data = ActionUpdate(name="updated_name")
    updated_id, updated_name = await action_service.update_action(
        action_id, update_data
    )

    assert updated_id == action_id
    assert updated_name == "updated_name"

    action = await action_service.get_action_by_id(action_id)
    assert action.description == "Fetches user data from external API"


@pytest.mark.asyncio
async def test_delete_action(action_service, valid_api_action_data):
    """اختبار حذف Action"""
    action_id, _ = await action_service.create_action(valid_api_action_data)

    await action_service.delete_action(action_id)

    with pytest.raises(ActionNotFoundException):
        await action_service.get_action_by_id(action_id)


@pytest.mark.asyncio
async def test_delete_internal_action_fails(action_service):
    """اختبار أن محاولة حذف فعل افتراضي ترفض"""
    with pytest.raises(InternalActionNotAllowedException):
        await action_service.delete_action("INT-001")


@pytest.mark.asyncio
async def test_toggle_action_status(action_service):
    """اختبار تفعيل / تعطيل Action (بما في ذلك الداخلي)"""

    action_id = "INT-001"

    _, _, new_status = await action_service.toggle_action_status(action_id)
    assert new_status is False

    _, _, new_status_2 = await action_service.toggle_action_status(action_id)
    assert new_status_2 is True


@pytest.mark.asyncio
async def test_backup_created_on_save(
    action_service, valid_api_action_data, mock_settings
):
    """اختبار أن إجراء تعديل (إنشاء فعل) يقوم بإنشاء ملف نسخة احتياطية"""
    assert (
        not mock_settings["backup_dir"].exists()
        or len(list(mock_settings["backup_dir"].glob("*.json"))) == 0
    )

    await action_service.create_action(valid_api_action_data)

    backups = await action_service.get_all_backups()
    assert len(backups) > 0
    assert backups[0]["filename"].startswith("actions_backup_")


@pytest.mark.asyncio
async def test_restore_backup(action_service, valid_api_action_data, mock_settings):
    """اختبار استرجاع نسخة احتياطية بنجاح"""

    with patch("services.action_service.datetime") as mock_datetime:

        mock_datetime.now.side_effect = [
            datetime(2026, 4, 1, 10, 0, i) for i in range(20)
        ]
        mock_datetime.timezone = timezone

        action_id, _ = await action_service.create_action(valid_api_action_data)

        await action_service.toggle_action_status(action_id)

        backups = await action_service.get_all_backups()

        latest_backup = backups[0]["filename"]

        await action_service.delete_action(action_id)
        with pytest.raises(ActionNotFoundException):
            await action_service.get_action_by_id(action_id)

        result = await action_service.restore_backup(latest_backup)
        assert result["message"] == "Backup restored successfully"

        restored_action = await action_service.get_action_by_id(action_id)
        assert restored_action.name == valid_api_action_data.name
