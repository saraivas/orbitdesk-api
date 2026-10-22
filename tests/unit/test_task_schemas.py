import pytest
from pydantic import ValidationError
from app.schemas.task import TaskCreate, TaskUpdate
from app.models.task import TaskType


def test_task_create_rejects_blank_title():
    with pytest.raises(ValidationError):
        TaskCreate(title="   ")


def test_task_create_strips_whitespace_from_title():
    task = TaskCreate(title="  Comprar leite  ")
    assert task.title == "Comprar leite"


def test_task_create_defaults_to_standard_type():
    task = TaskCreate(title="Tarefa qualquer")
    assert task.type == TaskType.standard


def test_task_create_accepts_confidential_type():
    task = TaskCreate(title="Tarefa sigilosa", type=TaskType.confidential)
    assert task.type == TaskType.confidential


def test_task_create_rejects_invalid_type():
    with pytest.raises(ValidationError):
        TaskCreate(title="Tarefa", type="nao_existe")


def test_task_update_allows_all_fields_omitted():
    task = TaskUpdate()
    assert task.title is None
    assert task.status is None


def test_task_update_rejects_blank_title_when_provided():
    with pytest.raises(ValidationError):
        TaskUpdate(title="   ")


def test_task_update_has_no_type_field():
    task = TaskUpdate(title="Novo título")
    assert not hasattr(task, "type")


def test_task_create_blank_title_error_message():
    with pytest.raises(ValidationError) as exc:
        TaskCreate(title="   ")
    assert "Title cannot be blank" in str(exc.value)
