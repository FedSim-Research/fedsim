import json

from sqlalchemy import select

from fedsim.api.schemas import PresetCreate, PresetUpdate
from fedsim.persistence.database import SessionLocal
from fedsim.persistence.models import NodePreset


def list_presets(architecture: str, node_type: str) -> list[NodePreset]:
    session = SessionLocal()
    try:
        stmt = (
            select(NodePreset)
            .where(NodePreset.architecture == architecture, NodePreset.node_type == node_type)
            .order_by(NodePreset.id.asc())
        )
        return list(session.execute(stmt).scalars().all())
    finally:
        session.close()


def create_preset(payload: PresetCreate) -> NodePreset:
    session = SessionLocal()
    try:
        preset = NodePreset(
            architecture=payload.architecture,
            node_type=payload.node_type,
            name=payload.name.strip() or "Preset",
            config_json=json.dumps(payload.config),
        )
        session.add(preset)
        session.commit()
        session.refresh(preset)
        return preset
    finally:
        session.close()


def update_preset(preset_id: int, payload: PresetUpdate) -> NodePreset | None:
    session = SessionLocal()
    try:
        preset = session.get(NodePreset, preset_id)
        if preset is None:
            return None
        if payload.name is not None:
            preset.name = payload.name.strip() or preset.name
        if payload.config is not None:
            preset.config_json = json.dumps(payload.config)
        session.commit()
        session.refresh(preset)
        return preset
    finally:
        session.close()


def delete_preset(preset_id: int) -> bool:
    session = SessionLocal()
    try:
        preset = session.get(NodePreset, preset_id)
        if preset is None:
            return False
        session.delete(preset)
        session.commit()
        return True
    finally:
        session.close()
