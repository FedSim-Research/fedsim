import json

from fastapi import APIRouter, HTTPException, Query

from fedsim.api.schemas import PresetCreate, PresetResponse, PresetUpdate
from fedsim.services import preset_service

router = APIRouter(prefix="/presets", tags=["presets"])


def _to_response(preset) -> PresetResponse:
    return PresetResponse(
        preset_id=preset.id,
        architecture=preset.architecture,
        node_type=preset.node_type,
        name=preset.name,
        config=json.loads(preset.config_json),
    )


@router.get("/", response_model=list[PresetResponse])
def list_presets(
    architecture: str = Query(..., pattern="^(spyker|hierfl)$"),
    node_type: str = Query(..., pattern="^(SuperServerNode|ServerNode|ClientNode)$"),
):
    presets = preset_service.list_presets(architecture, node_type)
    return [_to_response(item) for item in presets]


@router.post("/", response_model=PresetResponse)
def create_preset(payload: PresetCreate):
    preset = preset_service.create_preset(payload)
    return _to_response(preset)


@router.put("/{preset_id}", response_model=PresetResponse)
def update_preset(preset_id: int, payload: PresetUpdate):
    preset = preset_service.update_preset(preset_id, payload)
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return _to_response(preset)


@router.delete("/{preset_id}")
def delete_preset(preset_id: int):
    deleted = preset_service.delete_preset(preset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"status": "deleted"}
